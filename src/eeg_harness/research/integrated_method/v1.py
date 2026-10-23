"""CCEP v1: lineage-aware residual scientific planning.

The LLM freezes intent once.  This module then advances one deterministic EEG
state transition at a time through the existing ExecutionContext/Executor.
"""

from collections import Counter
from dataclasses import dataclass
import json
import time

from ...planning import ConstrainedPlanRunner, StateAwareConstrainedPlanner
from ...tooling import ToolRequest
from .agent import ConstraintCarryingEEGAgent, Point1RunResult
from .contracts import close_ledger, compile_intent, validate_plan_against_ledger


@dataclass(frozen=True)
class ResidualAction:
    kind: str
    tool_name: str
    arguments: dict
    purpose: str

    def to_dict(self):
        return {
            "kind": self.kind,
            "tool_name": self.tool_name,
            "arguments": dict(self.arguments),
            "purpose": self.purpose,
        }


@dataclass(frozen=True)
class DynamicPlanningRunResult:
    status: str
    plan: dict
    tool_results: tuple[dict, ...]
    planning_trace: tuple[dict, ...]
    execution_trace: dict
    replans: int
    duration_ms: float
    scientific_state: dict
    evidence_check: dict
    required_answer_tools: tuple[str, ...]

    def to_dict(self):
        payload = {
            "status": self.status,
            "plan": dict(self.plan),
            "tool_results": [dict(item) for item in self.tool_results],
            "planning_trace": [dict(item) for item in self.planning_trace],
            "execution_trace": dict(self.execution_trace),
            "replans": self.replans,
            "duration_ms": self.duration_ms,
            "scientific_state": dict(self.scientific_state),
            "evidence_check": dict(self.evidence_check),
            "required_answer_tools": list(self.required_answer_tools),
        }
        json.dumps(payload, ensure_ascii=False, allow_nan=False)
        return payload


