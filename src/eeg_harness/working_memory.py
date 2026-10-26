"""Execution-time EEG subgoals over the existing Executor and task archive.

No planner, numerical algorithm or LLM lives here. Completion is a check of a
model-declared scientific delivery contract, not proof of intent completeness.
"""

from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json

from .context import ExecutionContext
from .executor import Executor, _validate_schema
from .profiles import EDF_NATIVE
from .tooling import ToolRequest
from .tools import build_default_registry
from .research.integrated_method.v3 import EVENT_CAPABILITIES, REQUIRED_PARAMETERS, RESULT_UNITS
from .research.task_memory import CONFIG, TaskEntry
from .research.task_memory_issue41 import GranularEpisodeSession
from .research.task_memory_evidence import normalized_read, scalar_paths


NUMERIC_TOOLS = frozenset({
    "record_info", "amplitude", "psd", "record_quality", "list_events",
    "create_epochs", "epoch_summary", "epoch_quality", "event_bandpower",
})
TERMINALS = NUMERIC_TOOLS - {"create_epochs"}


def clone(value):
    return deepcopy(value)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


@dataclass
class ScientificSubgoal:
    subgoal_id: str
    title: str
    record: str
    deliverable: str
    scope: dict
    checks: list[str]
    criteria: list[dict] = field(default_factory=list)
    revision_of: str | None = None
    dependencies: list[str] = field(default_factory=list)
    status: str = "active"
    observations: list[dict] = field(default_factory=list)
    exchanges: list[list[dict]] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    task_id: str | None = None
    implicit: bool = False
    turn: int = 0


