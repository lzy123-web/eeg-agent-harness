"""CCEP/LRSP v1.1: contract-indexed EEG evidence dependency planning."""

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import time

from ...planning import ConstrainedPlanRunner, StateAwareConstrainedPlanner
from ...tooling import ToolRequest
from .agent import Point1RunResult
from .contracts import close_ledger, compile_intent, validate_plan_against_ledger
from .v1 import ConstraintCarryingEEGAgentV1, DynamicPlanningRunResult, ResidualAction


@dataclass(frozen=True)
class GoalContract:
    goal: str
    tool_name: str | None
    role: str
    input_policy: str
    base_dependencies: tuple[str, ...]
    priority: int
    answer_required: bool = False

    def to_dict(self):
        return {
            "goal": self.goal,
            "tool_name": self.tool_name,
            "role": self.role,
            "input_policy": self.input_policy,
            "base_dependencies": list(self.base_dependencies),
            "priority": self.priority,
            "answer_required": self.answer_required,
        }


@dataclass(frozen=True)
class ArtifactBinding:
    artifact_id: str
    fingerprint: str

    def to_dict(self):
        return {
            "artifact_id": self.artifact_id,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True)
class GoalEvidence:
    goal: str
    token_id: str
    semantic_id: str
    tool_name: str | None
    request_id: str | None
    dependency_tokens: tuple[tuple[str, str], ...]
    input_binding: ArtifactBinding | None = None
    output_binding: ArtifactBinding | None = None
    mode: str | None = None
    result: dict | None = None

    def to_dict(self):
        return {
            "goal": self.goal,
            "token_id": self.token_id,
            "semantic_id": self.semantic_id,
            "tool_name": self.tool_name,
            "request_id": self.request_id,
            "dependency_tokens": dict(self.dependency_tokens),
            "input_binding": None if self.input_binding is None else self.input_binding.to_dict(),
            "output_binding": None if self.output_binding is None else self.output_binding.to_dict(),
            "mode": self.mode,
        }


GOAL_CONTRACTS = {
    item.goal: item for item in (
        GoalContract("observe_events", "list_events", "observation", "none", (), 10),
        GoalContract(
            "create_epochs", "create_epochs", "producer", "none",
            ("observe_events",), 20,
        ),
        GoalContract(
            "epoch_quality", "epoch_quality", "evidence", "source_epochs",
            ("create_epochs",), 30, True,
        ),
        GoalContract(
            "trial_selection", "select_quality_epochs", "transition", "source_epochs",
            ("epoch_quality",), 40, True,
        ),
        GoalContract(
            "epoch_summary", "epoch_summary", "consumer", "effective_epochs",
            ("create_epochs",), 50, True,
        ),
        GoalContract(
            "event_bandpower", "event_bandpower", "consumer", "effective_epochs",
            ("create_epochs",), 60, True,
        ),
    )
}


def _stable_token(payload):
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str,
    ).encode("utf-8")
    return "goal-token:" + hashlib.sha256(encoded).hexdigest()