class ResidualScientificPlanner:
    """Choose the next legal action from observed EEG state and residual goals."""

    RETRYABLE_CODES = frozenset({"INJECTED_TRANSIENT_FAILURE", "TEMPORARY_TOOL_FAILURE"})

    def __init__(self, context, task, ledger, max_retries=1, max_tool_calls=12):
        if task.goal != "event_workflow":
            raise ValueError("CCEP v1 residual planning currently supports event_workflow")
        self.context = context
        self.task = task
        self.ledger = ledger
        self.max_retries = int(max_retries)
        self.max_tool_calls = int(max_tool_calls)
        self.objectives = tuple(task.arguments.get("objectives", ()))
        self.labels = tuple(task.arguments.get("labels", ()))
        self.epoch_arguments = {
            "labels": list(self.labels),
            "tmin": task.arguments.get("tmin"),
            "tmax": task.arguments.get("tmax"),
        }
        if "baseline" in task.arguments:
            self.epoch_arguments["baseline"] = list(task.arguments["baseline"])
        self.selection_authorized = task.arguments.get("selection_authorized") is True
        self.results = []
        self.transitions = []
        self.attempts = Counter()
        self.retries = 0
        self.event_result = None
        self.created_artifact_id = None
        self.quality_result = None
        self.selected_artifact_id = None
        self.selection_mode = None
        self.bandpower_result = None
        self.blocked = None

    def _artifact_exists(self, artifact_id):
        return bool(artifact_id) and artifact_id in self.context.artifacts

    def _record_transition(self, event, **details):
        self.transitions.append({"event": event, **details})

    def _invalidate_missing_artifacts(self):
        if self.created_artifact_id and not self._artifact_exists(self.created_artifact_id):
            missing = self.created_artifact_id
            self.created_artifact_id = None
            self.quality_result = None
            self.selected_artifact_id = None
            self.selection_mode = None
            self.bandpower_result = None
            self._record_transition(
                "lineage_invalidated", artifact_id=missing,
                reason="source_artifact_missing", invalidated=(
                    "epoch_quality", "trial_selection", "event_bandpower",
                ),
            )
        elif self.selected_artifact_id and not self._artifact_exists(self.selected_artifact_id):
            missing = self.selected_artifact_id
            self.selected_artifact_id = None
            self.selection_mode = None
            self.bandpower_result = None
            self._record_transition(
                "lineage_invalidated", artifact_id=missing,
                reason="derived_artifact_missing",
                invalidated=("trial_selection", "event_bandpower"),
            )

    def _quality_counts(self):
        if self.quality_result is None:
            return None
        return self.quality_result["data"]["epoch_counts"]

    def _quality_usable_by_label(self):
        if self.quality_result is None:
            return {}
        return self.quality_result["data"]["condition_counts_quality_usable"]

    def _effective_artifact_id(self):
        return self.selected_artifact_id or self.created_artifact_id

    def _goal_status(self):
        status = {}
        for objective in self.objectives:
            if objective == "epoch_quality":
                satisfied = self.quality_result is not None
                evidence = None if not satisfied else self.quality_result["request_id"]
            elif objective == "trial_selection":
                satisfied = self.selection_mode in {"identity", "derived"}
                evidence = self.selection_mode
            elif objective == "event_bandpower":
                satisfied = self.bandpower_result is not None
                evidence = None if not satisfied else self.bandpower_result["request_id"]
            else:
                satisfied, evidence = False, None
            status[objective] = {
                "status": "blocked" if self.blocked and not satisfied else (
                    "satisfied" if satisfied else "pending"
                ),
                "evidence": evidence,
            }
        return status

    def state_dict(self):
        quality = None
        if self.quality_result is not None:
            quality = {
                "request_id": self.quality_result["request_id"],
                "evidence_id": self.quality_result["data"]["evidence_id"],
                "artifact_id": self.quality_result["data"]["artifact_id"],
                "epoch_counts": dict(self._quality_counts()),
                "condition_counts_quality_usable": dict(self._quality_usable_by_label()),
                "threshold_status": self.quality_result["data"]["threshold_status"],
            }
        return {
            "context_id": self.context.task_id,
            "profile_id": self.context.profile.profile_id,
            "immutable_task": {
                "labels": list(self.labels),
                "tmin": self.epoch_arguments["tmin"],
                "tmax": self.epoch_arguments["tmax"],
                "objectives": list(self.objectives),
                "selection_authorized": self.selection_authorized,
            },
            "artifacts": {
                "created": self.created_artifact_id,
                "selected": self.selected_artifact_id,
                "effective": self._effective_artifact_id(),
            },
            "quality": quality,
            "selection_mode": self.selection_mode,
            "goals": self._goal_status(),
            "attempts": dict(self.attempts),
            "blocked": self.blocked,
        }

    def _block(self, code, message, **details):
        self.blocked = {"code": code, "message": message, **details}
        self._record_transition("scientific_stop", **self.blocked)

    def next_action(self):
        self._invalidate_missing_artifacts()
        if self.blocked:
            return None
        if self.event_result is None:
            return ResidualAction(
                "observe_events", "list_events", {}, "observe actual event state",
            )
        if self.created_artifact_id is None:
            return ResidualAction(
                "create_epochs", "create_epochs", dict(self.epoch_arguments),
                "create the shared Epoch artifact once",
            )
        quality_needed = (
            "epoch_quality" in self.objectives or "trial_selection" in self.objectives
        )
        if quality_needed and self.quality_result is None:
            return ResidualAction(
                "measure_quality", "epoch_quality",
                {"artifact_id": self.created_artifact_id},
                "observe quality before deciding the residual selection branch",
            )
        if "trial_selection" in self.objectives and self.selection_mode is None:
            if not self.selection_authorized:
                self._block(
                    "SELECTION_NOT_AUTHORIZED",
                    "Trial selection is a goal but explicit authorization is absent",
                )
                return None
            counts = self._quality_counts()
            usable = self._quality_usable_by_label()
            missing_conditions = [label for label in self.labels if usable.get(label, 0) < 1]
            if missing_conditions:
                self._block(
                    "NO_USABLE_EPOCHS_FOR_CONDITION",
                    "At least one requested condition has no quality-usable Epoch",
                    labels=missing_conditions,
                )
                return None
            if counts["quality_flagged"] == 0:
                self.selection_mode = "identity"
                self._record_transition(
                    "goal_satisfied_without_tool", goal="trial_selection",
                    reason="quality evidence flagged zero Epochs",
                    artifact_id=self.created_artifact_id,
                )
                return self.next_action()
            return ResidualAction(
                "select_quality", "select_quality_epochs",
                {"artifact_id": self.created_artifact_id},
                "materialize an authorized derived artifact because quality flagged Epochs",
            )
        if "event_bandpower" in self.objectives and self.bandpower_result is None:
            return ResidualAction(
                "event_bandpower", "event_bandpower",
                {"artifact_id": self._effective_artifact_id()},
                "analyse the current effective artifact after dynamic branch resolution",
            )
        return None

    def _request_id(self, action):
        self.attempts[action.kind] += 1
        return f"v1-{action.kind}-a{self.attempts[action.kind]}"

    def apply_result(self, action, rendered):
        if not rendered["success"]:
            code = rendered["error"]["code"]
            if code in self.RETRYABLE_CODES and self.attempts[action.kind] <= self.max_retries:
                self.retries += 1
                self._record_transition(
                    "frontier_retry", action=action.kind, error_code=code,
                    preserved_goals=[
                        key for key, value in self._goal_status().items()
                        if value["status"] == "satisfied"
                    ],
                )
                return
            self._block(
                "ACTION_FAILED", "Residual frontier action failed",
                action=action.kind, error_code=code,
            )
            return
        if action.kind == "observe_events":
            self.event_result = rendered
        elif action.kind == "create_epochs":
            self.created_artifact_id = rendered["data"]["artifact_id"]
        elif action.kind == "measure_quality":
            self.quality_result = rendered
        elif action.kind == "select_quality":
            self.selected_artifact_id = rendered["data"]["artifact_id"]
            self.selection_mode = "derived"
        elif action.kind == "event_bandpower":
            self.bandpower_result = rendered

    def _required_answer_tools(self):
        required = []
        if "epoch_quality" in self.objectives or "trial_selection" in self.objectives:
            required.append("epoch_quality")
        if self.selection_mode == "derived":
            required.append("select_quality_epochs")
        if "event_bandpower" in self.objectives:
            required.append("event_bandpower")
        return tuple(required)

    def _evidence_check(self, status):
        successful = [item["tool_name"] for item in self.results if item["success"]]
        violations = []
        for forbidden in self.ledger.forbidden_tools:
            if forbidden in successful:
                violations.append(f"forbidden_tool_executed:{forbidden}")
        for name in self._required_answer_tools():
            if name not in successful:
                violations.append(f"missing_successful_tool:{name}")
        if "trial_selection" in self.objectives and self.selection_mode is None:
            violations.append("trial_selection_goal_not_satisfied")
        effective = self._effective_artifact_id()
        if self.bandpower_result is not None and (
            self.bandpower_result["data"].get("artifact_id") != effective
        ):
            violations.append("artifact_lineage_mismatch")
        return {
            "closed": status == "completed" and not violations,
            "violations": violations,
            "successful_tools": successful,
            "selection_mode": self.selection_mode,
            "effective_artifact_id": effective,
            "termination_status": status,
            "goal_status": self._goal_status(),
        }

    def run(self, initial_plan, initial_check):
        started = time.perf_counter()
        trace = [
            {"event": "v0_preflight_reused", "status": initial_plan.status},
            {"event": "obligations_checked", **dict(initial_check)},
        ]
        transition_cursor = 0
        if initial_plan.status != "ready" or not initial_check.get("valid", False):
            self.context.trace.finish("v1_preflight_rejected")
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
                "event": "residual_frontier_planned", "request_id": request_id,
                **action.to_dict(), "state_before": self.state_dict(),
            })
            result = self.context.execute(
                ToolRequest(action.tool_name, action.arguments, request_id=request_id)
            )
            rendered = result.to_dict()
            self.results.append(rendered)
            self.apply_result(action, rendered)
            trace.extend(self.transitions[transition_cursor:])
            transition_cursor = len(self.transitions)
            trace.append({
                "event": "residual_frontier_executed", "request_id": request_id,
                "kind": action.kind, "success": result.success,
                "error_code": result.error_code,
            })
        goals = self._goal_status()
        all_satisfied = bool(goals) and all(
            item["status"] == "satisfied" for item in goals.values()
        )
        if self.blocked:
            status, reason = "scientifically_blocked", "v1_scientific_stop"
        elif all_satisfied:
            status, reason = "completed", "v1_completed"
        else:
            status, reason = "execution_failed", "v1_budget_or_incomplete"
            if len(self.results) >= self.max_tool_calls:
                self._block("TOOL_CALL_LIMIT", "Residual planner reached its tool-call limit")
        evidence = self._evidence_check(status)
        self.context.trace.finish(reason)
        return DynamicPlanningRunResult(
            status, initial_plan.to_dict(), tuple(self.results), tuple(trace),
            self.context.trace.to_dict(), self.retries,
            round((time.perf_counter() - started) * 1000, 3),
            self.state_dict(), evidence, self._required_answer_tools(),
        )


