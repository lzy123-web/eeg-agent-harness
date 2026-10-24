"""Opt-in multi-task goal graph over the existing EEG Executor and frozen v1.1 graph core."""

from dataclasses import dataclass, field, replace
import hashlib
import json
from pathlib import Path
from typing import Mapping

import numpy as np

from ...planning import Plan, PlanStep, StateAwareConstrainedPlanner, TaskSpec
from .agent import Point1RunResult
from .contracts import Obligation, ObligationLedger, _forbidden_tools
from .intent import IntentSpec
from .v11 import ArtifactBinding, ConstraintCarryingEEGAgentV11, GOAL_CONTRACTS, GoalContract
from .v2_graph import SharedEvidenceGraphCore
from .v1 import DynamicPlanningRunResult


RECORD_GOALS = {
    "record_info": GoalContract("record_info", "record_info", "consumer", "record", (), 1, True),
    "record_quality": GoalContract("record_quality", "record_quality", "consumer", "record", (), 2, True),
    "amplitude": GoalContract("amplitude", "amplitude", "consumer", "record", (), 3, True),
    "psd": GoalContract("psd", "psd", "consumer", "record", (), 4, True),
    "seizure_detection": GoalContract(
        "seizure_detection", "seizure_detection", "consumer", "record_model", (), 5, True,
    ),
}
MULTITASK_CONTRACTS = {
    **GOAL_CONTRACTS,
    "observe_events": replace(GOAL_CONTRACTS["observe_events"], input_policy="record"),
    "create_epochs": replace(GOAL_CONTRACTS["create_epochs"], input_policy="record"),
    **RECORD_GOALS,
}
WINDOW_GOALS = frozenset({"amplitude", "psd", "seizure_detection"})
EVENT_GOALS = frozenset(GOAL_CONTRACTS)


@dataclass(frozen=True)
class MultiTaskRequest:
    """Explicit parsed scientific goals; no data-set or diagnosis semantics."""

    objectives: tuple[str, ...]
    goal_arguments: Mapping[str, Mapping] = field(default_factory=dict)
    event_arguments: Mapping = field(default_factory=dict)
    forbidden_operations: tuple[str, ...] = ()

    @classmethod
    def from_intent(cls, intent: IntentSpec):
        if intent.analysis_type == "event_workflow":
            return cls(tuple(intent.objectives), event_arguments=dict(intent.parameters),
                       forbidden_operations=tuple(intent.forbidden_operations))
        if intent.analysis_type in RECORD_GOALS:
            return cls((intent.analysis_type,),
                       goal_arguments={intent.analysis_type: dict(intent.parameters)},
                       forbidden_operations=tuple(intent.forbidden_operations))
        return cls((intent.analysis_type,), forbidden_operations=tuple(intent.forbidden_operations))


def _required_goals(objectives):
    active = {}

    def add(goal):
        if goal in active:
            return
        contract = MULTITASK_CONTRACTS[goal]
        dependencies = list(contract.base_dependencies)
        if contract.input_policy == "effective_epochs" and "trial_selection" in objectives:
            dependencies = [name for name in dependencies if name != "create_epochs"]
            dependencies.append("trial_selection")
        active[goal] = tuple(dict.fromkeys(dependencies))
        for dependency in active[goal]:
            add(dependency)

    for objective in objectives:
        add(objective)
    return tuple(sorted(active, key=lambda name: (MULTITASK_CONTRACTS[name].priority, name)))


