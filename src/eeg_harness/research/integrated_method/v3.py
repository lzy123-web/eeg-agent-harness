"""Opt-in instance-goal compiler over the existing shared EEG evidence graph.

Each requested analysis is an instance, not a tool type.  Internal event-state
nodes are shared only when their complete scientific parameter scope matches.
The Executor and the frozen v1/v2 methods remain unchanged.
"""

from dataclasses import dataclass, field, replace
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Mapping

import numpy as np

from ...planning import Plan, StateAwareConstrainedPlanner, TaskSpec
from .contracts import Obligation, ObligationLedger, _forbidden_tools
from .v11 import ArtifactBinding, GoalContract
from .v2 import MULTITASK_CONTRACTS
from .v2_graph import SharedEvidenceGraphCore


USER_CAPABILITIES = frozenset({
    "record_info", "record_quality", "amplitude", "psd", "seizure_detection",
    "epoch_quality", "epoch_summary", "event_bandpower",
})
EVENT_CAPABILITIES = frozenset({"epoch_quality", "epoch_summary", "event_bandpower"})
EVENT_SCOPE_KEYS = ("labels", "tmin", "tmax", "baseline")
REQUIRED_PARAMETERS = {
    "record_info": (), "record_quality": (),
    "amplitude": ("channels", "start", "end"),
    "psd": ("channels", "start", "end"),
    "seizure_detection": ("channels", "start", "end"),
    "epoch_quality": ("labels", "tmin", "tmax"),
    "epoch_summary": ("labels", "tmin", "tmax"),
    "event_bandpower": ("labels", "tmin", "tmax"),
}
RESULT_UNITS = {
    "record_info": "record metadata", "record_quality": "quality measurements",
    "amplitude": "V", "psd": "V²", "seizure_detection": "model score",
    "epoch_quality": "quality measurements", "epoch_summary": "epoch counts",
    "event_bandpower": "V²",
}


@dataclass(frozen=True)
class GoalInstance:
    instance_id: str
    capability: str
    parameters: Mapping = field(default_factory=dict)
    request_quote: str = ""
    concept_quote: str = ""
    parameter_quotes: Mapping[str, str] = field(default_factory=dict)
    parameter_sources: Mapping[str, str] = field(default_factory=dict)
    source_stage: str = "current"
    scope_source: str | None = None

    def to_dict(self):
        return {"instance_id": self.instance_id, "capability": self.capability,
                "parameters": dict(self.parameters), "request_quote": self.request_quote,
                "concept_quote": self.concept_quote,
                "parameter_quotes": dict(self.parameter_quotes),
                "parameter_sources": dict(self.parameter_sources),
                "source_stage": self.source_stage,
                "scope_source": self.scope_source}


@dataclass(frozen=True)
class InstanceTaskRequest:
    goals: tuple[GoalInstance, ...]
    forbidden_operations: tuple[str, ...] = ()


def capability_catalog(context):
    """Expose only capabilities executable by this entry for this record."""
    catalog = []
    for name in sorted(USER_CAPABILITIES):
        spec = context.executor.registry.get(name)
        if (spec is None or not context.profile.supports_tool(name)
                or "*" not in spec.compatible_profiles
                and context.profile.profile_id not in spec.compatible_profiles):
            continue
        if name not in MULTITASK_CONTRACTS:
            continue
        if (name in EVENT_CAPABILITIES and context.record.events is None
                or spec.required_sfreq is not None and context.record.sfreq != spec.required_sfreq
                or any(not Path(context.executor.resources.get(resource, "")).expanduser().is_file()
                       for resource in spec.required_resources)):
            continue
        catalog.append({
            "name": name, "description": spec.description,
            "parameters": dict(spec.parameters), "required_user_parameters": list(REQUIRED_PARAMETERS[name]),
            "input_artifact": spec.consumes_artifact or "EEGRecord",
            "result_type": spec.return_type, "unit_or_kind": RESULT_UNITS[name],
            "required_resources": list(spec.required_resources),
            "configuration_dependencies": list(spec.config_keys),
            "scientific_scope": "event-locked epochs" if name in EVENT_CAPABILITIES else "continuous record",
        })
    return catalog