class ConstraintCarryingEEGAgentV1(ConstraintCarryingEEGAgent):
    """Opt-in natural-language CCEP v1 Agent; v0 remains unchanged."""

    def __init__(self, llm_client, context, max_retries=1, max_tool_calls=12):
        super().__init__(llm_client, context, max_replans=0)
        self.max_retries = max_retries
        self.max_tool_calls = max_tool_calls

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
            # v1 only changes dynamic event workflows; other supported tasks retain v0.
            plan = StateAwareConstrainedPlanner(self.context).plan(task)
            plan_check = validate_plan_against_ledger(plan, ledger)
            if not plan_check["valid"]:
                self.context.trace.finish("plan_rejected")
                return Point1RunResult(
                    "plan_rejected", interpretation.to_dict(), ledger.to_dict(),
                    plan_check, final_answer="科学约束或当前 EEG 状态不允许执行该计划。",
                    llm=self._llm_summary(), method="constraint_carrying_eeg_plan_v1_lrsp",
                )
            execution = ConstrainedPlanRunner(
                self.context, max_replans=0,
                plan_validator=lambda candidate: validate_plan_against_ledger(candidate, ledger),
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
                method="constraint_carrying_eeg_plan_v1_lrsp",
            )
        initial_plan = StateAwareConstrainedPlanner(self.context).plan(task)
        initial_check = validate_plan_against_ledger(initial_plan, ledger)
        runner = ResidualScientificPlanner(
            self.context, task, ledger,
            max_retries=self.max_retries, max_tool_calls=self.max_tool_calls,
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
                },
            )
            reason = "completed" if answer_check["valid"] else "completed_without_llm_answer"
        else:
            answer = (
                "动态科学状态无法满足全部剩余目标；未发布不完整分析。"
            )
            answer_check = {
                "valid": False, "code": "RESIDUAL_GOALS_UNSATISFIED",
                "required_tools": list(execution.required_answer_tools),
            }
            reason = "safe_stop_without_evidence"
        return Point1RunResult(
            reason, interpretation.to_dict(), ledger.to_dict(), initial_check,
            execution.to_dict(), evidence, answer_check=answer_check,
            final_answer=answer, llm=self._llm_summary(),
            method="constraint_carrying_eeg_plan_v1_lrsp",
        )