class ContractGraphResidualPlanner:
    """Derive one frontier from contracts, artifact versions, and residual goals."""

    RETRYABLE_CODES = frozenset({"INJECTED_TRANSIENT_FAILURE", "TEMPORARY_TOOL_FAILURE"})
    STATE_CONFLICT_CODES = frozenset({"ARTIFACT_NOT_FOUND", "ARTIFACT_STATE_CONFLICT"})

    def __init__(
        self, context, task, ledger, *, max_retries=1, max_repairs=2,
        max_tool_calls=16, contracts=None,
    ):
        if task.goal != "event_workflow":
            raise ValueError("LRSP v1.1 contract graph currently supports event_workflow")
        self.context = context
        self.task = task
        self.ledger = ledger
        self.contracts = dict(contracts or GOAL_CONTRACTS)
        self.requested_goals = tuple(task.arguments.get("objectives", ()))
        unknown = set(self.requested_goals) - set(self.contracts)
        if not self.requested_goals or unknown:
            raise ValueError(f"Unsupported v1.1 objectives: {sorted(unknown)}")
        self.labels = tuple(task.arguments.get("labels", ()))
        self.epoch_arguments = {
            "labels": list(self.labels),
            "tmin": task.arguments.get("tmin"),
            "tmax": task.arguments.get("tmax"),
        }
        if "baseline" in task.arguments:
            self.epoch_arguments["baseline"] = list(task.arguments["baseline"])
        self.selection_authorized = task.arguments.get("selection_authorized") is True
        self.dependencies = self._compile_dependencies()
        self.active_goals = tuple(sorted(
            self.dependencies,
            key=lambda name: (self.contracts[name].priority, name),
        ))
        self.max_retries = int(max_retries)
        self.max_repairs = int(max_repairs)
        self.max_tool_calls = int(max_tool_calls)
        self.evidence = {}
        self.evidence_cache = {}
        self.results = []
        self.transitions = []
        self.attempts = Counter()
        self.retries = 0
        self.repairs = 0
        self.blocked = None
        self._fingerprints = {}

    def _compile_dependencies(self):
        dependencies = {}

        def add(goal):
            if goal in dependencies:
                return
            contract = self.contracts[goal]
            deps = list(contract.base_dependencies)
            if contract.input_policy == "effective_epochs" and "trial_selection" in self.requested_goals:
                deps = [item for item in deps if item != "create_epochs"]
                deps.append("trial_selection")
            dependencies[goal] = tuple(dict.fromkeys(deps))
            for dependency in dependencies[goal]:
                add(dependency)

        for goal in self.requested_goals:
            add(goal)
        return dependencies

    def _record_transition(self, event, **details):
        self.transitions.append({"event": event, **details})

    def _begin_frontier_snapshot(self):
        self._fingerprints = {}

    def _artifact_fingerprint(self, artifact_id):
        if not artifact_id or artifact_id not in self.context.artifacts:
            return None
        if artifact_id not in self._fingerprints:
            self._fingerprints[artifact_id] = self.context.artifacts[
                artifact_id
            ].content_fingerprint()
        return self._fingerprints[artifact_id]

    def _binding_valid(self, binding):
        return (
            binding is None
            or self._artifact_fingerprint(binding.artifact_id) == binding.fingerprint
        )

    def _source_binding(self):
        token = self.evidence.get("create_epochs")
        return None if token is None else token.output_binding

    def _selection_mode(self):
        token = self.evidence.get("trial_selection")
        return None if token is None else token.mode

    def _effective_binding(self):
        if "trial_selection" in self.requested_goals:
            token = self.evidence.get("trial_selection")
            return None if token is None else token.output_binding
        return self._source_binding()

    def _input_binding(self, goal):
        policy = self.contracts[goal].input_policy
        if policy == "source_epochs":
            return self._source_binding()
        if policy == "effective_epochs":
            return self._effective_binding()
        return None

    def _dependency_tokens(self, goal):
        return tuple(
            (dependency, self.evidence[dependency].token_id)
            for dependency in self.dependencies[goal]
        )

    def _evidence_payload(
        self, goal, *, arguments, input_binding, output_binding, mode,
        semantic=False,
    ):
        if semantic:
            normalized_arguments = {
                key: value for key, value in dict(arguments or {}).items()
                if key not in {
                    "artifact_id", "expected_artifact_fingerprint",
                    "expected_quality_evidence_id",
                }
            }
            normalize_binding = lambda binding: (
                None if binding is None else {"fingerprint": binding.fingerprint}
            )
            dependencies = {
                dependency: self.evidence[dependency].semantic_id
                for dependency in self.dependencies[goal]
            }
        else:
            normalized_arguments = dict(arguments or {})
            normalize_binding = lambda binding: (
                None if binding is None else binding.to_dict()
            )
            dependencies = dict(self._dependency_tokens(goal))
        return {
            "goal": goal,
            "arguments": normalized_arguments,
            "input": normalize_binding(input_binding),
            "output": normalize_binding(output_binding),
            "dependencies": dependencies,
            "mode": mode,
        }

    def _reconcile(self):
        invalid = set()
        reasons = {}
        for goal, token in self.evidence.items():
            if not self._binding_valid(token.input_binding):
                invalid.add(goal)
                reasons[goal] = "input_artifact_changed_or_missing"
            elif not self._binding_valid(token.output_binding):
                invalid.add(goal)
                reasons[goal] = "output_artifact_changed_or_missing"
        changed = True
        while changed:
            changed = False
            for goal, token in self.evidence.items():
                if goal in invalid:
                    continue
                expected = dict(token.dependency_tokens)
                if any(
                    dependency in invalid
                    or dependency not in self.evidence
                    or self.evidence[dependency].token_id != expected.get(dependency)
                    for dependency in self.dependencies[goal]
                ):
                    invalid.add(goal)
                    reasons[goal] = "dependency_evidence_invalidated"
                    changed = True
        if invalid:
            ordered = sorted(invalid, key=lambda name: (self.contracts[name].priority, name))
            for goal in ordered:
                token = self.evidence.pop(goal, None)
                if token is not None and self.contracts[goal].role == "consumer":
                    self.evidence_cache.setdefault(goal, {})[token.semantic_id] = token
            self._record_transition(
                "evidence_graph_invalidated",
                goals=ordered,
                reasons={goal: reasons[goal] for goal in ordered},
            )

    def _quality_result(self):
        token = self.evidence.get("epoch_quality")
        return None if token is None else token.result

    def _block(self, code, message, **details):
        self.blocked = {"code": code, "message": message, **details}
        self._record_transition("scientific_stop", **self.blocked)

    def _materialize_evidence(
        self, goal, *, request_id=None, result=None, input_binding=None,
        output_binding=None, mode=None, arguments=None,
    ):
        dependencies = self._dependency_tokens(goal)
        payload = self._evidence_payload(
            goal, arguments=arguments, input_binding=input_binding,
            output_binding=output_binding, mode=mode,
        )
        semantic_payload = self._evidence_payload(
            goal, arguments=arguments, input_binding=input_binding,
            output_binding=output_binding, mode=mode, semantic=True,
        )
        token = GoalEvidence(
            goal=goal,
            token_id=_stable_token(payload),
            semantic_id=_stable_token(semantic_payload),
            tool_name=self.contracts[goal].tool_name if request_id else None,
            request_id=request_id,
            dependency_tokens=dependencies,
            input_binding=input_binding,
            output_binding=output_binding,
            mode=mode,
            result=result,
        )
        self.evidence[goal] = token
        return token

    def _restore_cached_consumer(self, goal):
        if self.contracts[goal].role != "consumer":
            return False
        input_binding = self._input_binding(goal)
        arguments = self._action_arguments(goal)
        semantic_payload = self._evidence_payload(
            goal, arguments=arguments, input_binding=input_binding,
            output_binding=None, mode=None, semantic=True,
        )
        semantic_id = _stable_token(semantic_payload)
        cached = self.evidence_cache.get(goal, {}).get(semantic_id)
        if cached is None:
            return False
        payload = self._evidence_payload(
            goal, arguments=arguments, input_binding=input_binding,
            output_binding=None, mode=None,
        )
        release_result = deepcopy(cached.result)
        release_request_id = (
            f"reuse-{goal}-{semantic_id.removeprefix('goal-token:')[:12]}"
        )
        release_result["request_id"] = release_request_id
        release_result["execution_kind"] = "semantic_evidence_reuse"
        release_result["reused_from_request_id"] = cached.request_id
        if isinstance(release_result.get("data"), dict):
            if "artifact_id" in release_result["data"]:
                release_result["data"]["artifact_id"] = input_binding.artifact_id
            if "artifact_fingerprint" in release_result["data"]:
                release_result["data"]["artifact_fingerprint"] = input_binding.fingerprint
            release_result["data"]["evidence_reuse"] = {
                "source_request_id": cached.request_id,
                "current_artifact_id": input_binding.artifact_id,
                "current_artifact_fingerprint": input_binding.fingerprint,
                "scientific_content_equivalent": True,
            }
        restored = GoalEvidence(
            goal=goal,
            token_id=_stable_token(payload),
            semantic_id=semantic_id,
            tool_name=cached.tool_name,
            request_id=release_request_id,
            dependency_tokens=self._dependency_tokens(goal),
            input_binding=input_binding,
            output_binding=None,
            mode=None,
            result=release_result,
        )
        self.evidence[goal] = restored
        self._record_transition(
            "goal_evidence_reused",
            goal=goal,
            cached_token_id=cached.token_id,
            restored_token_id=restored.token_id,
            semantic_id=semantic_id,
            artifact_fingerprint=input_binding.fingerprint,
            release_request_id=release_request_id,
        )
        return True

    def _release_results(self):
        results = []
        seen = set()
        for goal in self.active_goals:
            token = self.evidence.get(goal)
            if (
                token is None or token.result is None
                or not self.contracts[goal].answer_required
                or token.result["request_id"] in seen
            ):
                continue
            seen.add(token.result["request_id"])
            results.append(token.result)
        return tuple(results)

    def _resolve_selection(self):
        quality = self._quality_result()
        if quality is None:
            return None
        if not self.selection_authorized:
            self._block(
                "SELECTION_NOT_AUTHORIZED",
                "Trial selection is a goal but explicit authorization is absent",
            )
            return None
        usable = quality["data"]["condition_counts_quality_usable"]
        missing = [label for label in self.labels if usable.get(label, 0) < 1]
        if missing:
            self._block(
                "NO_USABLE_EPOCHS_FOR_CONDITION",
                "At least one requested condition has no quality-usable Epoch",
                labels=missing,
            )
            return None
        source = self._source_binding()
        if quality["data"]["epoch_counts"]["quality_flagged"] == 0:
            self._materialize_evidence(
                "trial_selection", input_binding=source, output_binding=source,
                mode="identity", arguments={"selection_authorized": True},
            )
            self._record_transition(
                "goal_satisfied_without_tool", goal="trial_selection",
                reason="quality evidence flagged zero Epochs",
                artifact_id=source.artifact_id,
            )
            return "resolved"
        return None

    def _action_arguments(self, goal):
        if goal == "observe_events":
            return {}
        if goal == "create_epochs":
            return dict(self.epoch_arguments)
        binding = self._input_binding(goal)
        arguments = {
            "artifact_id": binding.artifact_id,
            "expected_artifact_fingerprint": binding.fingerprint,
        }
        if goal == "trial_selection":
            arguments["expected_quality_evidence_id"] = self._quality_result()[
                "data"
            ]["evidence_id"]
        return arguments

    def next_action(self):
        self._begin_frontier_snapshot()
        self._reconcile()
        if self.blocked:
            return None
        while True:
            ready = [
                goal for goal in self.active_goals
                if goal not in self.evidence
                and all(dependency in self.evidence for dependency in self.dependencies[goal])
            ]
            if not ready:
                return None
            goal = ready[0]
            if self._restore_cached_consumer(goal):
                continue
            if goal == "trial_selection":
                if self._resolve_selection() == "resolved":
                    continue
                if self.blocked:
                    return None
            contract = self.contracts[goal]
            return ResidualAction(
                goal, contract.tool_name, self._action_arguments(goal),
                f"satisfy residual goal {goal} from declared contract",
            )

    def _request_id(self, action):
        self.attempts[action.kind] += 1
        return f"v11-{action.kind}-a{self.attempts[action.kind]}"

    def apply_result(self, action, rendered):
        goal = action.kind
        if not rendered["success"]:
            code = rendered["error"]["code"]
            if code in self.RETRYABLE_CODES and self.attempts[goal] <= self.max_retries:
                self.retries += 1
                self._record_transition(
                    "frontier_retry", goal=goal, error_code=code,
                    preserved_goals=sorted(self.evidence),
                )
                return
            if code in self.STATE_CONFLICT_CODES and self.repairs < self.max_repairs:
                self.repairs += 1
                self._record_transition(
                    "state_conflict_reconcile", goal=goal, error_code=code,
                    repair=self.repairs,
                )
                return
            self._block(
                "ACTION_FAILED", "Residual frontier action failed",
                goal=goal, error_code=code,
            )
            return
        input_binding = self._input_binding(goal)
        output_binding = None
        mode = None
        if (
            self.contracts[goal].role in {"producer", "transition"}
            and isinstance(rendered.get("data"), dict)
            and "artifact_id" in rendered["data"]
        ):
            output_binding = ArtifactBinding(
                rendered["data"]["artifact_id"],
                rendered["data"]["artifact_fingerprint"],
            )
        if self.contracts[goal].role == "transition":
            mode = "derived" if goal == "trial_selection" else goal
        self._materialize_evidence(
            goal,
            request_id=rendered["request_id"],
            result=rendered,
            input_binding=input_binding,
            output_binding=output_binding,
            mode=mode,
            arguments=action.arguments,
        )

    def _goal_status(self):
        return {
            goal: {
                "status": (
                    "blocked" if self.blocked and goal not in self.evidence else
                    "satisfied" if goal in self.evidence else "pending"
                ),
                "evidence": None if goal not in self.evidence else self.evidence[goal].token_id,
            }
            for goal in self.requested_goals
        }

    def _required_answer_tools(self):
        required = []
        if "epoch_quality" in self.requested_goals or "trial_selection" in self.requested_goals:
            required.append("epoch_quality")
        if self._selection_mode() == "derived":
            required.append("select_quality_epochs")
        for goal in ("epoch_summary", "event_bandpower"):
            if goal in self.requested_goals:
                required.append(self.contracts[goal].tool_name)
        return tuple(required)

    def state_dict(self):
        source = self._source_binding()
        effective = self._effective_binding()
        quality = self._quality_result()
        return {
            "context_id": self.context.task_id,
            "profile_id": self.context.profile.profile_id,
            "immutable_task": {
                "labels": list(self.labels),
                "tmin": self.epoch_arguments["tmin"],
                "tmax": self.epoch_arguments["tmax"],
                "objectives": list(self.requested_goals),
                "selection_authorized": self.selection_authorized,
            },
            "graph": {
                "active_goals": list(self.active_goals),
                "dependencies": {
                    goal: list(dependencies) for goal, dependencies in self.dependencies.items()
                },
                "evidence": {
                    goal: token.to_dict() for goal, token in self.evidence.items()
                },
            },
            "artifacts": {
                "created": None if source is None else source.artifact_id,
                "created_fingerprint": None if source is None else source.fingerprint,
                "selected": (
                    effective.artifact_id
                    if effective is not None and self._selection_mode() == "derived" else None
                ),
                "selected_fingerprint": (
                    effective.fingerprint
                    if effective is not None and self._selection_mode() == "derived" else None
                ),
                "effective": None if effective is None else effective.artifact_id,
                "effective_fingerprint": None if effective is None else effective.fingerprint,
            },
            "quality": None if quality is None else {
                "request_id": quality["request_id"],
                "evidence_id": quality["data"]["evidence_id"],
                "artifact_id": quality["data"]["artifact_id"],
                "artifact_fingerprint": quality["data"]["artifact_fingerprint"],
                "epoch_counts": dict(quality["data"]["epoch_counts"]),
                "condition_counts_quality_usable": dict(
                    quality["data"]["condition_counts_quality_usable"]
                ),
                "threshold_status": quality["data"]["threshold_status"],
            },
            "selection_mode": self._selection_mode(),
            "goals": self._goal_status(),
            "attempts": dict(self.attempts),
            "retries": self.retries,
            "repairs": self.repairs,
            "blocked": self.blocked,
        }

    def _evidence_check(self, status):
        successful = [item["tool_name"] for item in self.results if item["success"]]
        violations = []
        for forbidden in self.ledger.forbidden_tools:
            if forbidden in successful:
                violations.append(f"forbidden_tool_executed:{forbidden}")
        for name in self._required_answer_tools():
            if name not in successful:
                violations.append(f"missing_successful_tool:{name}")
        for goal in self.requested_goals:
            if goal not in self.evidence:
                violations.append(f"goal_not_satisfied:{goal}")
        effective = self._effective_binding()
        for goal in self.requested_goals:
            token = self.evidence.get(goal)
            if (
                token is not None
                and self.contracts[goal].input_policy == "effective_epochs"
                and token.input_binding != effective
            ):
                violations.append(f"effective_artifact_mismatch:{goal}")
        return {
            "closed": status == "completed" and not violations,
            "violations": violations,
            "successful_tools": successful,
            "selection_mode": self._selection_mode(),
            "effective_artifact_id": None if effective is None else effective.artifact_id,
            "effective_artifact_fingerprint": (
                None if effective is None else effective.fingerprint
            ),
            "termination_status": status,
            "goal_status": self._goal_status(),
        }

    def run(self, initial_plan, initial_check):
        started = time.perf_counter()
        trace = [
            {"event": "static_preflight_reused", "status": initial_plan.status},
            {"event": "obligations_checked", **dict(initial_check)},
            {
                "event": "goal_contract_graph_compiled",
                "active_goals": list(self.active_goals),
                "dependencies": {
                    goal: list(value) for goal, value in self.dependencies.items()
                },
            },
        ]
        transition_cursor = 0
        if initial_plan.status != "ready" or not initial_check.get("valid", False):
            self.context.trace.finish("v11_preflight_rejected")
            evidence = self._evidence_check("rejected")
            return DynamicPlanningRunResult(
                "rejected", initial_plan.to_dict(), (), tuple(trace),
                self.context.trace.to_dict(), 0,
                round((time.perf_counter() - started) * 1000, 3),
                self.state_dict(), evidence, (),
            )
        while len(self.results) < self.max_tool_calls:
            action = self.next_action()
            trace.extend(self.transitions[transition_cursor:])
            transition_cursor = len(self.transitions)
            if action is None:
                break
            request_id = self._request_id(action)
            trace.append({
                "event": "contract_frontier_planned",
                "request_id": request_id,
                **action.to_dict(),
                "state_before": self.state_dict(),
            })
            result = self.context.execute(ToolRequest(
                action.tool_name, action.arguments, request_id=request_id,
            ))
            rendered = result.to_dict()
            self.results.append(rendered)
            self.apply_result(action, rendered)
            trace.extend(self.transitions[transition_cursor:])
            transition_cursor = len(self.transitions)
            trace.append({
                "event": "contract_frontier_executed",
                "request_id": request_id,
                "goal": action.kind,
                "success": result.success,
                "error_code": result.error_code,
            })
        goals = self._goal_status()
        completed = bool(goals) and all(
            item["status"] == "satisfied" for item in goals.values()
        )
        if self.blocked:
            status, reason = "scientifically_blocked", "v11_scientific_stop"
        elif completed:
            status, reason = "completed", "v11_completed"
        else:
            status, reason = "execution_failed", "v11_budget_or_incomplete"
            if len(self.results) >= self.max_tool_calls:
                self._block("TOOL_CALL_LIMIT", "Contract planner reached its tool-call limit")
        evidence = self._evidence_check(status)
        self.context.trace.finish(reason)
        return DynamicPlanningRunResult(
            status, initial_plan.to_dict(), tuple(self.results), tuple(trace),
            self.context.trace.to_dict(), self.retries + self.repairs,
            round((time.perf_counter() - started) * 1000, 3),
            self.state_dict(), evidence, self._required_answer_tools(),
            self._release_results(),
        )