class WorkingMemoryStore(GranularEpisodeSession):
    """One session, explicit records, real artifacts and append-only task entries.

    Reuses the historical task/read contract but does NOT call its synchronous
    analyze/run_instances pipeline. Each numeric action is executed separately.
    """

    def __init__(self, session_id, records, *, config=None, profiles=None):
        super().__init__(session_id, records)
        if any(not isinstance(r.source, str) or not r.source.startswith("synthetic://")
               for r in self.records.values()):
            raise ValueError("Working memory network research requires synthetic sources")
        self.config = clone(config if config is not None else CONFIG)
        registry = build_default_registry()
        self.contexts = {
            alias: ExecutionContext(record, (profiles or {}).get(alias, EDF_NATIVE),
                                    Executor(registry, self.config), f"{session_id}:{alias}")
            for alias, record in self.records.items()
        }
        self.subgoals = []
        self.active = None
        self.turn = 0
        self.sequence = 0
        self.last_owner = None
        self.events = []

    def find_subgoal(self, ident):
        return next((g for g in self.subgoals if g.subgoal_id == ident), None)

    def find_entry(self, ident):
        return next((e for e in self.entries if e.task_id == ident), None)

    def _error(self, code, message):
        return {"status": "rejected", "code": code, "message": message}

    def begin_subgoal(self, title, record, deliverable, scope, *, checks=None,
                      revision_of=None, dependencies=None, criteria=None, implicit=False):
        if self.active is not None:
            return self._error("ACTIVE_SUBGOAL", "Complete, suspend or resume the current subgoal first")
        if not isinstance(title, str) or not title.strip() or len(title) > 400:
            return self._error("INVALID_SUBGOAL", "A short scientific objective is required")
        if record not in self.records or deliverable not in TERMINALS or not isinstance(scope, dict):
            return self._error("INVALID_SUBGOAL", "Known record, deliverable and explicit scope required")
        spec = self.contexts[record].executor.registry.get(deliverable)
        allowed = ({"labels", "tmin", "tmax", "baseline"} if deliverable in EVENT_CAPABILITIES
                   else set(spec.parameters.get("properties", {})))
        required = REQUIRED_PARAMETERS.get(deliverable, ())
        if set(scope) - allowed or any(scope.get(k) in (None, "", []) for k in required):
            return {**self._error("MISSING_OR_INVALID_SCOPE", "Use the capability's computational scope; output fields do not change tool inputs"),
                    "allowed_scope_keys": sorted(allowed), "required_scope_keys": list(required),
                    "unexpected_keys": sorted(set(scope) - allowed),
                    "missing_keys": [k for k in required if scope.get(k) in (None, "", [])],
                    "output_selection": ("Event tools compute all record channels; select the requested channel from the returned result. Do not put channels into Epoch creation scope."
                                         if deliverable in EVENT_CAPABILITIES else "Use declared channel window")}
        if scope.get("baseline") is not None:
            return self._error("TRANSFORM_NOT_ENABLED", "This mode does not authorize baseline correction")
        checks = checks or []
        dependencies = dependencies or []
        if not isinstance(checks, list) or any(x not in NUMERIC_TOOLS for x in checks):
            return self._error("INVALID_DEPENDENCY", "Checks must name registered tools")
        criteria = criteria or []
        if (not isinstance(criteria, list) or any(not isinstance(c, dict) or
                set(c) != {"tool", "path", "op", "value"} or c["tool"] not in NUMERIC_TOOLS or
                not isinstance(c["path"], list) or not c["path"] or
                c["op"] not in {"eq", "gte", "lte"} or
                type(c["value"]) not in {str, int, float, bool} for c in criteria)):
            return self._error("INVALID_CRITERION", "Criteria require a real observation path and eq/gte/lte scalar comparison")
        checks = list(dict.fromkeys(checks + [c["tool"] for c in criteria]))
        if (not isinstance(checks, list) or any(x not in NUMERIC_TOOLS for x in checks)
                or not isinstance(dependencies, list)
                or any(self.find_entry(x) is None for x in dependencies)):
            return self._error("INVALID_DEPENDENCY", "Checks must be registered tools; dependencies must be real completed tasks")
        if revision_of is not None:
            parent = self.find_entry(revision_of)
            if parent is None or (parent.record, parent.capability) != (record, deliverable):
                return self._error("INVALID_REVISION_PARENT", "Revision must retain its parent's record and scientific capability")
        goal = ScientificSubgoal(
            f"{self.session_id}-s{len(self.subgoals) + 1}", title, record, deliverable,
            clone(scope), list(dict.fromkeys(checks)), clone(criteria), revision_of, clone(dependencies),
            implicit=implicit, turn=self.turn,
        )
        self.active = goal
        self.subgoals.append(goal)
        self.active_record = record
        self.last_owner = goal.subgoal_id
        self.events.append({"event": "started", "subgoal_id": goal.subgoal_id,
                            "record": record, "implicit": implicit, "turn": self.turn})
        return {"status": "active", "subgoal_id": goal.subgoal_id,
                "contract": self.goal_card(goal)}

    def goal_card(self, goal):
        return {"subgoal_id": goal.subgoal_id, "title": goal.title,
                "record": goal.record, "deliverable": goal.deliverable,
                "scope": clone(goal.scope), "checks": goal.checks,
                "criteria": clone(goal.criteria),
                "revision_of": goal.revision_of, "dependencies": goal.dependencies,
                "status": goal.status, "task_id": goal.task_id,
                "unresolved": clone(goal.unresolved)}

    def _scope_error(self, goal, request, context):
        spec = context.executor.registry.get(request.name)
        args = dict(request.arguments)
        if spec.consumes_artifact:
            artifact = context.artifacts.get(args.get("artifact_id"))
            if artifact is None:
                return "ARTIFACT_NOT_FOUND"
            if goal.deliverable not in EVENT_CAPABILITIES:
                return "SCIENTIFIC_SCOPE_MISMATCH"
            actual = {"labels": list(artifact.parameters["selected_labels"]),
                      "tmin": artifact.tmin, "tmax": artifact.tmax}
            if artifact.baseline is not None:
                actual["baseline"] = list(artifact.baseline)
            if actual != goal.scope or artifact.source != context.record.source:
                return "SCIENTIFIC_SCOPE_MISMATCH"
        elif request.name == "create_epochs":
            if goal.deliverable not in EVENT_CAPABILITIES or args != goal.scope:
                return "SCIENTIFIC_SCOPE_MISMATCH"
        elif spec.requires_window or request.name == "record_quality":
            for key in ("channels", "start", "end"):
                if key in goal.scope and args.get(key) != goal.scope[key]:
                    return "SCIENTIFIC_SCOPE_MISMATCH"
            if goal.deliverable in EVENT_CAPABILITIES:
                return "SCIENTIFIC_SCOPE_MISMATCH"
        return None

    def execute_numeric(self, name, arguments):
        if name not in NUMERIC_TOOLS:
            return self._error("TOOL_NOT_AVAILABLE", "This research mode does not authorize this tool")
        if self.active is None:
            if name not in TERMINALS or name in EVENT_CAPABILITIES:
                return self._error("SUBGOAL_REQUIRED", "Declare an event scientific scope before artifact actions")
            started = self.begin_subgoal(name, self.active_record, name, arguments,
                                         implicit=True)
            if started["status"] != "active":
                return started
        goal = self.active
        self.last_owner = goal.subgoal_id
        if goal.status not in {"active", "blocked"}:
            return self._error("SUBGOAL_NOT_ACTIVE", "Resume the pending subgoal before execution")
        context = self.contexts[goal.record]
        self.sequence += 1
        request = ToolRequest(name, clone(arguments), f"{self.session_id}-a{self.sequence}")
        try:
            _validate_schema(arguments, context.executor.registry.get(name).parameters)
            mismatch = self._scope_error(goal, request, context)
        except (KeyError, ValueError, TypeError):
            mismatch = "INVALID_ARGUMENT"
        if mismatch:
            rendered = {"request_id": request.request_id, "tool_name": name,
                        "success": False, "data": None,
                        "error": {"code": mismatch, "message": "Tool input conflicts with the declared scope or schema"},
                        "duration_ms": 0}
        else:
            rendered = context.execute(request).to_dict()
        observation = {"request": {"name": name, "arguments": clone(arguments)},
                       "result": clone(rendered), "record": goal.record,
                       "scope": clone(goal.scope), "source": context.record.source}
        goal.observations.append(observation)
        goal.status = "active" if rendered["success"] else "blocked"
        goal.unresolved = [] if rendered["success"] else [rendered["error"]["code"]]
        out = {"status": "observed" if rendered["success"] else "blocked",
               "subgoal_id": goal.subgoal_id, "observation": observation}
        if goal.implicit and rendered["success"]:
            out["archive"] = self.close_subgoal("completed")
        return out

    def completion_check(self, goal):
        successful = [o for o in goal.observations if o["result"]["success"]]
        names = {o["request"]["name"] for o in successful}
        missing = (set(goal.checks) | {goal.deliverable}) - names
        if missing:
            return {"valid": False, "code": "DELIVERABLE_MISSING", "missing_tools": sorted(missing)}
        terminal = next(o for o in reversed(successful) if o["request"]["name"] == goal.deliverable)
        for criterion in goal.criteria:
            candidates = [o for o in successful if o["request"]["name"] == criterion["tool"]]
            if goal.deliverable in EVENT_CAPABILITIES:
                ident = terminal["request"]["arguments"]["artifact_id"]
                candidates = [o for o in candidates if o["result"]["data"].get("artifact_id") == ident]
            if not candidates:
                return {"valid": False, "code": "CHECK_ARTIFACT_MISMATCH"}
            observation = candidates[-1]
            try:
                value = observation["result"]["data"]
                for key in criterion["path"]:
                    value = value[key]
                target = criterion["value"]
                valid = (value == target if criterion["op"] == "eq" else
                         value >= target if criterion["op"] == "gte" else value <= target)
            except (KeyError, TypeError, IndexError):
                valid = False
            if not valid:
                return {"valid": False, "code": "CRITERION_NOT_SATISFIED", "criterion": criterion}
        if goal.deliverable in EVENT_CAPABILITIES:
            artifact_id = terminal["request"]["arguments"]["artifact_id"]
            for check in goal.checks:
                spec = self.contexts[goal.record].executor.registry.get(check)
                if spec.consumes_artifact and not any(
                        o["request"]["name"] == check and
                        o["request"]["arguments"].get("artifact_id") == artifact_id
                        for o in successful):
                    return {"valid": False, "code": "CHECK_ARTIFACT_MISMATCH"}
                if spec.produces_artifact and not any(
                        o["request"]["name"] == check and
                        o["result"]["data"].get("artifact_id") == artifact_id
                        for o in successful):
                    return {"valid": False, "code": "CHECK_ARTIFACT_MISMATCH"}
        # A terminal success followed by a failed required action is unresolved.
        last_by_tool = {o["request"]["name"]: o for o in goal.observations}
        if any(not last_by_tool[name]["result"]["success"]
               for name in set(goal.checks) | {goal.deliverable}):
            return {"valid": False, "code": "UNRESOLVED_TOOL_FAILURE"}
        return {"valid": True, "terminal": terminal}

    def close_subgoal(self, status, unresolved=None):
        goal = self.active
        if goal is None:
            return self._error("NO_ACTIVE_SUBGOAL", "There is no active subgoal")
        self.last_owner = goal.subgoal_id
        if status not in {"completed", "suspended"}:
            return self._error("INVALID_STATUS", "Close as completed or suspended")
        if status == "suspended":
            if not isinstance(unresolved, list) or not unresolved or not all(isinstance(x, str) for x in unresolved):
                return self._error("UNRESOLVED_REQUIRED", "Suspension must retain its unresolved question")
            goal.status = "suspended"
            goal.unresolved = clone(unresolved)
        else:
            check = self.completion_check(goal)
            if not check["valid"]:
                return {"status": "rejected", **check}
            terminal = check["terminal"]
            task_id = f"{self.session_id}-t{len(self.entries) + 1}"
            scope = clone(goal.scope)
            data = clone(terminal["result"]["data"])
            source = self.records[goal.record].source
            proof = {"record": goal.record, "source": source, "scope": scope,
                     "capability": goal.deliverable, "result": data,
                     "revision_of": goal.revision_of}
            record = self.records[goal.record]
            scientific_config = {"sfreq": record.sfreq, "reference": record.reference,
                                 "montage": record.montage,
                                 "processing_metadata": clone(list(record.processing_metadata)),
                                 "time_reference": "event_relative" if goal.deliverable in EVENT_CAPABILITIES else "record_absolute"}
            if goal.deliverable in {"psd", "event_bandpower"}:
                scientific_config["freq_bands"] = clone(self.config["freq_bands"])
            evidence = {"source": source, "source_stage": "event_epochs" if goal.deliverable in EVENT_CAPABILITIES else "loaded_record",
                        "analysis_configuration": scientific_config,
                        "unit_or_kind": RESULT_UNITS.get(goal.deliverable, "event metadata"),
                        "evidence_token": "wm:" + hashlib.sha256(encoded(proof)).hexdigest()}
            entry = TaskEntry(task_id, len(self.entries) + 1, goal.record, goal.deliverable,
                              scope, goal.title, goal.revision_of, "completed", data, evidence,
                              tuple(clone(o) for o in goal.observations))
            self.entries.append(entry)
            goal.task_id = task_id
            goal.status = "completed"
            goal.unresolved = []
        self.events.append({"event": "archived" if status == "completed" else "suspended",
                            "subgoal_id": goal.subgoal_id, "task_id": goal.task_id,
                            "reason": "verified_delivery" if status == "completed" else "unresolved",
                            "turn": self.turn})
        self.active = None
        return {"status": status, "summary": self.summary(goal)}

    def resume_subgoal(self, subgoal_id):
        goal = self.find_subgoal(subgoal_id)
        if self.active is not None and self.active is not goal:
            return self._error("ACTIVE_SUBGOAL", "Suspend or complete the other active subgoal")
        if goal is None or goal.status not in {"blocked", "suspended", "awaiting_input"}:
            return self._error("NOT_RESUMABLE", "Only a pending subgoal can resume unchanged")
        self.active = goal
        self.active_record = goal.record
        goal.status = "active"
        self.last_owner = goal.subgoal_id
        self.events.append({"event": "resumed", "subgoal_id": subgoal_id, "turn": self.turn})
        return {"status": "active", "contract": self.goal_card(goal)}

    def summary(self, goal):
        entry = self.find_entry(goal.task_id)
        result = self.goal_card(goal)
        result["action_outcomes"] = [
            {"tool": o["request"]["name"], "success": o["result"]["success"],
             "error": o["result"]["error"],
             "artifact_id": (o["result"].get("data") or {}).get("artifact_id")}
            for o in goal.observations]
        result["checked_facts"] = [
            {"tool": o["request"]["name"], "artifact_id": o["result"]["data"].get("artifact_id"),
             "facts": {k: clone(v) for k, v in o["result"]["data"].items()
                       if k in {"valid_epoch_count", "rejected_epoch_count", "epoch_counts",
                                "condition_counts_quality_usable", "validity", "threshold_status"}}}
            for o in goal.observations if o["result"]["success"] and
            o["request"]["name"] in {"create_epochs", "epoch_summary", "epoch_quality"}]
        if entry is not None:
            fields = list(scalar_paths(entry.result))
            # Fixed schema preview, independent of any future query/gold.
            result["evidence"] = {"task_id": entry.task_id, **clone(entry.evidence),
                                  "fields": [{"path": p, "value": v} for p, v in fields[:12]],
                                  "omitted_fields": max(0, len(fields) - 12),
                                  "readable_fields": [p for p, _ in fields[:64]]}
        return result

    def read_evidence(self, task_id, record, parameters, *, field_paths=None):
        entry = self.find_entry(task_id)
        if entry is None:
            return self._error("TASK_NOT_FOUND", "Task is not in this session")
        if entry.record != record or entry.parameters != parameters:
            return self._error("EVIDENCE_BINDING_MISMATCH", "Requested record/parameters differ from this exact task version")
        # Reuse the existing archive read and normalize against original facts.
        full = super().read_task(task_id, "", record_message=False)
        if field_paths is None:
            read = full
        else:
            if not isinstance(field_paths, list) or not 1 <= len(field_paths) <= 4:
                return self._error("FIELD_COUNT_INVALID", "Read one to four scalar fields")
            available = {encoded(path): value for path, value in scalar_paths(entry.result)}
            if any(encoded(path) not in available for path in field_paths):
                return self._error("FIELD_NOT_FOUND", "Use a canonical path from this task result")
            read = {key: value for key, value in full.items() if key not in {"result", "tool_trace"}}
            read.update(status="read_fields", fields=[{"path": path, "value": available[encoded(path)]}
                                                     for path in field_paths])
        proof = normalized_read(self, read)
        return {"status": "read", "evidence": proof}

    def restore_subgoal(self, subgoal_id):
        goal = self.find_subgoal(subgoal_id)
        if goal is None or goal is self.active:
            return self._error("TRAJECTORY_NOT_ARCHIVED", "Choose an archived or suspended subgoal")
        return {"status": "restored", "subgoal": self.goal_card(goal),
                "action_observations": clone(goal.observations),
                "native_exchanges": clone(goal.exchanges)}