def capability_inventory(context):
    """Distinguish current entry support, migrated-but-blocked, and old-only tools."""
    active = {item["name"] for item in capability_catalog(context)}
    entries = []
    for spec in context.executor.registry.list_specs():
        if spec.name in active:
            category = "available_v3"
        elif spec.name in USER_CAPABILITIES:
            category = "v3_unavailable_for_current_context"
        elif spec.name in {"list_events", "create_epochs"}:
            category = "internal_prerequisite_only"
        else:
            category = "registered_not_migrated_to_v3"
        entries.append({"name": spec.name, "category": category})
    return entries


def _scope_key(parameters):
    scope = {key: parameters[key] for key in EVENT_SCOPE_KEYS if key in parameters}
    serialized = json.dumps(scope, sort_keys=True, ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:12]


def _failure(context, code, reason, details=None, goals=()):
    status = "clarification_required" if code == "MISSING_PARAMETERS" else "rejected"
    unfulfilled = [{"instance_id": goal.instance_id,
                    **(details or {}).get(goal.instance_id, {"code": "ATOMIC_PREFLIGHT_WITHHELD"})}
                   for goal in goals]
    return {"status": status,
            "code": code, "reason": reason, "details": details or {},
            "context_id": context.task_id, "tool_results": [],
            "evidence_bundle": {"schema_version": "1", "context_id": context.task_id,
                                "status": status, "goals": [],
                                "expected_goal_count": len(goals), "published_goal_count": 0,
                                "publication": "none", "unfulfilled_goals": unfulfilled}}


