"""Opt-in research policy for scientific-need/feedback-driven EEG orchestration.

All numerical work runs through the existing ExecutionContext and Executor.  This
module does not infer event labels, quality thresholds, or clinical meaning.
"""

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping
import json
import math

from ..executor import _validate_schema
from ..tooling import ToolRequest
from .integrated_method.v3 import GoalInstance


USER_TOOLS = frozenset({
    "record_info", "amplitude", "psd", "seizure_detection",
    "epoch_summary", "epoch_quality", "event_bandpower",
})
EPOCH_SCOPE_KEYS = ("labels", "tmin", "tmax", "baseline")


@dataclass(frozen=True)
class ScientificTask:
    goals: tuple[GoalInstance, ...]
    minimum_valid_epochs: Mapping[str, int] = field(default_factory=dict)
    forbidden_operations: tuple[str, ...] = ()
    max_tool_calls: int = 20


def _reject(context, status, code, reason, decisions=()):
    context.trace.finish(code)
    return {
        "status": status, "code": code, "reason": reason,
        "tool_results": [context.results[key].to_dict() for key in context.history],
        "decisions": list(decisions),
        "evidence_bundle": {"status": status, "publication": "none", "goals": []},
        "trace": context.trace.to_dict(),
    }


def _complete(context, task, evidence, decisions):
    context.trace.finish("completed")
    return {
        "status": "completed", "code": None, "reason": None,
        "tool_results": [context.results[key].to_dict() for key in context.history],
        "decisions": decisions,
        "evidence_bundle": {
            "status": "completed", "publication": "all_goals",
            "goals": [evidence[goal.instance_id] for goal in task.goals],
        },
        "trace": context.trace.to_dict(),
    }


def _preflight(context, task):
    if not task.goals or len({g.instance_id for g in task.goals}) != len(task.goals):
        return "INVALID_GOALS", "Goals need unique nonempty IDs"
    if any(not isinstance(g.instance_id, str) or not g.instance_id for g in task.goals):
        return "INVALID_GOALS", "Goals need unique nonempty IDs"
    if not isinstance(task.max_tool_calls, int) or task.max_tool_calls < 1:
        return "INVALID_BUDGET", "Tool budget must be a positive integer"
    if set(task.minimum_valid_epochs) - {g.instance_id for g in task.goals}:
        return "INVALID_REQUIREMENT", "Trial requirements reference an unknown goal"
    for value in task.minimum_valid_epochs.values():
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            return "INVALID_REQUIREMENT", "Minimum valid epochs must be a positive integer"
    try:
        context.profile.validate_record(context.record)
    except ValueError as exc:
        return "INCOMPATIBLE_PROFILE", str(exc)
    record_profile = context.record.metadata.get("profile_id")
    if record_profile and record_profile != context.profile.profile_id:
        return "INCOMPATIBLE_PROFILE", "Record and declared Profile differ"
    forbidden = set(task.forbidden_operations)
    for goal in task.goals:
        name = goal.capability
        spec = context.executor.registry.get(name)
        if name not in USER_TOOLS or spec is None:
            return "UNSUPPORTED_GOAL", f"Unsupported read-only goal: {name}"
        if name in forbidden:
            return "FORBIDDEN_OPERATION", f"Goal tool is forbidden: {name}"
        if not context.profile.supports_tool(name) or (
            "*" not in spec.compatible_profiles
            and context.profile.profile_id not in spec.compatible_profiles
        ):
            return "INCOMPATIBLE_PROFILE", f"Tool is unavailable for Profile: {name}"
        params = dict(goal.parameters)
        if spec.consumes_artifact == "epochs":
            if "create_epochs" in forbidden:
                return "FORBIDDEN_OPERATION", "Epoch creation is forbidden"
            extra = set(params) - set(EPOCH_SCOPE_KEYS)
            if extra:
                return "INVALID_PARAMETERS", f"Unexpected event scope fields: {sorted(extra)}"
            labels = params.get("labels")
            if not isinstance(labels, (list, tuple)) or not labels:
                return "MISSING_EVENT_LABELS", "Explicit event labels are required"
            if any(not isinstance(label, str) or not label for label in labels) or len(set(labels)) != len(labels):
                return "INVALID_EVENT_LABELS", "Event labels must be unique nonempty strings"
            try:
                tmin, tmax = float(params["tmin"]), float(params["tmax"])
            except (KeyError, TypeError, ValueError):
                return "MISSING_EVENT_WINDOW", "Explicit tmin and tmax are required"
            if not math.isfinite(tmin) or not math.isfinite(tmax) or tmin >= tmax:
                return "INVALID_EVENT_WINDOW", "Epoch window requires finite tmin < tmax"
            if name == "event_bandpower" and tmax - tmin < 1.0:
                return "INVALID_EVENT_WINDOW", "Event bandpower requires at least 1 second"
        else:
            try:
                _validate_schema(params, spec.parameters)
                if spec.requires_window:
                    if (spec.max_window_seconds is not None
                            and params["end"] - params["start"] > spec.max_window_seconds):
                        return "INVALID_WINDOW", "Requested window exceeds tool limit"
                    context.record.slice(params["start"], params["end"], params["channels"])
            except (KeyError, TypeError, ValueError) as exc:
                return "INVALID_PARAMETERS", str(exc)
        if spec.required_sfreq is not None and context.record.sfreq != spec.required_sfreq:
            return "MODEL_INPUT_MISMATCH", f"{name} requires {spec.required_sfreq:g} Hz"
        for resource in spec.required_resources:
            path = context.executor.resources.get(resource)
            if not path or not Path(path).expanduser().is_file():
                return "MODEL_RESOURCE_MISSING", f"Required resource is missing: {resource}"
    return None


