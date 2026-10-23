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
    observes_state: tuple[str, ...] = ()
    preconditions: Mapping[str, Any] = field(default_factory=dict)

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
            "observes_state": list(self.observes_state),
            "preconditions": dict(self.preconditions),
        }


def build_operation_contracts(registry):
    """Build contracts for the eight registered tools without loading models."""

    contracts = {}
    for spec in registry.list_specs():
        contracts[spec.name] = OperationContract(
            tool_name=spec.name,
            required_parameters=tuple(spec.parameters.get("required", ())),
            compatible_profiles=tuple(spec.compatible_profiles),
            consumes_artifact=spec.consumes_artifact,
            produces_artifact=spec.produces_artifact,
            requires_events=spec.requires_events,
            required_resources=tuple(spec.required_resources),
            state_effect=spec.state_effect,
            observes_state=tuple(spec.observes_state),
            preconditions=dict(spec.preconditions),
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

    def _validate_epoch_goal(self, task, arguments, state, consumer):
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
        minimum = float(
            self.contracts[consumer].preconditions.get(
                "min_artifact_duration_seconds", 0.0
            )
        )
        if tmax - tmin < minimum:
            return "UNSATISFIABLE_CONSTRAINTS", (
                f"{consumer} requires an Epoch of at least {minimum:g} seconds"
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

    def _find_artifact_producer(self, artifact_type):
        return next(
            (item for item in self.contracts.values() if item.produces_artifact == artifact_type),
            None,
        )

    def _find_state_observer(self, state_name):
        return next(
            (item for item in self.contracts.values() if state_name in item.observes_state),
            None,
        )

    def _plan_artifact_consumer(self, task, state):
        consumer = task.goal
        consumer_contract = self.contracts[consumer]
        arguments = dict(task.arguments)
        artifact_id = arguments.get("artifact_id")
        if artifact_id and state.artifact(artifact_id):
            tool_args = {"artifact_id": artifact_id}
            failure = self._validate_tool(task, consumer, tool_args, state)
            if failure:
                return _reject(task, state, failure[0], failure[1])
            return Plan(
                task.task_id,
                "ready",
                (PlanStep("consume-artifact", consumer, tool_args, purpose="consume existing session artifact"),),
                state_summary={"context_id": state.context_id, "profile_id": state.profile_id},
            )
        producer = self._find_artifact_producer(consumer_contract.consumes_artifact)
        if producer is None:
            return _reject(
                task, state, "UNSATISFIABLE_CONSTRAINTS",
                f"No tool produces {consumer_contract.consumes_artifact} artifacts",
            )
        failure = self._validate_epoch_goal(task, arguments, state, consumer)
        if failure:
            return _reject(task, state, failure[0], failure[1])
        epoch_args = {
            "labels": list(arguments["labels"]),
            "tmin": arguments["tmin"],
            "tmax": arguments["tmax"],
        }
        if "baseline" in arguments:
            epoch_args["baseline"] = list(arguments["baseline"])
        steps = []
        observer = self._find_state_observer("events") if producer.requires_events else None
        producer_dependencies = ()
        if observer is not None:
            steps.append(PlanStep(
                "observe-events", observer.tool_name, {},
                purpose="record visible event state",
            ))
            producer_dependencies = ("observe-events",)
        steps.extend((
            PlanStep(
                "produce-artifact", producer.tool_name, epoch_args,
                producer_dependencies, "produce declared session artifact",
            ),
            PlanStep(
                "consume-artifact",
                consumer,
                {"artifact_id": {"$result": "produce-artifact", "path": ["artifact_id"]}},
                ("produce-artifact",),
                "consume the newly produced declared artifact",
            ),
        ))
        return Plan(
            task.task_id,
            "ready",
            tuple(steps),
            state_summary={"context_id": state.context_id, "profile_id": state.profile_id},
        )

    def _plan_quality_selection(self, task, state):
        """Plan measure-before-select while reusing one real Epoch artifact."""
        arguments = dict(task.arguments)
        if arguments.pop("selection_authorized", False) is not True:
            return _reject(
                task, state, "UNSATISFIABLE_CONSTRAINTS",
                "Epoch selection requires explicit user authorization",
            )
        failure = self._validate_epoch_goal(task, arguments, state, "epoch_quality")
        if failure:
            return _reject(task, state, failure[0], failure[1])
        epoch_args = {
            "labels": list(arguments["labels"]),
            "tmin": arguments["tmin"], "tmax": arguments["tmax"],
        }
        if "baseline" in arguments:
            epoch_args["baseline"] = list(arguments["baseline"])
        reference = {"$result": "produce-artifact", "path": ["artifact_id"]}
        steps = (
            PlanStep("observe-events", "list_events", {}, purpose="record visible event state"),
            PlanStep("produce-artifact", "create_epochs", epoch_args, ("observe-events",), "produce one declared Epoch artifact"),
            PlanStep("measure-quality", "epoch_quality", {"artifact_id": reference}, ("produce-artifact",), "measure quality before any selection"),
            PlanStep("select-quality", "select_quality_epochs", {"artifact_id": reference}, ("measure-quality",), "apply explicitly authorized empirical selection"),
        )
        return Plan(
            task.task_id, "ready", steps,
            state_summary={"context_id": state.context_id, "profile_id": state.profile_id},
        )

    def _plan_quality_selected_bandpower(self, task, state):
        """Measure, select, then analyse the derived Epoch artifact."""
        base = self._plan_quality_selection(task, state)
        if base.status != "ready":
            return base
        selected_reference = {"$result": "select-quality", "path": ["artifact_id"]}
        steps = base.steps + (
            PlanStep(
                "analyse-selected", "event_bandpower",
                {"artifact_id": selected_reference}, ("select-quality",),
                "analyse only the explicitly authorized quality-selected artifact",
            ),
        )
        return Plan(
            task.task_id, "ready", steps,
            state_summary={"context_id": state.context_id, "profile_id": state.profile_id},
        )

    def plan(self, task, state=None):
        state = state or EEGStateSnapshot.from_context(self.context)
        if task.goal == "quality_selected_bandpower":
            return self._plan_quality_selected_bandpower(task, state)
        if task.goal == "quality_selection":
            return self._plan_quality_selection(task, state)
        if task.goal == "tool":
            return self._plan_tool(task, state)
        if task.goal in self.contracts and self.contracts[task.goal].consumes_artifact:
            return self._plan_artifact_consumer(task, state)
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
    def __init__(self, context, max_replans=1, plan_validator=None):
        self.context = context
        self.planner = StateAwareConstrainedPlanner(context)
        self.max_replans = max_replans
        self.plan_validator = plan_validator

    def run(self, task):
        return self.execute_plan(task, self.planner.plan(task))

    def execute_plan(self, task, plan):
        from .tooling import ToolRequest

        started = time.perf_counter()
        planning_trace = [{"event": "plan_created", "status": plan.status, "reason": plan.reason_code}]
        validation = self.plan_validator(plan) if self.plan_validator and plan.status == "ready" else None
        if validation is not None:
            planning_trace.append({"event": "obligations_checked", **dict(validation)})
        if validation is not None and not validation.get("valid", False):
            self.context.trace.finish("constraint_rejected")
            return PlanningRunResult(
                "rejected", plan.to_dict(), (), tuple(planning_trace),
                self.context.trace.to_dict(), 0,
                round((time.perf_counter() - started) * 1000, 3),
            )
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
            validation = (
                self.plan_validator(current_plan)
                if self.plan_validator and current_plan.status == "ready" else None
            )
            planning_trace.append({
                "event": "replanned",
                "attempt": replans,
                "status": current_plan.status,
                "reason": current_plan.reason_code,
                "obligations_valid": None if validation is None else validation.get("valid", False),
            })
            if current_plan.status != "ready" or (
                validation is not None and not validation.get("valid", False)
            ):
                self.context.trace.finish("replan_rejected")
                status = "rejected_after_replan"
                break
        return PlanningRunResult(
            status, plan.to_dict(), tuple(results), tuple(planning_trace),
            self.context.trace.to_dict(), replans,
            round((time.perf_counter() - started) * 1000, 3),
        )
