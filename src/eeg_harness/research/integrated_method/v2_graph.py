"""Task-neutral evidence graph runtime for the opt-in multi-task research version.

The frozen event-specific v1.1 runner remains unchanged. This runtime shares one
frontier, version reconciliation, bounded failure policy, and evidence gate across
record, event and model goals. EEG operations still run only through Context/Executor.
"""

from collections import Counter
from copy import deepcopy
import time

from ...tooling import ToolRequest
from .v1 import DynamicPlanningRunResult, ResidualAction
from .v11 import ArtifactBinding, GoalEvidence, _stable_token


class SharedEvidenceGraphCore:
    RETRYABLE_CODES = frozenset({"INJECTED_TRANSIENT_FAILURE", "TEMPORARY_TOOL_FAILURE"})
    STATE_CONFLICT_CODES = frozenset({"ARTIFACT_NOT_FOUND", "ARTIFACT_STATE_CONFLICT"})

    def __init__(self, context, task, ledger, contracts, *, max_retries=1,
                 max_repairs=2, max_tool_calls=16):
        self.context, self.task, self.ledger = context, task, ledger
        self.contracts = dict(contracts)
        self.requested_goals = tuple(task.arguments["objectives"])
        self.dependencies = self._compile_dependencies()
        self.active_goals = tuple(sorted(
            self.dependencies, key=lambda name: (self.contracts[name].priority, name),
        ))
        self.max_retries = int(max_retries)
        self.max_repairs = int(max_repairs)
        self.max_tool_calls = int(max_tool_calls)
        self.evidence = {}
        self.evidence_cache = {}
        self.results = []
        self.transitions = []
        self.attempts = Counter()
        self.retries = self.repairs = 0
        self.blocked = None
        self._fingerprints = {}

    def _dependencies_for(self, goal):
        return self.contracts[goal].base_dependencies

    def _compile_dependencies(self):
        dependencies = {}

        def add(goal):
            if goal in dependencies:
                return
            dependencies[goal] = tuple(dict.fromkeys(self._dependencies_for(goal)))
            for dependency in dependencies[goal]:
                add(dependency)

        for goal in self.requested_goals:
            add(goal)
        return dependencies

    def _record_transition(self, event, **details):
        self.transitions.append({"event": event, **details})

    def _block(self, code, message, **details):
        self.blocked = {"code": code, "message": message, **details}
        self._record_transition("scientific_stop", **self.blocked)

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
        return binding is None or self._artifact_fingerprint(binding.artifact_id) == binding.fingerprint

    def _input_binding(self, goal):
        raise NotImplementedError

    def _action_arguments(self, goal):
        raise NotImplementedError

    def _resolve_without_tool(self, goal):
        return False

    def _output_mode(self, goal):
        return "derived" if self.contracts[goal].role == "transition" else None

    def _extra_state(self):
        return {}

    def _dependency_tokens(self, goal):
        return tuple((dependency, self.evidence[dependency].token_id)
                     for dependency in self.dependencies[goal])

    def _evidence_payload(self, goal, *, arguments, input_binding, output_binding,
                          mode, semantic=False):
        if semantic:
            arguments = {key: value for key, value in dict(arguments or {}).items()
                         if key not in {"artifact_id", "expected_artifact_fingerprint",
                                        "expected_quality_evidence_id"}}
            bind = lambda item: None if item is None else {"fingerprint": item.fingerprint}
            dependencies = {name: self.evidence[name].semantic_id
                            for name in self.dependencies[goal]}
        else:
            arguments = dict(arguments or {})
            bind = lambda item: None if item is None else item.to_dict()
            dependencies = dict(self._dependency_tokens(goal))
        return {"goal": goal, "arguments": arguments, "input": bind(input_binding),
                "output": bind(output_binding), "dependencies": dependencies, "mode": mode}

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
                if any(dependency in invalid or dependency not in self.evidence
                       or self.evidence[dependency].token_id != expected.get(dependency)
                       for dependency in self.dependencies[goal]):
                    invalid.add(goal)
                    reasons[goal] = "dependency_evidence_invalidated"
                    changed = True
        if invalid:
            ordered = sorted(invalid, key=lambda name: (self.contracts[name].priority, name))
            for goal in ordered:
                token = self.evidence.pop(goal, None)
                if token is not None and self.contracts[goal].role == "consumer":
                    self.evidence_cache.setdefault(goal, {})[token.semantic_id] = token
            self._record_transition("evidence_graph_invalidated", goals=ordered,
                                    reasons={goal: reasons[goal] for goal in ordered})

    def _materialize_evidence(self, goal, *, request_id=None, result=None,
                              input_binding=None, output_binding=None, mode=None,
                              arguments=None):
        payload = self._evidence_payload(
            goal, arguments=arguments, input_binding=input_binding,
            output_binding=output_binding, mode=mode,
        )
        semantic = self._evidence_payload(
            goal, arguments=arguments, input_binding=input_binding,
            output_binding=output_binding, mode=mode, semantic=True,
        )
        token = GoalEvidence(
            goal=goal, token_id=_stable_token(payload), semantic_id=_stable_token(semantic),
            tool_name=self.contracts[goal].tool_name if request_id else None,
            request_id=request_id, dependency_tokens=self._dependency_tokens(goal),
            input_binding=input_binding, output_binding=output_binding,
            mode=mode, result=result,
        )
        self.evidence[goal] = token
        return token

    def _restore_cached_consumer(self, goal):
        if self.contracts[goal].role != "consumer":
            return False
        input_binding = self._input_binding(goal)
        arguments = self._action_arguments(goal)
        semantic = self._evidence_payload(
            goal, arguments=arguments, input_binding=input_binding,
            output_binding=None, mode=None, semantic=True,
        )
        semantic_id = _stable_token(semantic)
        cached = self.evidence_cache.get(goal, {}).get(semantic_id)
        if cached is None:
            return False
        payload = self._evidence_payload(
            goal, arguments=arguments, input_binding=input_binding,
            output_binding=None, mode=None,
        )
        released = deepcopy(cached.result)
        request_id = f"reuse-{goal}-{semantic_id.removeprefix('goal-token:')[:12]}"
        released["request_id"] = request_id
        released["execution_kind"] = "semantic_evidence_reuse"
        released["reused_from_request_id"] = cached.request_id
        if isinstance(released.get("data"), dict) and input_binding is not None:
            if "artifact_id" in released["data"]:
                released["data"]["artifact_id"] = input_binding.artifact_id
            if "artifact_fingerprint" in released["data"]:
                released["data"]["artifact_fingerprint"] = input_binding.fingerprint
            released["data"]["evidence_reuse"] = {
                "source_request_id": cached.request_id,
                "current_artifact_id": input_binding.artifact_id,
                "current_artifact_fingerprint": input_binding.fingerprint,
                "scientific_content_equivalent": True,
            }
        self.evidence[goal] = GoalEvidence(
            goal=goal, token_id=_stable_token(payload), semantic_id=semantic_id,
            tool_name=cached.tool_name, request_id=request_id,
            dependency_tokens=self._dependency_tokens(goal), input_binding=input_binding,
            result=released,
        )
        self._record_transition("goal_evidence_reused", goal=goal,
                                cached_token_id=cached.token_id,
                                restored_token_id=self.evidence[goal].token_id,
                                semantic_id=semantic_id, release_request_id=request_id)
        return True

    def next_action(self):
        self._begin_frontier_snapshot()
        self._reconcile()
        if self.blocked:
            return None
        while True:
            ready = [goal for goal in self.active_goals if goal not in self.evidence
                     and all(dep in self.evidence for dep in self.dependencies[goal])]
            if not ready:
                return None
            goal = ready[0]
            if self._restore_cached_consumer(goal):
                continue
            if self._resolve_without_tool(goal):
                continue
            if self.blocked:
                return None
            contract = self.contracts[goal]
            return ResidualAction(goal, contract.tool_name,
                                  self._action_arguments(goal),
                                  f"satisfy residual goal {goal} from declared contract")

    def apply_result(self, action, rendered):
        goal = action.kind
        if not rendered["success"]:
            code = rendered["error"]["code"]
            if code in self.RETRYABLE_CODES and self.attempts[goal] <= self.max_retries:
                self.retries += 1
                self._record_transition("frontier_retry", goal=goal, error_code=code,
                                        preserved_goals=sorted(self.evidence))
                return
            if code in self.STATE_CONFLICT_CODES and self.repairs < self.max_repairs:
                self.repairs += 1
                self._record_transition("state_conflict_reconcile", goal=goal,
                                        error_code=code, repair=self.repairs)
                return
            self._block("ACTION_FAILED", "Residual frontier action failed",
                        goal=goal, error_code=code)
            return
        spec = self.context.executor.registry.get(action.tool_name)
        data = rendered.get("data")
        expected_type = None if spec is None else spec.return_type
        if ((expected_type == "object" and not isinstance(data, dict))
                or (expected_type == "array" and not isinstance(data, list))):
            self._block("TOOL_RESULT_TYPE_MISMATCH",
                        "Successful tool output violates its declared return type", goal=goal)
            return
        if spec is not None and spec.produces_artifact:
            artifact_id = data.get("artifact_id") if isinstance(data, dict) else None
            fingerprint = data.get("artifact_fingerprint") if isinstance(data, dict) else None
            if (not isinstance(artifact_id, str) or not isinstance(fingerprint, str)
                    or self._artifact_fingerprint(artifact_id) != fingerprint):
                self._block("ARTIFACT_OUTPUT_MISMATCH",
                            "Produced artifact is absent or differs from declared result", goal=goal)
                return
        binding = self._input_binding(goal)
        output = None
        if (self.contracts[goal].role in {"producer", "transition"}
                and isinstance(rendered.get("data"), dict)
                and "artifact_id" in rendered["data"]):
            output = ArtifactBinding(rendered["data"]["artifact_id"],
                                     rendered["data"]["artifact_fingerprint"])
        self._materialize_evidence(
            goal, request_id=rendered["request_id"], result=rendered,
            input_binding=binding, output_binding=output,
            mode=self._output_mode(goal), arguments=action.arguments,
        )

    def _goal_status(self):
        return {goal: {"status": ("satisfied" if goal in self.evidence else
                                 "blocked" if self.blocked else "pending"),
                       "evidence": None if goal not in self.evidence
                       else self.evidence[goal].token_id}
                for goal in self.requested_goals}

    def _required_answer_tools(self):
        return tuple(dict.fromkeys(
            token.tool_name for goal in self.active_goals
            if self.contracts[goal].answer_required
            for token in [self.evidence.get(goal)]
            if token is not None and token.result is not None and token.tool_name
        ))

    def _release_results(self):
        released = []
        seen = set()
        for goal in self.active_goals:
            token = self.evidence.get(goal)
            if (token is None or token.result is None
                    or not self.contracts[goal].answer_required
                    or token.result["request_id"] in seen):
                continue
            seen.add(token.result["request_id"])
            released.append(token.result)
        return tuple(released)

    def _evidence_check(self, status):
        successful = [item["tool_name"] for item in self.results if item["success"]]
        violations = [f"forbidden_tool_executed:{name}" for name in self.ledger.forbidden_tools
                      if name in successful]
        for goal in self.requested_goals:
            if goal not in self.evidence:
                violations.append(f"goal_not_satisfied:{goal}")
        for goal, token in self.evidence.items():
            if not self._binding_valid(token.input_binding):
                violations.append(f"stale_input_binding:{goal}")
            if not self._binding_valid(token.output_binding):
                violations.append(f"stale_output_binding:{goal}")
        for name in self._required_answer_tools():
            if name not in successful and not any(
                token.tool_name == name and token.result is not None
                and token.result.get("execution_kind") == "semantic_evidence_reuse"
                for token in self.evidence.values()
            ):
                violations.append(f"missing_successful_tool:{name}")
        return {"closed": status == "completed" and not violations,
                "violations": violations, "successful_tools": successful,
                "termination_status": status, "goal_status": self._goal_status()}

    def state_dict(self):
        return {"context_id": self.context.task_id,
                "profile_id": self.context.profile.profile_id,
                "immutable_task": dict(self.task.arguments),
                "graph": {"active_goals": list(self.active_goals),
                          "dependencies": {goal: list(deps) for goal, deps in self.dependencies.items()},
                          "evidence": {goal: token.to_dict() for goal, token in self.evidence.items()}},
                "goals": self._goal_status(), "attempts": dict(self.attempts),
                "retries": self.retries, "repairs": self.repairs,
                "blocked": self.blocked, **self._extra_state()}

    def run(self, initial_plan, initial_check):
        started = time.perf_counter()
        trace = [
            {"event": "static_preflight_reused", "status": initial_plan.status},
            {"event": "obligations_checked", **dict(initial_check)},
            {"event": "goal_contract_graph_compiled", "active_goals": list(self.active_goals),
             "dependencies": {goal: list(deps) for goal, deps in self.dependencies.items()}},
        ]
        cursor = 0
        if initial_plan.status != "ready" or not initial_check.get("valid", False):
            self.context.trace.finish("v2_preflight_rejected")
            return DynamicPlanningRunResult(
                "rejected", initial_plan.to_dict(), (), tuple(trace),
                self.context.trace.to_dict(), 0,
                round((time.perf_counter() - started) * 1000, 3),
                self.state_dict(), self._evidence_check("rejected"), (),
            )
        while len(self.results) < self.max_tool_calls:
            action = self.next_action()
            trace.extend(self.transitions[cursor:])
            cursor = len(self.transitions)
            if action is None:
                break
            self.attempts[action.kind] += 1
            request_id = f"v2-{action.kind}-a{self.attempts[action.kind]}"
            trace.append({"event": "contract_frontier_planned", "request_id": request_id,
                          **action.to_dict(), "state_before": self.state_dict()})
            result = self.context.execute(ToolRequest(
                action.tool_name, action.arguments, request_id=request_id,
            ))
            rendered = result.to_dict()
            self.results.append(rendered)
            self.apply_result(action, rendered)
            trace.extend(self.transitions[cursor:])
            cursor = len(self.transitions)
            trace.append({"event": "contract_frontier_executed", "request_id": request_id,
                          "goal": action.kind, "success": result.success,
                          "error_code": result.error_code})
        completed = bool(self.requested_goals) and all(
            item["status"] == "satisfied" for item in self._goal_status().values()
        )
        if self.blocked:
            status, reason = "scientifically_blocked", "v2_scientific_stop"
        elif completed:
            status, reason = "completed", "v2_completed"
        else:
            status, reason = "execution_failed", "v2_budget_or_incomplete"
            if len(self.results) >= self.max_tool_calls:
                self._block("TOOL_CALL_LIMIT", "Goal graph reached its tool-call limit")
        evidence = self._evidence_check(status)
        self.context.trace.finish(reason)
        return DynamicPlanningRunResult(
            status, initial_plan.to_dict(), tuple(self.results), tuple(trace),
            self.context.trace.to_dict(), self.retries + self.repairs,
            round((time.perf_counter() - started) * 1000, 3),
            self.state_dict(), evidence, self._required_answer_tools(),
            self._release_results(),
        )
