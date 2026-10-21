"""Minimal state and contract model for planning-before-execution research.

The objects in this module describe facts already verified by the Harness.
They deliberately contain no dataset labels, diagnoses, raw EEG, or inferred
signal quality.
"""

from dataclasses import dataclass, field
import json
from pathlib import Path
import time
from typing import Any, Mapping, Optional

from .provenance import source_reference


@dataclass(frozen=True)
class TaskSpec:
    goal: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    subtasks: tuple["TaskSpec", ...] = ()
    task_id: str = "task"

    def to_dict(self):
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "arguments": dict(self.arguments),
            "subtasks": [item.to_dict() for item in self.subtasks],
        }


@dataclass(frozen=True)
class ArtifactSnapshot:
    artifact_id: str
    artifact_type: str
    context_id: str
    profile_id: str
    record_source: Mapping[str, Any]
    summary: Mapping[str, Any]

    def to_dict(self):
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "context_id": self.context_id,
            "profile_id": self.profile_id,
            "record_source": dict(self.record_source),
            "summary": dict(self.summary),
        }


@dataclass(frozen=True)
class EEGStateSnapshot:
    context_id: str
    profile_id: str
    record_source: Mapping[str, Any]
    sfreq: float
    duration_seconds: float
    channel_names: tuple[str, ...]
    event_labels: Mapping[str, int]
    artifacts: tuple[ArtifactSnapshot, ...]
    resources_available: Mapping[str, bool]
    verified_quality_facts: tuple[str, ...] = ()

    @classmethod
    def from_context(cls, context):
        labels = {}
        if context.record.events is not None:
            labels = context.record.events.summary()["labels"]
        record_ref = source_reference(context.record.source)
        artifacts = []
        for artifact_id, artifact in context.artifacts.items():
            summary = artifact.summary() if hasattr(artifact, "summary") else {}
            artifacts.append(
                ArtifactSnapshot(
                    artifact_id=artifact_id,
                    artifact_type="epochs" if hasattr(artifact, "event_labels") else "unknown",
                    context_id=context.task_id,
                    profile_id=context.profile.profile_id,
                    record_source=record_ref,
                    summary=summary,
                )
            )
        resources = {
            name: bool(value) and Path(value).expanduser().is_file()
            for name, value in sorted(context.executor.resources.items())
            if name != "artifact_store"
        }
        return cls(
            context_id=context.task_id,
            profile_id=context.profile.profile_id,
            record_source=record_ref,
            sfreq=context.record.sfreq,
            duration_seconds=context.record.duration_seconds,
            channel_names=context.record.channel_names,
            event_labels=labels,
            artifacts=tuple(artifacts),
            resources_available=resources,
        )

    def artifact(self, artifact_id):
        return next((item for item in self.artifacts if item.artifact_id == artifact_id), None)

    def to_dict(self):
        payload = {
            "context_id": self.context_id,
            "profile_id": self.profile_id,
            "record_source": dict(self.record_source),
            "sfreq": self.sfreq,
            "duration_seconds": self.duration_seconds,
            "channel_names": list(self.channel_names),
            "event_labels": dict(self.event_labels),
            "artifacts": [item.to_dict() for item in self.artifacts],
            "resources_available": dict(self.resources_available),
            "verified_quality_facts": list(self.verified_quality_facts),
        }
        json.dumps(payload, ensure_ascii=False, allow_nan=False)
        return payload


@dataclass(frozen=True)
class OperationContract:
    tool_name: str
    required_parameters: tuple[str, ...]
    compatible_profiles: tuple[str, ...]
    consumes_artifact: Optional[str] = None
    produces_artifact: Optional[str] = None
    requires_events: bool = False
    required_resources: tuple[str, ...] = ()
    state_effect: str = "result_only"

    def to_dict(self):
        return {
            "tool_name": self.tool_name,
            "required_parameters": list(self.required_parameters),
            "compatible_profiles": list(self.compatible_profiles),
            "consumes_artifact": self.consumes_artifact,
            "produces_artifact": self.produces_artifact,
            "requires_events": self.requires_events,
            "required_resources": list(self.required_resources),
            "state_effect": self.state_effect,
        }