def _scope(goal):
    return {key: goal.parameters[key] for key in EPOCH_SCOPE_KEYS if key in goal.parameters}


def _groups(task, registry):
    grouped = {}
    for goal in task.goals:
        if registry.get(goal.capability).consumes_artifact != "epochs":
            continue
        scope = _scope(goal)
        key = json.dumps(scope, sort_keys=True, ensure_ascii=False, allow_nan=False)
        grouped.setdefault(key, {"scope": scope, "goals": []})["goals"].append(goal)
    return tuple(grouped.values())


def _call(context, task, name, arguments, decisions, reason):
    if len(context.history) >= task.max_tool_calls:
        return None
    decisions.append({"action": name, "reason": reason, "arguments": dict(arguments)})
    return context.execute(ToolRequest(name, dict(arguments)))


def _need_counts(group, task):
    return max(task.minimum_valid_epochs.get(g.instance_id, 1) for g in group["goals"])


def _add_evidence(evidence, goal, result):
    evidence[goal.instance_id] = {
        "instance_id": goal.instance_id, "capability": goal.capability,
        "parameters": dict(goal.parameters), "request_id": result.request_id,
        "result": result.data,
    }


def run_adaptive(context, task):
    """Progressively expand only unmet scientific prerequisites.

    Event inventory is worth a call when a user-specified trial minimum > 1 can
    eliminate downstream work. Epoch construction then reveals boundary losses;
    atomic multi-goal publication motivates checking those gates before cheap
    independent consumers. No probabilistic VOI or automatic trial selection.
    """
    error = _preflight(context, task)
    if error:
        code, reason = error
        status = "clarification_required" if code.startswith("MISSING_") else "rejected"
        return _reject(context, status, code, reason)
    decisions, evidence = [], {}
    forbidden = set(task.forbidden_operations)
    for group in _groups(task, context.executor.registry):
        scope, minimum = group["scope"], _need_counts(group, task)
        labels = tuple(scope["labels"])
        if minimum > 1 and "list_events" not in forbidden:
            observed = _call(context, task, "list_events", {}, decisions,
                             "event inventory may rule out the declared trial requirement")
            if observed is None:
                return _reject(context, "stopped", "TOOL_BUDGET_EXCEEDED", "No budget for event inventory", decisions)
            if not observed.success:
                return _reject(context, "stopped", observed.error_code, "Event inventory failed", decisions)
            decisions.append({"observation": "event_counts", "counts": {
                label: observed.data["labels"].get(label, 0) for label in labels}})
            if any(observed.data["labels"].get(label, 0) < minimum for label in labels):
                return _reject(context, "scientific_stop", "INSUFFICIENT_EVENT_COUNT",
                               "Observed event count cannot meet the requested minimum", decisions)
        created = _call(context, task, "create_epochs", scope, decisions,
                        "materialize authorized event scope to observe valid trials")
        if created is None:
            return _reject(context, "stopped", "TOOL_BUDGET_EXCEEDED", "No budget for Epoch creation", decisions)
        if not created.success:
            return _reject(context, "scientific_stop", created.error_code,
                           "Epoch construction failed; no event consumer can be released", decisions)
        counts = Counter(created.data["event_labels"])
        decisions.append({"observation": "valid_epoch_counts", "counts": dict(counts),
                          "rejected_count": created.data["rejected_epoch_count"]})
        if any(counts.get(label, 0) < minimum for label in labels):
            return _reject(context, "scientific_stop", "INSUFFICIENT_VALID_EPOCHS",
                           "Boundary-valid trial count is below the requested minimum", decisions)
        for goal in group["goals"]:
            result = _call(context, task, goal.capability, {
                "artifact_id": created.data["artifact_id"],
                "expected_artifact_fingerprint": created.data["artifact_fingerprint"],
            }, decisions, "all declared event prerequisites are now satisfied")
            if result is None:
                return _reject(context, "stopped", "TOOL_BUDGET_EXCEEDED", "No budget for event analysis", decisions)
            if not result.success:
                return _reject(context, "scientific_stop", result.error_code, "Event analysis failed", decisions)
            _add_evidence(evidence, goal, result)
    for goal in task.goals:
        if goal.instance_id in evidence:
            continue
        result = _call(context, task, goal.capability, goal.parameters, decisions,
                       "independent goal after all atomic event gates have passed")
        if result is None:
            return _reject(context, "stopped", "TOOL_BUDGET_EXCEEDED", "No budget for analysis", decisions)
        if not result.success:
            return _reject(context, "scientific_stop", result.error_code, "Analysis failed", decisions)
        _add_evidence(evidence, goal, result)
    return _complete(context, task, evidence, decisions)
