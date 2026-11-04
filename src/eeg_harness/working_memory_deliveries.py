"""Opt-in multi-result scientific delivery over the original working-memory store.

This module defines completion/storage/reuse contracts, not numerical execution
or a planner. Every action still runs WorkingMemoryStore -> original Executor.
"""

from dataclasses import dataclass, field
import hashlib
import math

from .working_memory import (WorkingMemoryStore, ScientificSubgoal, NUMERIC_TOOLS,
                             TERMINALS, clone, encoded)
from .research.integrated_method.v3 import EVENT_CAPABILITIES, REQUIRED_PARAMETERS, RESULT_UNITS
from .research.task_memory import TaskEntry
from .research.task_memory_evidence import scalar_paths
from .executor import _validate_schema


@dataclass
class DeliverySubgoal(ScientificSubgoal):
    deliveries: list[dict] = field(default_factory=list)
    result_ids: list[str] = field(default_factory=list)
    reused: dict = field(default_factory=dict)


class MultiResultWorkingMemoryStore(WorkingMemoryStore):
    """One scientific purpose may produce multiple independently readable results."""

    def begin_subgoal(self, title, record, deliverable=None, scope=None, *, deliveries=None,
                      checks=None, revision_of=None, dependencies=None, criteria=None, implicit=False):
        if self.active is not None:
            return self._error("ACTIVE_SUBGOAL", "Complete or suspend the current subgoal first")
        if not isinstance(title, str) or not title.strip() or len(title) > 400 or record not in self.records:
            return self._error("INVALID_SUBGOAL", "A title and an available record are required")
        if deliveries is not None and (deliverable is not None or scope is not None or checks or revision_of):
            return self._error("MIXED_CONTRACTS", "Choose a deliveries list OR the legacy single-result contract")
        if deliveries is None:
            if deliverable not in TERMINALS or not isinstance(scope, dict):
                return self._error("INVALID_SUBGOAL", "Declare explicit deliverables and scope")
            deliveries = [{"key": "main", "tool": deliverable, "scope": scope,
                           **({"revision_of": revision_of} if revision_of else {})}]
            for name in checks or []:
                if name != deliverable:
                    deliveries.append({"key": name, "tool": name,
                                       "scope": {} if name in {"record_info", "list_events"} else scope})
        if not isinstance(deliveries, list) or not 1 <= len(deliveries) <= 12:
            return self._error("INVALID_DELIVERIES", "Declare one to twelve delivery items")
        normalized = []
        registry = self.contexts[record].executor.registry
        for item in deliveries:
            if not isinstance(item, dict) or set(item) - {"key", "tool", "scope", "required", "revision_of"}:
                return self._error("INVALID_DELIVERY", "Unknown delivery fields")
            key, name, params = item.get("key"), item.get("tool"), item.get("scope")
            if (not isinstance(key, str) or not key or len(key) > 80 or name not in NUMERIC_TOOLS or
                    not isinstance(params, dict) or type(item.get("required", True)) is not bool):
                return self._error("INVALID_DELIVERY", "Each delivery needs a key, enabled tool, scientific scope and boolean required")
            event = name in EVENT_CAPABILITIES or name == "create_epochs"
            allowed = {"labels", "tmin", "tmax"} if event else set(registry.get(name).parameters.get("properties", {}))
            required = ("labels", "tmin", "tmax") if event else REQUIRED_PARAMETERS.get(name, ())
            if set(params) - allowed or any(params.get(k) in (None, "", []) for k in required):
                return {**self._error("MISSING_OR_INVALID_SCOPE", "Declare computational scope, not an output selector"),
                        "key": key, "allowed": sorted(allowed), "required": list(required)}
            try:
                _validate_schema(params, registry.get("create_epochs" if event else name).parameters)
            except (TypeError, ValueError):
                return self._error("INVALID_SCOPE", "Scope does not satisfy the original tool schema")
            parent = None
            if item.get("revision_of"):
                parent = self.find_entry(item["revision_of"])
                if parent is None or (parent.record, parent.capability) != (record, name):
                    return self._error("INVALID_REVISION_PARENT", "Use an exact result of the same record and capability")
            normalized.append({"key": key, "tool": name, "scope": clone(params),
                               "required": item.get("required", True),
                               "revision_of": parent.task_id if parent else None})
        if (len({x["key"] for x in normalized}) != len(normalized) or
                len({encoded([x["tool"], x["scope"]]) for x in normalized}) != len(normalized) or
                not any(x["required"] for x in normalized)):
            return self._error("DUPLICATE_OR_EMPTY_CONTRACT", "Unique keys/scopes and at least one required delivery are needed")
        deps = dependencies or []
        if not isinstance(deps, list) or any(self.find_entry(x) is None for x in deps):
            return self._error("INVALID_DEPENDENCY", "Dependencies must identify actual results")
        parsed_criteria = []
        for criterion in criteria or []:
            if not isinstance(criterion, dict):
                return self._error("INVALID_CRITERION", "Criterion must be structured")
            c = clone(criterion)
            if "tool" in c and "delivery" not in c:
                targets = [d for d in normalized if d["tool"] == c["tool"]]
                if len(targets) != 1:
                    return self._error("AMBIGUOUS_CRITERION", "Use the local delivery key when tool scopes differ")
                c["delivery"] = targets[0]["key"]
                c.pop("tool")
            if (set(c) != {"delivery", "path", "op", "value"} or c["delivery"] not in {d["key"] for d in normalized}
                    or not isinstance(c["path"], list) or not c["path"] or c["op"] not in {"eq", "gte", "lte"}
                    or type(c["value"]) not in {str, float, int, bool}
                    or isinstance(c["value"], (int, float)) and not math.isfinite(c["value"])):
                return self._error("INVALID_CRITERION", "Reference a delivery, real field and finite scalar condition")
            parsed_criteria.append(c)
        first = normalized[0]
        goal = DeliverySubgoal(subgoal_id=f"{self.session_id}-s{len(self.subgoals)+1}",
            title=title, record=record, deliverable=first["tool"], scope=clone(first["scope"]), checks=[],
            criteria=parsed_criteria, dependencies=[self.find_entry(x).task_id for x in deps],
            implicit=implicit, turn=self.turn, deliveries=normalized)
        self.active = goal
        self.subgoals.append(goal)
        self.active_record, self.last_owner = record, goal.subgoal_id
        self.events.append({"event": "started", "subgoal_id": goal.subgoal_id, "record": record,
                            "delivery_keys": [d["key"] for d in normalized], "turn": self.turn})
        return {"status": "active", "subgoal_id": goal.subgoal_id, "contract": self.goal_card(goal)}

    def goal_card(self, goal):
        card = super().goal_card(goal)
        card["deliveries"] = clone(goal.deliveries)
        card["result_ids"] = clone(goal.result_ids)
        card["reused_results"] = clone(goal.reused)
        card["contract_version"] = "multi_result_v1"
        return card

    def _scientific_scope(self, name, args, context):
        spec = context.executor.registry.get(name)
        if spec.consumes_artifact:
            artifact = context.artifacts.get(args.get("artifact_id"))
            if artifact is None:
                return None
            return {"labels": list(artifact.parameters["selected_labels"]), "tmin": artifact.tmin, "tmax": artifact.tmax}
        return clone(args)

    def _scope_error(self, goal, request, context):
        actual = self._scientific_scope(request.name, dict(request.arguments), context)
        if actual is None:
            return "ARTIFACT_NOT_FOUND"
        spec = context.executor.registry.get(request.name)
        if spec.consumes_artifact:
            artifact = context.artifacts[request.arguments["artifact_id"]]
            if artifact.source != context.record.source or artifact.baseline is not None:
                return "SCIENTIFIC_SCOPE_MISMATCH"
        if request.name in {"record_info", "list_events"}:
            return None
        # Extra measurements on a declared scientific object are allowed, but
        # never fulfill a different tool/scope's required delivery.
        if not any(d["scope"] == actual for d in goal.deliveries):
            return "SCIENTIFIC_SCOPE_MISMATCH"
        return None

    def decorate_observation(self, goal, observation, context):
        observation["scope"] = self._scientific_scope(observation["request"]["name"], observation["request"]["arguments"], context)

    def _binding(self, context, name, artifact_id=None):
        r = context.record
        metadata = {"source": r.source, "sfreq": r.sfreq, "channels": r.channel_names,
                    "reference": r.reference, "montage": r.montage,
                    "processing": list(r.processing_metadata), "shape": list(r.data.shape), "dtype": str(r.data.dtype),
                    "events": [e.to_dict() for e in r.events.events] if r.events else None}
        digest = hashlib.sha256(encoded(metadata))
        digest.update(r.data.tobytes(order="C"))
        artifact = context.artifacts.get(artifact_id)
        return {"record_fingerprint": digest.hexdigest(),
                "config": {k: clone(context.executor.config[k]) for k in context.executor.registry.get(name).config_keys},
                "artifact_id": artifact_id, "artifact_fingerprint": artifact.content_fingerprint() if artifact else None}

    def remember_observation(self, goal, observation, context):
        result = observation["result"]
        # A subsequent numerical attempt supersedes an explicit binding for
        # this item. Conversely, reuse_result below records a later binding.
        target = next((d for d in goal.deliveries if d["tool"] == observation["request"]["name"] and d["scope"] == observation["scope"]), None)
        if target:
            goal.reused.pop(target["key"], None)
        if not result["success"]:
            return
        name = observation["request"]["name"]
        artifact_id = (result["data"] or {}).get("artifact_id")
        binding = self._binding(context, name, artifact_id)
        parent = target["revision_of"] if target else None
        task_id = f"{self.session_id}-t{len(self.entries)+1}"
        meta = {"sfreq": context.record.sfreq, "reference": context.record.reference,
                "montage": context.record.montage, "processing_metadata": clone(list(context.record.processing_metadata)),
                "time_reference": "event_relative" if name in EVENT_CAPABILITIES or name == "create_epochs" else "record_absolute",
                **binding["config"]}
        proof = {"result": result["data"], "record": goal.record, "scope": observation["scope"],
                 "binding": binding, "tool": name, "revision_of": parent}
        evidence = {"source": context.record.source, "source_stage": "event_epochs" if artifact_id else "loaded_record",
                    "analysis_configuration": meta, "unit_or_kind": RESULT_UNITS.get(name, "Epoch artifact descriptor" if name == "create_epochs" else "event metadata"),
                    "evidence_token": "wm-set:" + hashlib.sha256(encoded(proof)).hexdigest(),
                    "binding": binding, "subgoal_id": goal.subgoal_id,
                    "delivery_key": target["key"] if target else None}
        entry = TaskEntry(task_id, len(self.entries)+1, goal.record, name, clone(observation["scope"]),
                          goal.title, parent, "completed", clone(result["data"]), evidence, (clone(observation),))
        self.entries.append(entry)
        goal.result_ids.append(task_id)
        observation["result_id"] = task_id

    def _binding_valid(self, entry):
        b = entry.evidence["binding"]
        context = self.contexts[entry.record]
        if b["artifact_id"] and b["artifact_id"] not in context.artifacts:
            return False
        return b == self._binding(context, entry.capability, b["artifact_id"])

    def completion_check(self, goal):
        states = []
        for delivery in goal.deliveries:
            attempts = [o for o in goal.observations if o["request"]["name"] == delivery["tool"] and o["scope"] == delivery["scope"]]
            entry = self.find_entry(goal.reused.get(delivery["key"]))
            state = "missing"
            if entry:
                state = "satisfied"
            elif attempts:
                entry = self.find_entry(attempts[-1].get("result_id"))
                state = "failed" if not attempts[-1]["result"]["success"] else "satisfied"
            if entry:
                state = "satisfied" if self._binding_valid(entry) else "stale"
            if state == "satisfied":
                for c in (c for c in goal.criteria if c["delivery"] == delivery["key"]):
                    try:
                        value = entry.result
                        for k in c["path"]:
                            value = value[k]
                        # Legacy numeric tools serialize scalars in scientific
                        # notation. Compare their values without changing output.
                        if type(c["value"]) in {int, float} and isinstance(value, str):
                            value = float(value)
                        if isinstance(value, float) and not math.isfinite(value):
                            raise ValueError("Non-finite observation")
                        ok = value == c["value"] if c["op"] == "eq" else value >= c["value"] if c["op"] == "gte" else value <= c["value"]
                    except (KeyError, TypeError, IndexError, ValueError):
                        ok = False
                    if not ok:
                        state = "condition_unsatisfied"
            states.append({"key": delivery["key"], "required": delivery["required"], "status": state,
                           "result_id": entry.task_id if entry else None})
        # Required outputs on one event scope must refer to the same actual
        # Epoch object, not merely two content-equivalent artifacts.
        groups = {}
        for delivery, state in zip(goal.deliveries, states):
            if state["status"] == "satisfied" and delivery["required"]:
                entry = self.find_entry(state["result_id"])
                ident = entry.evidence["binding"]["artifact_id"]
                if ident:
                    groups.setdefault(encoded(delivery["scope"]), []).append((ident, state))
        for group in groups.values():
            if len({ident for ident, _ in group}) > 1:
                for _, state in group:
                    state["status"] = "artifact_mismatch"
        valid = all(s["status"] == "satisfied" for s in states if s["required"])
        return {"valid": valid, "code": None if valid else "INCOMPLETE_DELIVERIES", "deliveries": states}

    def reuse_result(self, delivery_key, task_id):
        goal, entry = self.active, self.find_entry(task_id)
        if goal is None or goal.status not in {"active", "blocked"}:
            return self._error("NO_ACTIVE_SUBGOAL", "Resume or start a subgoal before binding evidence")
        delivery = next((d for d in goal.deliveries if d["key"] == delivery_key), None)
        if entry is None or delivery is None:
            return self._error("RESULT_NOT_FOUND", "Choose a visible result and a declared delivery")
        if (entry.record != goal.record or entry.capability != delivery["tool"] or entry.parameters != delivery["scope"]
                or entry.revision_of != delivery["revision_of"] or not self._binding_valid(entry)):
            return self._error("REUSE_MISMATCH", "Record, capability, scope, version and resource identity must all match")
        goal.reused[delivery_key] = entry.task_id
        self.last_owner = goal.subgoal_id
        self.events.append({"event": "result_reused", "subgoal_id": goal.subgoal_id,
                            "delivery_key": delivery_key, "result_id": entry.task_id, "turn": self.turn})
        return {"status": "reused", "task_id": entry.task_id, "delivery_check": self.completion_check(goal)}

    def close_subgoal(self, status, unresolved=None, subgoal_id=None):
        goal = self.find_subgoal(subgoal_id) if subgoal_id else self.active
        if goal is None or goal.status == "completed":
            return self._error("NOT_CLOSABLE", "Choose a pending subgoal")
        if self.active is not None and self.active is not goal:
            return self._error("ACTIVE_SUBGOAL", "Resolve the active subgoal first")
        if status == "completed":
            check = self.completion_check(goal)
            if not check["valid"]:
                return {"status": "rejected", **check}
            goal.status, goal.unresolved = "completed", []
        elif status == "suspended" and isinstance(unresolved, list) and unresolved and all(isinstance(x, str) for x in unresolved):
            goal.status, goal.unresolved = "suspended", clone(unresolved)
        else:
            return self._error("INVALID_STATUS", "Complete verified work or suspend with unresolved items")
        # Only a unique result has a safe legacy subgoal-to-task alias.
        all_ids = list(dict.fromkeys(goal.result_ids + list(goal.reused.values())))
        goal.task_id = all_ids[0] if len(all_ids) == 1 else None
        self.last_owner, self.active = goal.subgoal_id, None
        self.events.append({"event": "archived" if status == "completed" else "suspended",
                            "subgoal_id": goal.subgoal_id, "result_ids": all_ids, "turn": self.turn})
        return {"status": status, "summary": self.summary(goal)}

    def summary(self, goal):
        card = self.goal_card(goal)
        card["delivery_check"] = self.completion_check(goal)
        card["available_control"] = "read_evidence/restore_subgoal or continue a new requirement" if goal.status == "completed" else "close_subgoal when required deliveries are satisfied; otherwise continue missing work"
        card["results"] = []
        for ident in dict.fromkeys(goal.result_ids + list(goal.reused.values())):
            entry = self.find_entry(ident)
            fields = list(scalar_paths(entry.result))
            successors = [e.task_id for e in self.entries if e.revision_of == ident]
            card["results"].append({**entry.card(compact=True), "subgoal_id": entry.evidence["subgoal_id"],
                "delivery_key": entry.evidence["delivery_key"], "binding_valid": self._binding_valid(entry),
                "superseded_by": successors, "reused": ident in goal.reused.values(),
                "evidence": {**{k:v for k,v in clone(entry.evidence).items() if k != "binding"},
                    "fields": [{"path":p,"value":v} for p,v in fields[:12]],
                    "omitted_fields": max(0,len(fields)-12), "readable_fields": [p for p,_ in fields[:64]]},
                "artifact_id": entry.evidence["binding"]["artifact_id"]})
        card["failed_attempts"] = [{"tool":o["request"]["name"], "scope":o["scope"], "error":o["result"]["error"]}
                                   for o in goal.observations if not o["result"]["success"]]
        return card