def build_operation_contracts(registry):
    """Build contracts for the eight registered tools without loading models."""

    artifact_consumers = {"epoch_summary": "epochs", "event_bandpower": "epochs"}
    contracts = {}
    for spec in registry.list_specs():
        contracts[spec.name] = OperationContract(
            tool_name=spec.name,
            required_parameters=tuple(spec.parameters.get("required", ())),
            compatible_profiles=tuple(spec.compatible_profiles),
            consumes_artifact=artifact_consumers.get(spec.name),
            produces_artifact="epochs" if spec.name == "create_epochs" else None,
            requires_events=spec.name == "create_epochs",
            required_resources=tuple(spec.required_resources),
            state_effect="stores_session_artifact" if spec.name == "create_epochs" else "result_only",
        )
    return contracts


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    tool_name: str
    arguments: Mapping[str, Any]
    depends_on: tuple[str, ...] = ()
    purpose: str = ""

    def to_dict(self):
        return {
            "step_id": self.step_id,
            "tool_name": self.tool_name,
            "arguments": dict(self.arguments),
            "depends_on": list(self.depends_on),
            "purpose": self.purpose,
        }


@dataclass(frozen=True)
class Plan:
    task_id: str
    status: str
    steps: tuple[PlanStep, ...] = ()
    reason_code: Optional[str] = None
    reason: Optional[str] = None
    state_summary: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self):
        payload = {
            "task_id": self.task_id,
            "status": self.status,
            "steps": [item.to_dict() for item in self.steps],
            "reason": None if self.reason_code is None else {
                "code": self.reason_code,
                "message": self.reason,
            },
            "state_summary": dict(self.state_summary),
        }
        json.dumps(payload, ensure_ascii=False, allow_nan=False)
        return payload


def _reject(task, state, code, message):
    return Plan(
        task_id=task.task_id,
        status="rejected",
        reason_code=code,
        reason=message,
        state_summary={
            "context_id": state.context_id,
            "profile_id": state.profile_id,
            "artifact_count": len(state.artifacts),
        },
    )