def compile_multitask(context, request: MultiTaskRequest):
    """Preflight the entire goal set before any EEG tool call."""

    objectives = tuple(request.objectives)
    task = TaskSpec("multitask_workflow", {
        "objectives": list(objectives),
        "goal_arguments": {name: dict(values) for name, values in request.goal_arguments.items()},
        **dict(request.event_arguments),
    }, task_id=context.task_id)
    forbidden = _forbidden_tools(request.forbidden_operations)
    if not objectives or len(set(objectives)) != len(objectives):
        return _reject(context, task, "INVALID_OBJECTIVES", "Goals must be non-empty and unique", forbidden)
    unsupported = set(objectives) - set(MULTITASK_CONTRACTS)
    if unsupported:
        return _reject(context, task, "UNSUPPORTED_GOAL", "At least one goal is unsupported", forbidden)
    if any(goal in {"observe_events", "create_epochs"} for goal in objectives):
        return _reject(context, task, "UNSUPPORTED_GOAL", "Internal dependency goals cannot be requested", forbidden)
    if set(request.goal_arguments) - set(objectives):
        return _reject(context, task, "UNREQUESTED_PARAMETERS", "Arguments name an unrequested goal", forbidden)
    if request.event_arguments and not any(goal in EVENT_GOALS for goal in objectives):
        return _reject(context, task, "UNREQUESTED_PARAMETERS", "Event arguments require an event goal", forbidden)
    if "trial_selection" in objectives and request.event_arguments.get("selection_authorized") is not True:
        return _reject(context, task, "SELECTION_NOT_AUTHORIZED", "Trial selection requires explicit authorization", forbidden)
    if set(objectives) & {"epoch_rereference"}:
        return _reject(context, task, "UNSUPPORTED_GOAL", "This version does not combine Epoch rereferencing", forbidden)
    if any(goal in EVENT_GOALS for goal in objectives) and any(
        name in request.goal_arguments for name in EVENT_GOALS
    ):
        return _reject(context, task, "INVALID_PARAMETERS", "Event parameters must be shared explicitly", forbidden)
    active = _required_goals(objectives)
    expected_tools = [MULTITASK_CONTRACTS[name].tool_name for name in active]
    ledger = ObligationLedger(context.task_id, "multitask_workflow", (
        Obligation("objectives", "objectives", list(objectives)),
        Obligation("evidence", "successful_tools", expected_tools),
    ), forbidden)
    if set(expected_tools) & set(forbidden):
        return task, ledger, Plan(task.task_id, "rejected", reason_code="FORBIDDEN_OPERATION",
                                  reason="A required goal is explicitly forbidden"), {
            "valid": False, "code": "FORBIDDEN_OPERATION", "planned_tools": [],
        }
    # The goal graph is not an alternative tool registry: bind every goal's
    # input/output type and applicability to the same ToolSpec used by Executor.
    for goal in active:
        contract = MULTITASK_CONTRACTS[goal]
        spec = context.executor.registry.get(contract.tool_name)
        expected_input = "epochs" if contract.input_policy in {
            "source_epochs", "effective_epochs",
        } else None
        expected_output = "epochs" if contract.role in {"producer", "transition"} else None
        if (spec is None or spec.consumes_artifact != expected_input
                or spec.produces_artifact != expected_output):
            return _reject(context, task, "GOAL_TOOL_CONTRACT_MISMATCH",
                           "Goal input/output type disagrees with the registered tool", forbidden)
        if (("*" not in spec.compatible_profiles
             and context.profile.profile_id not in spec.compatible_profiles)
                or not context.profile.supports_tool(spec.name)):
            return _reject(context, task, "INCOMPATIBLE_PROFILE",
                           "Goal tool is not applicable to the current EEG Profile", forbidden)
    planner = StateAwareConstrainedPlanner(context)
    steps = []
    for goal in objectives:
        if goal not in RECORD_GOALS:
            continue
        parameters = dict(request.goal_arguments.get(goal, {}))
        subtask = TaskSpec("tool", {"tool_name": goal, "parameters": parameters},
                           task_id=f"{task.task_id}-{goal}")
        subplan = planner.plan(subtask)
        if subplan.status != "ready":
            return task, ledger, Plan(task.task_id, "rejected", reason_code=subplan.reason_code,
                                      reason=subplan.reason), {
                "valid": False, "code": subplan.reason_code, "planned_tools": [],
            }
        steps.extend(replace(step, step_id=f"{goal}-{step.step_id}") for step in subplan.steps)
    event_objectives = [goal for goal in objectives if goal in EVENT_GOALS]
    if event_objectives:
        subtask = TaskSpec("event_workflow", {
            **dict(request.event_arguments), "objectives": event_objectives,
        }, task_id=f"{task.task_id}-event")
        subplan = planner.plan(subtask)
        if subplan.status != "ready":
            return task, ledger, Plan(task.task_id, "rejected", reason_code=subplan.reason_code,
                                      reason=subplan.reason), {
                "valid": False, "code": subplan.reason_code, "planned_tools": [],
            }
        steps.extend(replace(step, step_id=f"event-{step.step_id}") for step in subplan.steps)
    plan = Plan(task.task_id, "ready", tuple(steps), state_summary={
        "context_id": context.task_id, "profile_id": context.profile.profile_id,
    })
    planned = [step.tool_name for step in steps]
    missing = sorted(set(expected_tools) - set(planned))
    check = {"valid": not missing, "code": None if not missing else "GOAL_PLAN_MISMATCH",
             "planned_tools": planned, "missing_tools": missing}
    if missing:
        plan = Plan(task.task_id, "rejected", reason_code="GOAL_PLAN_MISMATCH",
                    reason="A required contract tool is absent from preflight plan")
    return task, ledger, plan, check