def compile_instances(context, request):
    """Atomically validate all user goals and build per-instance graph contracts."""
    goals = tuple(request.goals)
    if not goals or len({goal.instance_id for goal in goals}) != len(goals):
        return None, _failure(context, "INVALID_GOAL_INSTANCES", "Goal IDs must be nonempty and unique",
                              goals=goals)
    available = {item["name"] for item in capability_catalog(context)}
    forbidden = _forbidden_tools(request.forbidden_operations)
    contracts, arguments, scopes, reasons = {}, {}, {}, {}
    planner = StateAwareConstrainedPlanner(context)
    preflight_steps = []
    for goal in goals:
        name, params = goal.capability, dict(goal.parameters)
        if not goal.instance_id or not isinstance(goal.instance_id, str):
            reasons[str(goal.instance_id)] = {"code": "INVALID_GOAL_ID"}
            continue
        if name not in USER_CAPABILITIES or name not in available:
            reasons[goal.instance_id] = {"code": "UNSUPPORTED_OR_INCOMPATIBLE_CAPABILITY", "capability": name}
            continue
        if name in forbidden:
            reasons[goal.instance_id] = {"code": "FORBIDDEN_OPERATION", "capability": name}
            continue
        actual_stage = context.record.metadata.get("source_stage", "current")
        if goal.source_stage not in {"current", actual_stage}:
            reasons[goal.instance_id] = {"code": "SOURCE_STAGE_UNAVAILABLE",
                                         "requested": goal.source_stage,
                                         "actual": actual_stage}
            continue
        missing = [key for key in REQUIRED_PARAMETERS[name] if params.get(key) in (None, "", [])]
        if name == "record_quality" and ("start" in params) != ("end" in params):
            missing.append("end" if "start" in params else "start")
        if missing:
            reasons[goal.instance_id] = {"code": "MISSING_PARAMETERS", "fields": missing}
            continue
        if name == "record_quality":
            try:
                context.record.slice(
                    params.get("start", 0), params.get("end", context.record.duration_seconds),
                    params.get("channels", list(context.record.channel_names)),
                )
            except (TypeError, ValueError) as exc:
                reasons[goal.instance_id] = {"code": "INVALID_RECORD_QUALITY_SCOPE",
                                             "reason": str(exc)}
                continue
        if name in EVENT_CAPABILITIES:
            scope = {key: params[key] for key in EVENT_SCOPE_KEYS if key in params}
            extra = set(params) - set(EVENT_SCOPE_KEYS)
            if extra:
                reasons[goal.instance_id] = {"code": "INVALID_PARAMETERS", "fields": sorted(extra)}
                continue
            subplan = planner.plan(TaskSpec("event_workflow", {
                **scope, "objectives": [name],
            }, task_id=f"{context.task_id}-{goal.instance_id}"))
            if subplan.status != "ready":
                reasons[goal.instance_id] = {"code": subplan.reason_code, "reason": subplan.reason}
                continue
            key = _scope_key(scope)
            scopes.setdefault(key, scope)
            producer = f"_epochs_{key}"
            contracts[goal.instance_id] = replace(
                MULTITASK_CONTRACTS[name], goal=goal.instance_id,
                base_dependencies=(producer,), answer_required=True,
            )
            arguments[goal.instance_id] = {}
        else:
            subplan = planner.plan(TaskSpec("tool", {"tool_name": name, "parameters": params},
                                            task_id=f"{context.task_id}-{goal.instance_id}"))
            if subplan.status != "ready":
                reasons[goal.instance_id] = {"code": subplan.reason_code, "reason": subplan.reason}
                continue
            contracts[goal.instance_id] = replace(MULTITASK_CONTRACTS[name], goal=goal.instance_id)
            arguments[goal.instance_id] = params
        preflight_steps.extend(step.to_dict() for step in subplan.steps)
    if reasons:
        code = "MISSING_PARAMETERS" if all(item["code"] == "MISSING_PARAMETERS" for item in reasons.values()) else "GOAL_PREFLIGHT_FAILED"
        return None, _failure(context, code, "No EEG tool was run; resolve every goal before execution",
                              reasons, goals)
    if scopes:
        contracts["_observe_events"] = GoalContract(
            "_observe_events", "list_events", "consumer", "record", (), 0, False)
        for key, scope in scopes.items():
            node = f"_epochs_{key}"
            contracts[node] = GoalContract(
                node, "create_epochs", "producer", "record", ("_observe_events",), 1, False)
            arguments[node] = scope
    task = TaskSpec("multitask_instances", {
        "objectives": [goal.instance_id for goal in goals],
        "instances": [goal.to_dict() for goal in goals],
    }, task_id=context.task_id)
    ledger = ObligationLedger(context.task_id, "multitask_instances", (
        Obligation("goal_instances", "objectives", [goal.instance_id for goal in goals]),
    ), forbidden)
    plan = Plan(task.task_id, "ready", state_summary={
        "context_id": context.task_id, "profile_id": context.profile.profile_id,
    })
    return (task, ledger, plan, contracts, arguments, scopes, preflight_steps), None