class StateAwareConstrainedPlanner:
    """Deterministic pilot planner over current state and tool contracts."""

    def __init__(self, context):
        self.context = context
        self.contracts = build_operation_contracts(context.executor.registry)

    def _validate_tool(self, task, tool_name, arguments, state):
        from .executor import _validate_schema
        from .profiles import ProfileValidationError

        spec = self.context.executor.registry.get(tool_name)
        if spec is None or tool_name not in self.contracts:
            return "UNSUPPORTED_GOAL", f"Unknown or uncontracted tool: {tool_name}"
        if not self.context.profile.supports_tool(tool_name) or (
            "*" not in spec.compatible_profiles
            and state.profile_id not in spec.compatible_profiles
        ):
            return "UNSATISFIABLE_CONSTRAINTS", (
                f"Tool {tool_name} is incompatible with profile {state.profile_id}"
            )
        try:
            self.context.profile.validate_record(self.context.record)
            _validate_schema(dict(arguments), spec.parameters)
        except (ProfileValidationError, TypeError, ValueError) as exc:
            return "UNSATISFIABLE_CONSTRAINTS", str(exc)
        if spec.required_sfreq is not None and state.sfreq != spec.required_sfreq:
            return "UNSATISFIABLE_CONSTRAINTS", (
                f"Tool {tool_name} requires {spec.required_sfreq:g} Hz, got {state.sfreq:g} Hz"
            )
        for resource in spec.required_resources:
            if not state.resources_available.get(resource, False):
                return "UNSATISFIABLE_CONSTRAINTS", f"Required resource is missing: {resource}"
        if spec.requires_window:
            start, end = arguments["start"], arguments["end"]
            if spec.max_window_seconds is not None and end - start > spec.max_window_seconds:
                return "UNSATISFIABLE_CONSTRAINTS", "Requested window exceeds the tool limit"
            try:
                self.context.record.slice(start, end, arguments["channels"])
            except ValueError as exc:
                return "UNSATISFIABLE_CONSTRAINTS", str(exc)
        contract = self.contracts[tool_name]
        if contract.consumes_artifact:
            artifact = state.artifact(arguments.get("artifact_id"))
            if artifact is None or artifact.artifact_type != contract.consumes_artifact:
                return "UNSATISFIABLE_CONSTRAINTS", (
                    f"Current context has no compatible {contract.consumes_artifact} artifact"
                )
        return None

    def _plan_tool(self, task, state):
        arguments = dict(task.arguments)
        tool_name = arguments.pop("tool_name", None)
        parameters = arguments.pop("parameters", arguments)
        if not tool_name:
            return _reject(task, state, "UNSUPPORTED_GOAL", "tool goal requires tool_name")
        failure = self._validate_tool(task, tool_name, parameters, state)
        if failure:
            return _reject(task, state, failure[0], failure[1])
        return Plan(
            task.task_id,
            "ready",
            (PlanStep("invoke", tool_name, parameters, purpose="requested tool operation"),),
            state_summary={"context_id": state.context_id, "profile_id": state.profile_id},
        )

    def _validate_epoch_goal(self, task, arguments, state):
        labels = tuple(arguments.get("labels", ()))
        if not labels:
            return "UNSATISFIABLE_CONSTRAINTS", "At least one event label is required"
        if not state.event_labels:
            return "UNSATISFIABLE_CONSTRAINTS", "Current record has no events or annotations"
        missing = [label for label in labels if label not in state.event_labels]
        if missing:
            return "UNSATISFIABLE_CONSTRAINTS", (
                "Requested event label(s) do not exist: " + ", ".join(missing)
            )
        try:
            tmin = float(arguments["tmin"])
            tmax = float(arguments["tmax"])
        except (KeyError, TypeError, ValueError):
            return "UNSATISFIABLE_CONSTRAINTS", "Finite tmin and tmax are required"
        if not (tmin < tmax):
            return "UNSATISFIABLE_CONSTRAINTS", "Epoch requires tmin < tmax"
        if tmax - tmin < 1.0:
            return "UNSATISFIABLE_CONSTRAINTS", (
                "event_bandpower requires at least a one-second Epoch"
            )
        baseline = arguments.get("baseline")
        if baseline is not None:
            if len(baseline) != 2:
                return "UNSATISFIABLE_CONSTRAINTS", "Baseline requires two bounds"
            start = tmin if baseline[0] is None else float(baseline[0])
            end = tmax if baseline[1] is None else float(baseline[1])
            if start < tmin or end > tmax or start >= end:
                return "UNSATISFIABLE_CONSTRAINTS", "Baseline must be inside the Epoch window"
        return None

    def _plan_event_bandpower(self, task, state):
        arguments = dict(task.arguments)
        artifact_id = arguments.get("artifact_id")
        if artifact_id and state.artifact(artifact_id):
            tool_args = {"artifact_id": artifact_id}
            failure = self._validate_tool(task, "event_bandpower", tool_args, state)
            if failure:
                return _reject(task, state, failure[0], failure[1])
            return Plan(
                task.task_id,
                "ready",
                (PlanStep("bandpower", "event_bandpower", tool_args, purpose="consume existing Epoch artifact"),),
                state_summary={"context_id": state.context_id, "profile_id": state.profile_id},
            )
        failure = self._validate_epoch_goal(task, arguments, state)
        if failure:
            return _reject(task, state, failure[0], failure[1])
        epoch_args = {
            "labels": list(arguments["labels"]),
            "tmin": arguments["tmin"],
            "tmax": arguments["tmax"],
        }
        if "baseline" in arguments:
            epoch_args["baseline"] = list(arguments["baseline"])
        return Plan(
            task.task_id,
            "ready",
            (
                PlanStep("list-events", "list_events", {}, purpose="record visible event state"),
                PlanStep("create-epochs", "create_epochs", epoch_args, ("list-events",), "produce session Epoch artifact"),
                PlanStep(
                    "bandpower",
                    "event_bandpower",
                    {"artifact_id": {"$result": "create-epochs", "path": ["artifact_id"]}},
                    ("create-epochs",),
                    "consume the newly produced Epoch artifact",
                ),
            ),
            state_summary={"context_id": state.context_id, "profile_id": state.profile_id},
        )

    def plan(self, task, state=None):
        state = state or EEGStateSnapshot.from_context(self.context)
        if task.goal == "tool":
            return self._plan_tool(task, state)
        if task.goal == "event_bandpower":
            return self._plan_event_bandpower(task, state)
        if task.goal == "sequence":
            steps = []
            for index, subtask in enumerate(task.subtasks):
                subplan = self.plan(subtask, state)
                if subplan.status != "ready":
                    return _reject(task, state, subplan.reason_code, subplan.reason)
                for step in subplan.steps:
                    prefix = f"s{index + 1}-"
                    def prefix_references(value):
                        if isinstance(value, list):
                            return [prefix_references(item) for item in value]
                        if isinstance(value, dict):
                            output = {key: prefix_references(item) for key, item in value.items()}
                            if "$result" in output:
                                output["$result"] = prefix + output["$result"]
                            return output
                        return value

                    arguments = prefix_references(step.arguments)
                    steps.append(PlanStep(prefix + step.step_id, step.tool_name, arguments, tuple(prefix + item for item in step.depends_on), step.purpose))
            return Plan(task.task_id, "ready", tuple(steps), state_summary={"context_id": state.context_id, "profile_id": state.profile_id})
        return _reject(task, state, "UNSUPPORTED_GOAL", f"Unsupported goal: {task.goal}")


