"""Fair fixed-order and explicit dynamic Expert controls for Issue #32.

Both use the same context/Executor, static preflight, task authorization, trial
requirements and publication rule as the candidate; they differ only in policy.
"""

from collections import Counter

from .adaptive_orchestration import (
    _add_evidence, _call, _complete, _groups, _need_counts, _preflight,
    _reject,
)


def _begin(context, task):
    error = _preflight(context, task)
    if error is None:
        return None
    code, reason = error
    status = "clarification_required" if code.startswith("MISSING_") else "rejected"
    return _reject(context, status, code, reason)


def run_fixed_plan(context, task):
    """Predeclared user-goal order with the same hard scientific guards.

The plan is not permitted to call an invalid downstream tool once the observed
count fails. It does not reconsider the ordering of *independent* goals.
    """
    stopped = _begin(context, task)
    if stopped:
        return stopped
    decisions, evidence, prepared = [], {}, {}
    groups = _groups(task, context.executor.registry)
    lookup = {goal.instance_id: group for group in groups for goal in group["goals"]}
    forbidden = set(task.forbidden_operations)
    for goal in task.goals:
        group = lookup.get(goal.instance_id)
        if group is None:
            result = _call(context, task, goal.capability, goal.parameters, decisions,
                           "fixed user-goal order")
            if result is None:
                return _reject(context, "stopped", "TOOL_BUDGET_EXCEEDED", "Tool budget exhausted", decisions)
            if not result.success:
                return _reject(context, "scientific_stop", result.error_code, "Analysis failed", decisions)
            _add_evidence(evidence, goal, result)
            continue
        key = id(group)
        if key not in prepared:
            scope, minimum = group["scope"], _need_counts(group, task)
            labels = tuple(scope["labels"])
            if minimum > 1 and "list_events" not in forbidden:
                observed = _call(context, task, "list_events", {}, decisions,
                                 "fixed plan inventory step")
                if observed is None:
                    return _reject(context, "stopped", "TOOL_BUDGET_EXCEEDED", "Tool budget exhausted", decisions)
                if not observed.success:
                    return _reject(context, "scientific_stop", observed.error_code, "Inventory failed", decisions)
                if any(observed.data["labels"].get(label, 0) < minimum for label in labels):
                    return _reject(context, "scientific_stop", "INSUFFICIENT_EVENT_COUNT",
                                   "Raw event count below requested minimum", decisions)
            created = _call(context, task, "create_epochs", scope, decisions,
                            "fixed plan Epoch step")
            if created is None:
                return _reject(context, "stopped", "TOOL_BUDGET_EXCEEDED", "Tool budget exhausted", decisions)
            if not created.success:
                return _reject(context, "scientific_stop", created.error_code, "Epoch creation failed", decisions)
            counts = Counter(created.data["event_labels"])
            if any(counts.get(label, 0) < minimum for label in labels):
                return _reject(context, "scientific_stop", "INSUFFICIENT_VALID_EPOCHS",
                               "Valid Epoch count below requested minimum", decisions)
            prepared[key] = created.data
        artifact = prepared[key]
        result = _call(context, task, goal.capability, {
            "artifact_id": artifact["artifact_id"],
            "expected_artifact_fingerprint": artifact["artifact_fingerprint"],
        }, decisions, "fixed plan event consumer")
        if result is None:
            return _reject(context, "stopped", "TOOL_BUDGET_EXCEEDED", "Tool budget exhausted", decisions)
        if not result.success:
            return _reject(context, "scientific_stop", result.error_code, "Event analysis failed", decisions)
        _add_evidence(evidence, goal, result)
    return _complete(context, task, evidence, decisions)


def run_strong_expert(context, task):
    """Hand-written conditional EEG workflow with event-risk-first ordering.

This expert is deliberately allowed the same observations, guards and budget
as the candidate, including skipping the inventory when it is unnecessary or
forbidden. It is a genuine comparator, not a disabled fixed-order script.
    """
    stopped = _begin(context, task)
    if stopped:
        return stopped
    decisions, evidence = [], {}
    groups = _groups(task, context.executor.registry)
    at_risk = [group for group in groups if _need_counts(group, task) > 1]
    # Strong Expert is not denied global atomic-task inspection or tool reuse.
    if at_risk and "list_events" not in task.forbidden_operations:
        inventory = _call(context, task, "list_events", {}, decisions,
                          "expert inspects all event scopes before irreversible work")
        if inventory is None:
            return _reject(context, "stopped", "TOOL_BUDGET_EXCEEDED", "Tool budget exhausted", decisions)
        if not inventory.success:
            return _reject(context, "scientific_stop", inventory.error_code, "Inventory failed", decisions)
        for group in at_risk:
            labels = tuple(group["scope"]["labels"])
            minimum = _need_counts(group, task)
            if any(inventory.data["labels"].get(label, 0) < minimum for label in labels):
                return _reject(context, "scientific_stop", "INSUFFICIENT_EVENT_COUNT",
                               "Raw event count below requested minimum", decisions)
    prepared = []
    for group in groups:
        scope = group["scope"]
        labels = tuple(scope["labels"])
        minimum = _need_counts(group, task)
        epochs = _call(context, task, "create_epochs", scope, decisions,
                       "expert checks actual valid trial support")
        if epochs is None:
            return _reject(context, "stopped", "TOOL_BUDGET_EXCEEDED", "Tool budget exhausted", decisions)
        if not epochs.success:
            return _reject(context, "scientific_stop", epochs.error_code, "Epoch creation failed", decisions)
        valid = Counter(epochs.data["event_labels"])
        if any(valid.get(label, 0) < minimum for label in labels):
            return _reject(context, "scientific_stop", "INSUFFICIENT_VALID_EPOCHS",
                           "Valid Epoch count below requested minimum", decisions)
        prepared.append((group, epochs.data))
    for group, artifact in prepared:
        for goal in group["goals"]:
            measured = _call(context, task, goal.capability, {
                "artifact_id": artifact["artifact_id"],
                "expected_artifact_fingerprint": artifact["artifact_fingerprint"],
            }, decisions, "expert releases only supported event analysis")
            if measured is None:
                return _reject(context, "stopped", "TOOL_BUDGET_EXCEEDED", "Tool budget exhausted", decisions)
            if not measured.success:
                return _reject(context, "scientific_stop", measured.error_code, "Event analysis failed", decisions)
            _add_evidence(evidence, goal, measured)
    for goal in task.goals:
        if goal.instance_id in evidence:
            continue
        measured = _call(context, task, goal.capability, goal.parameters, decisions,
                         "expert executes independent goal after risky prerequisite")
        if measured is None:
            return _reject(context, "stopped", "TOOL_BUDGET_EXCEEDED", "Tool budget exhausted", decisions)
        if not measured.success:
            return _reject(context, "scientific_stop", measured.error_code, "Analysis failed", decisions)
        _add_evidence(evidence, goal, measured)
    return _complete(context, task, evidence, decisions)