class InstanceEvidenceGraph(SharedEvidenceGraphCore):
    """Same shared reconciliation/frontier/execution core, indexed by goal instance."""

    def __init__(self, context, task, ledger, contracts, arguments, scopes, **limits):
        self.goal_arguments = arguments
        self.scopes = scopes
        self.labels = ()
        self.epoch_arguments = {}
        self.selection_authorized = False
        self._config_for_evidence = {}
        super().__init__(context, task, ledger, contracts, **limits)
        self._initial_model_digest = self._model_digest() if any(
            contracts[g].tool_name == "seizure_detection" for g in self.requested_goals
        ) else None

    def _begin_frontier_snapshot(self):
        super()._begin_frontier_snapshot()
        if self._initial_model_digest is not None and self._model_digest() != self._initial_model_digest:
            self._block("MODEL_RESOURCE_CHANGED", "Model resource changed during this task")

    def _analysis_configuration(self, goal):
        spec = self.context.executor.registry.get(self.contracts[goal].tool_name)
        return {key: deepcopy(self.context.executor.config.get(key))
                for key in (() if spec is None else spec.config_keys)}

    def _evidence_payload(self, goal, **kwargs):
        payload = super()._evidence_payload(goal, **kwargs)
        payload["analysis_configuration"] = self._analysis_configuration(goal)
        return payload

    def _materialize_evidence(self, goal, **kwargs):
        token = super()._materialize_evidence(goal, **kwargs)
        self._config_for_evidence[goal] = self._analysis_configuration(goal)
        return token

    def _restore_cached_consumer(self, goal):
        restored = super()._restore_cached_consumer(goal)
        if restored:
            self._config_for_evidence[goal] = self._analysis_configuration(goal)
        return restored

    def _reconcile(self):
        super()._reconcile()
        changed = {goal for goal in self.evidence
                   if self._config_for_evidence.get(goal) != self._analysis_configuration(goal)}
        if not changed:
            return
        invalid = set(changed)
        while True:
            descendants = {goal for goal in self.evidence if goal not in invalid
                           and any(dep in invalid for dep in self.dependencies[goal])}
            if not descendants:
                break
            invalid.update(descendants)
        for goal in invalid:
            token = self.evidence.pop(goal)
            self._config_for_evidence.pop(goal, None)
            if self.contracts[goal].role == "consumer":
                self.evidence_cache.setdefault(goal, {})[token.semantic_id] = token
        self._record_transition("analysis_configuration_invalidated",
                                goals=sorted(invalid), changed_goals=sorted(changed))

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

    def _source_binding_for(self, goal):
        producer = self.dependencies[goal][0]
        token = self.evidence.get(producer)
        return None if token is None else token.output_binding

    def _input_binding(self, goal):
        policy = self.contracts[goal].input_policy
        if policy in {"record", "record_model"}:
            identity = f"record{'-model' if policy == 'record_model' else ''}:{self.context.task_id}"
            return ArtifactBinding(identity, self._artifact_fingerprint(identity))
        if policy in {"source_epochs", "effective_epochs"}:
            return self._source_binding_for(goal)
        return None

    def _action_arguments(self, goal):
        if goal == "_observe_events":
            return {}
        if goal.startswith("_epochs_"):
            return dict(self.goal_arguments[goal])
        binding = self._input_binding(goal)
        if binding is not None and self.contracts[goal].input_policy in {"source_epochs", "effective_epochs"}:
            return {"artifact_id": binding.artifact_id,
                    "expected_artifact_fingerprint": binding.fingerprint}
        return dict(self.goal_arguments[goal])

    def _resolve_without_tool(self, goal):
        """Reuse only exact same tool, arguments, bound input and dependencies."""
        if goal not in self.requested_goals:
            return False
        contract = self.contracts[goal]
        arguments = self._action_arguments(goal)
        binding = self._input_binding(goal)
        dependency_semantics = tuple(
            self.evidence[item].semantic_id for item in self.dependencies[goal]
        )
        for candidate in self.requested_goals:
            token = self.evidence.get(candidate)
            if (candidate == goal or token is None or token.result is None
                    or self.contracts[candidate].tool_name != contract.tool_name
                    or self._action_arguments(candidate) != arguments
                    or token.input_binding != binding
                    or tuple(self.evidence[item].semantic_id for item in self.dependencies[candidate])
                    != dependency_semantics):
                continue
            shared = dict(token.result)
            shared["execution_kind"] = "shared_identical_goal_result"
            self._materialize_evidence(
                goal, request_id=token.request_id, result=shared,
                input_binding=binding, arguments=arguments,
            )
            self._record_transition("identical_goal_evidence_shared", goal=goal,
                                    source_goal=candidate, source_request_id=token.request_id)
            return True
        return False

    def _extra_state(self):
        return {"record_binding": self._artifact_fingerprint(f"record:{self.context.task_id}"),
                "event_scopes": dict(self.scopes)}