def _reject(context, task, code, reason, forbidden):
    ledger = ObligationLedger(context.task_id, "multitask_workflow", (
        Obligation("evidence", "successful_tools", []),
    ), forbidden)
    return task, ledger, Plan(task.task_id, "rejected", reason_code=code, reason=reason), {
        "valid": False, "code": code, "planned_tools": [],
    }


class MultiTaskContractGraphPlanner(SharedEvidenceGraphCore):
    """One task-neutral graph with event-specific operations as an adapter."""

    def __init__(self, context, task, ledger, *, max_retries=1, max_repairs=2, max_tool_calls=16):
        if task.goal != "multitask_workflow":
            raise ValueError("Expected a multi-task workflow")
        self.goal_arguments = {name: dict(values) for name, values in task.arguments["goal_arguments"].items()}
        self.labels = tuple(task.arguments.get("labels", ()))
        self.epoch_arguments = {
            "labels": list(self.labels), "tmin": task.arguments.get("tmin"),
            "tmax": task.arguments.get("tmax"),
        }
        if "baseline" in task.arguments:
            self.epoch_arguments["baseline"] = list(task.arguments["baseline"])
        self.selection_authorized = task.arguments.get("selection_authorized") is True
        super().__init__(
            context, task, ledger, MULTITASK_CONTRACTS, max_retries=max_retries,
            max_repairs=max_repairs, max_tool_calls=max_tool_calls,
        )
        self._initial_model_digest = (
            self._model_digest() if "seizure_detection" in self.requested_goals else None
        )

    def _dependencies_for(self, goal):
        contract = self.contracts[goal]
        dependencies = list(contract.base_dependencies)
        if contract.input_policy == "effective_epochs" and "trial_selection" in self.requested_goals:
            dependencies = [name for name in dependencies if name != "create_epochs"]
            dependencies.append("trial_selection")
        return tuple(dependencies)

    def _begin_frontier_snapshot(self):
        super()._begin_frontier_snapshot()
        if "seizure_detection" in self.requested_goals and (
            self._model_digest() != self._initial_model_digest
        ) and self.blocked is None:
            # The legacy model loader caches by path; a changed file cannot be
            # safely retried in-process as if it were the original resource.
            self._block("MODEL_RESOURCE_CHANGED", "Model resource changed during this task")

    def _record_digest(self):
        record = self.context.record
        events = None if record.events is None else {
            "source": record.events.source,
            "items": [event.to_dict() for event in record.events.events],
        }
        metadata = {
            "source": record.source, "shape": list(record.data.shape),
            "dtype": str(record.data.dtype), "sfreq": record.sfreq,
            "channels": list(record.channel_names), "reference": record.reference,
            "montage": record.montage, "processing": list(record.processing_metadata),
            "metadata": dict(record.metadata), "events": events,
        }
        digest = hashlib.sha256(json.dumps(metadata, sort_keys=True, ensure_ascii=False,
                                          default=str).encode("utf-8"))
        digest.update(np.ascontiguousarray(record.data).tobytes())
        return "sha256:" + digest.hexdigest()

    def _model_digest(self):
        value = self.context.executor.resources.get("seizure_model")
        path = Path(value).expanduser() if value else None
        if path is None or not path.is_file():
            return None
        digest = hashlib.sha256(self._record_digest().encode("ascii"))
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return "sha256:" + digest.hexdigest()

    def _artifact_fingerprint(self, artifact_id):
        if artifact_id not in self._fingerprints:
            if artifact_id == f"record:{self.context.task_id}":
                self._fingerprints[artifact_id] = self._record_digest()
            elif artifact_id == f"record-model:{self.context.task_id}":
                self._fingerprints[artifact_id] = self._model_digest()
            else:
                return super()._artifact_fingerprint(artifact_id)
        return self._fingerprints[artifact_id]

    def _input_binding(self, goal):
        policy = self.contracts[goal].input_policy
        if policy in {"record", "record_model"}:
            identity = f"record{'-model' if policy == 'record_model' else ''}:{self.context.task_id}"
            return ArtifactBinding(identity, self._artifact_fingerprint(identity))
        if policy == "source_epochs":
            return self._source_binding()
        if policy == "effective_epochs":
            return self._effective_binding()
        return None

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

    def _resolve_without_tool(self, goal):
        if goal != "trial_selection":
            return False
        quality = self.evidence.get("epoch_quality")
        if quality is None:
            return False
        if not self.selection_authorized:
            self._block("SELECTION_NOT_AUTHORIZED", "Trial selection requires authorization")
            return False
        usable = quality.result["data"]["condition_counts_quality_usable"]
        missing = [label for label in self.labels if usable.get(label, 0) < 1]
        if missing:
            self._block("NO_USABLE_EPOCHS_FOR_CONDITION",
                        "A requested condition lacks quality-usable Epochs", labels=missing)
            return False
        if quality.result["data"]["epoch_counts"]["quality_flagged"] != 0:
            return False
        source = self._source_binding()
        self._materialize_evidence(
            goal, input_binding=source, output_binding=source,
            mode="identity", arguments={"selection_authorized": True},
        )
        self._record_transition("goal_satisfied_without_tool", goal=goal,
                                reason="quality evidence flagged zero Epochs",
                                artifact_id=source.artifact_id)
        return True

    def _action_arguments(self, goal):
        if goal in RECORD_GOALS:
            return dict(self.goal_arguments.get(goal, {}))
        if goal == "observe_events":
            return {}
        if goal == "create_epochs":
            return dict(self.epoch_arguments)
        binding = self._input_binding(goal)
        arguments = {"artifact_id": binding.artifact_id,
                     "expected_artifact_fingerprint": binding.fingerprint}
        if goal == "trial_selection":
            arguments["expected_quality_evidence_id"] = self.evidence[
                "epoch_quality"
            ].result["data"]["evidence_id"]
        return arguments

    def _extra_state(self):
        state = {"record_binding": self._artifact_fingerprint(f"record:{self.context.task_id}")}
        if any(goal in EVENT_GOALS for goal in self.active_goals):
            source = self._source_binding()
            effective = self._effective_binding()
            state["event_state"] = {
                "source_epochs": None if source is None else source.to_dict(),
                "effective_epochs": None if effective is None else effective.to_dict(),
                "selection_mode": self._selection_mode(),
            }
        if "seizure_detection" in self.requested_goals:
            state["model_input_binding"] = self._artifact_fingerprint(
                f"record-model:{self.context.task_id}"
            )
        return state

    def _evidence_check(self, status):
        result = super()._evidence_check(status)
        if any(goal in EVENT_GOALS for goal in self.active_goals):
            effective = self._effective_binding()
            for goal in self.requested_goals:
                token = self.evidence.get(goal)
                if (token is not None and self.contracts[goal].input_policy == "effective_epochs"
                        and token.input_binding != effective):
                    result["violations"].append(f"effective_artifact_mismatch:{goal}")
            result["selection_mode"] = self._selection_mode()
            result["effective_artifact_id"] = None if effective is None else effective.artifact_id
            result["effective_artifact_fingerprint"] = None if effective is None else effective.fingerprint
            result["closed"] = status == "completed" and not result["violations"]
        return result