@dataclass(frozen=True)
class PlanningRunResult:
    status: str
    plan: Mapping[str, Any]
    tool_results: tuple[Mapping[str, Any], ...]
    planning_trace: tuple[Mapping[str, Any], ...]
    execution_trace: Mapping[str, Any]
    replans: int
    duration_ms: float

    def to_dict(self):
        payload = {
            "status": self.status,
            "plan": dict(self.plan),
            "tool_results": [dict(item) for item in self.tool_results],
            "planning_trace": [dict(item) for item in self.planning_trace],
            "execution_trace": dict(self.execution_trace),
            "replans": self.replans,
            "duration_ms": self.duration_ms,
        }
        json.dumps(payload, ensure_ascii=False, allow_nan=False)
        return payload


class ConstrainedPlanRunner:
    def __init__(self, context, max_replans=1):
        self.context = context
        self.planner = StateAwareConstrainedPlanner(context)
        self.max_replans = max_replans

    def run(self, task):
        return self.execute_plan(task, self.planner.plan(task))

    def execute_plan(self, task, plan):
        from .tooling import ToolRequest

        started = time.perf_counter()
        planning_trace = [{"event": "plan_created", "status": plan.status, "reason": plan.reason_code}]
        if plan.status != "ready":
            self.context.trace.finish("preflight_rejected")
            return PlanningRunResult(
                "rejected", plan.to_dict(), (), tuple(planning_trace),
                self.context.trace.to_dict(), 0,
                round((time.perf_counter() - started) * 1000, 3),
            )
        results = []
        current_plan = plan
        replans = 0
        while True:
            failed = False
            for step in current_plan.steps:
                result = self.context.execute(
                    ToolRequest(step.tool_name, step.arguments, request_id=step.step_id)
                )
                results.append(result.to_dict())
                planning_trace.append({
                    "event": "step_executed",
                    "step_id": step.step_id,
                    "success": result.success,
                    "error_code": result.error_code,
                })
                if not result.success:
                    failed = True
                    break
            if not failed:
                self.context.trace.finish("completed")
                status = "completed"
                break
            if replans >= self.max_replans:
                self.context.trace.finish("safe_stop_after_execution_failure")
                status = "execution_failed"
                break
            replans += 1
            current_plan = self.planner.plan(task, EEGStateSnapshot.from_context(self.context))
            planning_trace.append({
                "event": "replanned",
                "attempt": replans,
                "status": current_plan.status,
                "reason": current_plan.reason_code,
            })
            if current_plan.status != "ready":
                self.context.trace.finish("replan_rejected")
                status = "rejected_after_replan"
                break
        return PlanningRunResult(
            status, plan.to_dict(), tuple(results), tuple(planning_trace),
            self.context.trace.to_dict(), replans,
            round((time.perf_counter() - started) * 1000, 3),
        )