class ConstraintCarryingEEGAgentV11(ConstraintCarryingEEGAgentV1):
    """Opt-in v1.1 Agent using the contract-indexed evidence graph."""

    runner_class = ContractGraphResidualPlanner
    method_name = "constraint_carrying_eeg_plan_v11_ciedg"

    def __init__(
        self, llm_client, context, max_retries=1, max_repairs=2, max_tool_calls=16,
    ):
        super().__init__(llm_client, context, max_retries, max_tool_calls)
        self.max_repairs = max_repairs

    def run(self, user_request):
        interpretation = self.interpreter.interpret(user_request, self.context)
        if not interpretation.success:
            return self._stop(
                "intent_error", interpretation,
                "无法可靠解析 EEG 分析意图；未执行任何工具。",
            )
        if interpretation.disposition == "clarify":
            slots = "、".join(interpretation.missing_slots)
            return self._stop(
                "clarification_required", interpretation,
                f"需要补充或明确以下科学参数：{slots}。在此之前不会猜测或执行分析。",
            )
        if interpretation.disposition == "reject":
            return self._stop(
                "unsupported_or_unobservable", interpretation,
                interpretation.error_message or "当前记录或工具不支持该请求。",
            )
        task, ledger = compile_intent(interpretation.intent, self.context)
        if task.goal != "event_workflow":
            plan = StateAwareConstrainedPlanner(self.context).plan(task)
            plan_check = validate_plan_against_ledger(plan, ledger)
            if not plan_check["valid"]:
                self.context.trace.finish("plan_rejected")
                return Point1RunResult(
                    "plan_rejected", interpretation.to_dict(), ledger.to_dict(),
                    plan_check, final_answer="科学约束或当前 EEG 状态不允许执行该计划。",
                    llm=self._llm_summary(),
                    method=self.method_name,
                )
            execution = ConstrainedPlanRunner(
                self.context, max_replans=0,
                plan_validator=lambda candidate: validate_plan_against_ledger(
                    candidate, ledger
                ),
            ).execute_plan(task, plan)
            evidence = close_ledger(ledger, execution)
            answer, answer_check = self._answer(
                user_request, interpretation, ledger, execution, evidence,
            )
            reason = (
                "safe_stop_without_evidence" if not evidence["closed"] else
                "completed_without_llm_answer" if not answer_check["valid"] else
                "completed"
            )
            return Point1RunResult(
                reason, interpretation.to_dict(), ledger.to_dict(), plan_check,
                execution.to_dict(), evidence, answer_check=answer_check,
                final_answer=answer, llm=self._llm_summary(),
                method=self.method_name,
            )
        initial_plan = StateAwareConstrainedPlanner(self.context).plan(task)
        initial_check = validate_plan_against_ledger(initial_plan, ledger)
        runner = self.runner_class(
            self.context, task, ledger,
            max_retries=self.max_retries,
            max_repairs=self.max_repairs,
            max_tool_calls=self.max_tool_calls,
        )
        execution = runner.run(initial_plan, initial_check)
        evidence = execution.evidence_check
        if evidence["closed"]:
            answer, answer_check = self._answer(
                user_request, interpretation, ledger, execution, evidence,
                required_tools=execution.required_answer_tools,
                runtime_facts={
                    "selection_mode": execution.scientific_state.get("selection_mode"),
                    "goal_status": execution.scientific_state.get("goals"),
                    "effective_artifact_fingerprint": evidence.get(
                        "effective_artifact_fingerprint"
                    ),
                },
            )
            if answer_check["valid"]:
                answer = self._append_runtime_disclosure(answer, execution)
            reason = "completed" if answer_check["valid"] else "completed_without_llm_answer"
        else:
            answer = "动态科学状态无法满足全部剩余目标；未发布不完整分析。"
            answer_check = {
                "valid": False,
                "code": "RESIDUAL_GOALS_UNSATISFIED",
                "required_tools": list(execution.required_answer_tools),
            }
            reason = "safe_stop_without_evidence"
        return Point1RunResult(
            reason, interpretation.to_dict(), ledger.to_dict(), initial_check,
            execution.to_dict(), evidence, answer_check=answer_check,
            final_answer=answer, llm=self._llm_summary(),
            method=self.method_name,
        )