def run_instances(context, request, *, max_retries=1, max_repairs=2, max_tool_calls=20):
    compiled, failure = compile_instances(context, request)
    if failure:
        return failure
    task, ledger, plan, contracts, arguments, scopes, preflight = compiled
    graph = InstanceEvidenceGraph(context, task, ledger, contracts, arguments, scopes,
                                  max_retries=max_retries, max_repairs=max_repairs,
                                  max_tool_calls=max_tool_calls)
    execution = graph.run(plan, {"valid": True, "code": None,
                                 "planned_tools": [step["tool_name"] for step in preflight]})
    bundle = {"schema_version": "1", "context_id": context.task_id,
              "status": execution.status, "goals": [],
              "expected_goal_count": len(request.goals), "published_goal_count": 0,
              "publication": "none",
              "unfulfilled_goals": [
                  {"instance_id": goal.instance_id,
                   **execution.evidence_check["goal_status"][goal.instance_id],
                   "publication": "withheld_until_all_goals_close"}
                  for goal in request.goals
              ]}
    if execution.evidence_check["closed"]:
        items = []
        for goal in request.goals:
            token = graph.evidence[goal.instance_id]
            if goal.capability in EVENT_CAPABILITIES:
                analysis_scope = "event_epochs"
            elif goal.capability == "record_quality" and not any(
                    key in goal.parameters for key in ("start", "end")):
                analysis_scope = "whole_record"
            elif goal.capability == "record_info":
                analysis_scope = "record_metadata"
            elif goal.capability == "seizure_detection":
                analysis_scope = "verified_model_window"
            else:
                analysis_scope = "continuous_window"
            data = token.result["data"]
            items.append({
                "instance_id": goal.instance_id, "capability": goal.capability,
                "parameters": dict(goal.parameters), "status": "satisfied",
                "analysis_scope": analysis_scope,
                "source_stage": context.record.metadata.get("source_stage", "current"),
                "requested_source_stage": goal.source_stage,
                "request_quote": goal.request_quote, "concept_quote": goal.concept_quote,
                "parameter_quotes": dict(goal.parameter_quotes),
                "parameter_sources": dict(goal.parameter_sources),
                "scope_source": goal.scope_source,
                "evidence_token": token.token_id, "request_id": token.request_id,
                "input_binding": None if token.input_binding is None else token.input_binding.to_dict(),
                "dependency_evidence": dict(token.dependency_tokens),
                "unit_or_kind": RESULT_UNITS[goal.capability],
                "sampling_rate_hz": context.record.sfreq,
                "analysis_configuration": graph._config_for_evidence[goal.instance_id],
                "method": data.get("method") if isinstance(data, dict) else
                          context.executor.registry.get(goal.capability).description,
                "source": context.record.source, "profile_id": context.profile.profile_id,
                "result": data,
                "limitation": "Research analysis only; no diagnosis or ability score.",
            })
        bundle = {"schema_version": "1", "context_id": context.task_id,
                  "status": "completed",
                  "expected_goal_count": len(request.goals),
                  "published_goal_count": len(items), "publication": "complete",
                  "record_state": {"source": context.record.source,
                                   "source_stage": context.record.metadata.get("source_stage", "current"),
                                   "reference": context.record.reference,
                                   "montage": context.record.montage,
                                   "processing_metadata": list(context.record.processing_metadata)},
                  "unfulfilled_goals": [], "goals": items}
        json.dumps(bundle, ensure_ascii=False, allow_nan=False)
    return {"status": execution.status,
            "code": None if execution.evidence_check["closed"] else execution.status,
            "context_id": context.task_id, "preflight": preflight,
            "tool_results": list(execution.tool_results),
            "execution": execution.to_dict(), "evidence_bundle": bundle}