def run_multitask(context, request, *, max_retries=1, max_repairs=2, max_tool_calls=16):
    """Parsed-task entry; returns the original bounded graph result and preflight."""

    task, ledger, plan, check = compile_multitask(context, request)
    if any(goal not in MULTITASK_CONTRACTS for goal in task.arguments["objectives"]):
        context.trace.finish("v2_preflight_rejected")
        execution = DynamicPlanningRunResult(
            "rejected", plan.to_dict(), (), ({"event": "unsupported_goal_rejected"},),
            context.trace.to_dict(), 0, 0.0,
            {"context_id": context.task_id, "goals": {}},
            {"closed": False, "violations": [check["code"]], "termination_status": "rejected"},
            (),
        )
        return task, ledger, check, execution
    runner = MultiTaskContractGraphPlanner(
        context, task, ledger, max_retries=max_retries,
        max_repairs=max_repairs, max_tool_calls=max_tool_calls,
    )
    return task, ledger, check, runner.run(plan, check)


class ConstraintCarryingEEGAgentV2(ConstraintCarryingEEGAgentV11):
    """Natural language entry with one graph path for record, event and model goals."""

    method_name = "constraint_carrying_eeg_multitask_v2"

    def run(self, user_request):
        interpretation = self.interpreter.interpret(user_request, self.context)
        if not interpretation.success:
            return self._stop("intent_error", interpretation, "无法可靠解析 EEG 分析意图；未执行工具。")
        if interpretation.disposition == "clarify":
            slots = "、".join(interpretation.missing_slots)
            return self._stop("clarification_required", interpretation,
                              f"需要补充或明确：{slots}。未执行工具。")
        if interpretation.disposition == "reject":
            return self._stop("unsupported_or_unobservable", interpretation,
                              interpretation.error_message or "当前任务不受支持。")
        request = MultiTaskRequest.from_intent(interpretation.intent)
        task, ledger, check, execution = run_multitask(
            self.context, request, max_retries=self.max_retries,
            max_repairs=self.max_repairs, max_tool_calls=self.max_tool_calls,
        )
        evidence = execution.evidence_check
        if evidence["closed"]:
            answer, answer_check = self._answer(
                user_request, interpretation, ledger, execution, evidence,
                required_tools=execution.required_answer_tools,
                runtime_facts={
                    "goal_status": execution.scientific_state.get("goals"),
                    "effective_artifact_fingerprint": evidence.get("effective_artifact_fingerprint"),
                },
            )
            reason = "completed" if answer_check["valid"] else "completed_without_llm_answer"
        else:
            answer = "科学约束或数据状态未满足全部目标；未发布不完整分析。"
            answer_check = {"valid": False, "code": "MULTITASK_EVIDENCE_UNCLOSED"}
            reason = "plan_rejected" if execution.status == "rejected" else "safe_stop_without_evidence"
        return Point1RunResult(
            reason, interpretation.to_dict(), ledger.to_dict(), check,
            execution.to_dict(), evidence, answer_check=answer_check,
            final_answer=answer, llm=self._llm_summary(), method=self.method_name,
        )
