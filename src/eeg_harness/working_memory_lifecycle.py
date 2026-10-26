"""Opt-in scientifically grounded lifecycle on the existing working-memory store.

The model still interprets requests. This bounded source checker verifies quoted
typed values, exact prior objects and field contracts; it does not prove general
natural-language intent or supply a plan. No numerical executor lives here.
"""
import math
import re
from itertools import product

from .executor import _validate_schema
from .result_semantics import UnsupportedResultField, read_scalar, result_field_semantics
from .working_memory import NUMERIC_TOOLS, clone, encoded
from .working_memory_deliveries import DeliverySubgoal, MultiResultWorkingMemoryStore
from .research.integrated_method.v3 import EVENT_CAPABILITIES, REQUIRED_PARAMETERS


EVENT_TOOLS = set(EVENT_CAPABILITIES) | {"create_epochs"}
METADATA = {"record_info", "list_events"}
NUMBER = r"[-+]?\d+(?:\.\d+)?"
RANGE = re.compile(rf"(?<![A-Za-z0-9.])({NUMBER})\s*(?:秒|s)?\s*(?:到|至|—|–|~|～|to|,|，|-)\s*({NUMBER})(?![\d.])", re.I)


def field_contract(name, path, record, scope, config):
    """Describe available scalar fields without fabricating an observation.

    Dynamic address components are record channels, event labels and configured
    bands. An event result may later omit a condition with no usable epochs;
    that absence is checked after execution, separately from schema legality.
    """
    if not isinstance(path, list) or not path or any(type(p) not in {str, int} for p in path):
        return None
    p = tuple(path)
    labels = set(scope.get("labels", [e.label for e in record.events.events] if record.events else []))
    channels = set(scope.get("channels", record.channel_names))
    bands = set(config.get("freq_bands", {}))
    if name == "list_events":
        if p == ("event_count",) or len(p) == 2 and p[0] == "labels" and p[1] in labels:
            return "integer"
        if p in {("first_onset_seconds",), ("last_onset_seconds",)}:
            return "number"
        if p == ("time_reference",):
            return "string"
    if name == "amplitude" and len(p) == 2 and p[0] in channels and p[1] in {"mean_abs", "rms", "min_val", "max_val"}:
        return "number"
    if name == "psd" and len(p) == 2 and p[0] in channels and p[1] in bands:
        return "number"
    if name in {"record_info", "create_epochs", "epoch_summary"}:
        counts = ("sample_count", "channel_count") if name == "record_info" else ("valid_epoch_count", "rejected_epoch_count")
        quantities = ("sfreq", "duration_seconds") if name == "record_info" else ("sfreq", "tmin", "tmax")
        strings = ("reference", "montage") if name == "record_info" else ("artifact_id", "artifact_fingerprint", "reference")
        if p in {(k,) for k in counts}:
            return "integer"
        if p in {(k,) for k in quantities}:
            return "number"
        if p in {(k,) for k in strings}:
            return "string"
    if name == "event_bandpower":
        if p == ("frequency_resolution_hz",):
            return "number"
        if len(p) == 3 and p[:1] == ("conditions",) and p[1] in labels and p[2] == "epoch_count":
            return "integer"
        if len(p) == 5 and p[0] == "conditions" and p[1] in labels and p[2] == "channels" and p[3] in channels and p[4] in bands:
            return "number"
        if p in {(k,) for k in ("artifact_id", "artifact_fingerprint", "method", "interpretation")}:
            return "string"
    if name == "epoch_quality":
        if len(p) == 2 and p[0] == "epoch_counts" and p[1] in {"requested_or_boundary_checked", "created", "boundary_rejected", "quality_flagged", "quality_usable"}:
            return "integer"
        if len(p) == 2 and p[0] in {"condition_counts_before_quality", "condition_counts_quality_usable"} and p[1] in labels:
            return "integer"
        if p == ("usable_fraction_of_created",):
            return "number"
        if p in {(k,) for k in ("threshold_status", "validity", "artifact_id", "artifact_fingerprint")}:
            return "string"
    return None


class ReliableWorkingMemoryStore(MultiResultWorkingMemoryStore):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_requests = []

    def _quote(self, source):
        if not isinstance(source, dict) or source.get("kind") != "user":
            return None
        turn, quote = source.get("turn", len(self.user_requests)), source.get("quote")
        if type(turn) is not int or not 1 <= turn <= len(self.user_requests) or not isinstance(quote, str) or not quote:
            return None
        return quote if quote in self.user_requests[turn-1] else None

    def _user_source(self):
        return {"kind": "user", "turn": len(self.user_requests), "quote": self.user_requests[-1] if self.user_requests else ""}

    def _mentioned_records(self, quote):
        return {key for key in self.records if re.search(r"(?:记录|record)\s*" + re.escape(key) + r"(?![A-Za-z0-9])", quote, re.I)}

    def _source_ok(self, key, value, scope, record, source, *, name):
        if not isinstance(source, dict):
            return False
        kind = source.get("kind")
        if kind == "user":
            quote = self._quote(source)
            if quote is None:
                return False
            mentions = self._mentioned_records(quote)
            if mentions and mentions != {record}:
                return False
            whole = self.user_requests[source.get("turn", len(self.user_requests))-1]
            whole_mentions = self._mentioned_records(whole)
            if (whole_mentions and record not in whole_mentions or
                    len(whole_mentions) > 1 and mentions != {record}):
                return False
            if key in {"channels", "labels"}:
                return isinstance(value, list) and all(isinstance(x, str) and re.search(r"(?<![A-Za-z0-9_-])"+re.escape(x)+r"(?![A-Za-z0-9_-])", quote) for x in value)
            if key in {"start", "end", "tmin", "tmax"}:
                pair = ("tmin", "tmax") if key in {"tmin", "tmax"} else ("start", "end")
                if all(k in scope for k in pair):
                    ranges = {(float(a), float(b)) for a, b in RANGE.findall(quote)}
                    return ranges == {(float(scope[pair[0]]), float(scope[pair[1]]))}
                numbers = {float(x) for x in re.findall(rf"(?<![A-Za-z0-9.])({NUMBER})(?![\d.])", quote)}
                return float(value) in numbers
            return False
        entry = None
        if kind == "result":
            entry = self.find_entry(source.get("result_id"))
            if entry is None or entry.record != record or not self._binding_valid(entry):
                return False
            if (entry.capability in EVENT_TOOLS) != (name in EVENT_TOOLS):
                return False
            return key in entry.parameters and entry.parameters[key] == value
        if kind == "artifact":
            ident = source.get("artifact_id")
            artifact = self.contexts[record].artifacts.get(ident)
            if artifact is None or name not in EVENT_TOOLS:
                return False
            # The artifact must have an actual, already grounded result owner.
            entry = next((e for e in self.entries if e.record == record and e.evidence.get("binding", {}).get("artifact_id") == ident and self._binding_valid(e)), None)
            return entry is not None and key in entry.parameters and entry.parameters[key] == value
        if kind == "profile":
            # Current profiles prescribe preprocessing, not user analysis windows.
            # No such defaults are registered here; do not trust an LLM's claim.
            return False
        return False

    def _sources_check(self, deliveries, record, sources):
        issues, verified = [], {}
        for item in deliveries:
            key, scope, name = item["key"], item["scope"], item["tool"]
            required = ("labels", "tmin", "tmax") if name in EVENT_TOOLS else REQUIRED_PARAMETERS.get(name, ())
            given = sources.get(key, self._user_source())
            verified[key] = {}
            for field in set(required) | (set(scope) & {"channels", "start", "end", "labels", "tmin", "tmax"}):
                if field not in scope:
                    issues.append({"delivery": key, "field": field, "code": "MISSING_SCIENTIFIC_PARAMETER"})
                    continue
                source = given.get("fields", {}).get(field, given) if isinstance(given, dict) else None
                if not self._source_ok(field, scope[field], scope, record, source, name=name):
                    issues.append({"delivery": key, "field": field, "code": "UNVERIFIED_PARAMETER_SOURCE"})
                else:
                    verified[key][field] = clone(source)
        return issues, verified

    @staticmethod
    def _remember_sources(sources, verified):
        saved = clone(sources)
        for key, fields in verified.items():
            original = saved.get(key, {})
            saved[key] = {"fields": {**(original.get("fields", {}) if isinstance(original, dict) else {}), **clone(fields)}}
        return saved

    def _criteria_check(self, criteria, deliveries, record, sources):
        for index, c in enumerate(criteria):
            if not isinstance(c, dict) or set(c) != {"delivery", "path", "op", "value"}:
                return self._error("INVALID_CRITERION", "Use delivery, canonical path, op and value")
            delivery = next((d for d in deliveries if d["key"] == c["delivery"]), None)
            if delivery is None:
                return self._error("INVALID_CRITERION_REFERENCE", "Criterion delivery must be a local delivery key")
            kind = field_contract(delivery["tool"], c["path"], self.records[record], delivery["scope"], self.config)
            if kind is None:
                return {**self._error("UNKNOWN_RESULT_FIELD", "Use a registered output address; no future observation is invented"),
                        "criterion": index, "tool": delivery["tool"], "path": c["path"]}
            numeric = type(c["value"]) in {int, float} and math.isfinite(c["value"])
            if (c["op"] not in {"eq", "gte", "lte"} or
                    kind == "string" and (c["op"] != "eq" or not isinstance(c["value"], str)) or
                    kind in {"integer", "number"} and not numeric or
                    kind == "integer" and type(c["value"]) is not int):
                return self._error("CRITERION_TYPE_MISMATCH", "Operator and value must match the actual field quantity type")
            source = sources.get("criteria", {}).get(str(index), {})
            quote = self._quote(source)
            operators = {"eq": r"(?<![<>!=])=(?!=)|(?<!不)等于|(?<!not )\bequal\b",
                         "gte": r">=|≥|至少|不低于|\bat least\b", "lte": r"<=|≤|至多|不超过|\bat most\b"}
            matched_ops = {op for op, pattern in operators.items() if quote and re.search(pattern, quote, re.I)}
            if not quote or matched_ops != {c["op"]}:
                return self._error("UNGROUNDED_CRITERION", "An acceptance threshold needs an explicit quoted user condition; a count query has no implied minimum")
            whole_mentions = self._mentioned_records(self.user_requests[source.get("turn", len(self.user_requests))-1])
            if (self._mentioned_records(quote) and self._mentioned_records(quote) != {record} or
                    whole_mentions and record not in whole_mentions or
                    len(whole_mentions) > 1 and self._mentioned_records(quote) != {record}):
                return self._error("UNGROUNDED_CRITERION", "The acceptance condition belongs to a different or ambiguous record")
            dynamic = set(self.records[record].channel_names) | {e.label for e in self.records[record].events.events} if self.records[record].events else set(self.records[record].channel_names)
            dynamic |= set(self.config.get("freq_bands", {}))
            if any(p in dynamic and not re.search(r"(?<![A-Za-z0-9_-])"+re.escape(p)+r"(?![A-Za-z0-9_-])", quote) for p in c["path"] if isinstance(p, str)):
                return self._error("UNGROUNDED_CRITERION", "Quoted acceptance condition must identify the addressed channel/condition")
            if numeric:
                numbers = {float(x) for x in re.findall(rf"(?<![A-Za-z0-9.])({NUMBER})(?![\d.])", quote)}
                if float(c["value"]) not in numbers:
                    return self._error("UNGROUNDED_CRITERION", "The threshold must match the quoted user value")
            elif c["value"] not in quote:
                return self._error("UNGROUNDED_CRITERION", "The compared value is absent from the user quote")
        return None

    def begin_subgoal(self, title, record, deliverable=None, scope=None, *, deliveries=None,
                      checks=None, revision_of=None, dependencies=None, criteria=None, implicit=False,
                      parameter_sources=None):
        sources = clone(parameter_sources or {})
        if not isinstance(sources, dict) or record not in self.records or not isinstance(title, str) or not title.strip():
            return self._error("INVALID_SUBGOAL", "Known record, nonempty title and source map required")
        if deliveries is None:
            deliveries = [{"key": "main", "tool": deliverable, "scope": scope or {},
                           **({"revision_of": revision_of} if revision_of else {})}]
            for name in checks or []:
                if name != deliverable:
                    deliveries.append({"key": name, "tool": name, "scope": {} if name in METADATA else scope or {}})
        if not isinstance(deliveries, list) or not 1 <= len(deliveries) <= 12:
            return self._error("INVALID_DELIVERIES", "Declare one to twelve deliveries")
        ds = clone(deliveries)
        registry = self.contexts[record].executor.registry
        for d in ds:
            if not isinstance(d, dict) or set(d) - {"key", "tool", "scope", "required", "revision_of"}:
                return self._error("INVALID_DELIVERY", "Unknown delivery fields")
            if not isinstance(d.get("key"), str) or not d["key"] or d.get("tool") not in NUMERIC_TOOLS or not isinstance(d.get("scope"), dict):
                return self._error("INVALID_DELIVERY", "Each delivery needs a key, enabled tool and partial or full scope")
            if type(d.get("required", True)) is not bool:
                return self._error("INVALID_DELIVERY", "Required must be boolean")
            d["required"], d["revision_of"] = d.get("required", True), d.get("revision_of")
            if d["revision_of"]:
                parent = self.find_entry(d["revision_of"])
                if parent is None or (parent.record, parent.capability) != (record, d["tool"]):
                    return self._error("INVALID_REVISION_PARENT", "Revision needs exact same-record/capability prior result")
                d["revision_of"] = parent.task_id
            schema = clone(registry.get("create_epochs" if d["tool"] in EVENT_TOOLS else d["tool"]).parameters)
            schema["required"] = []
            try:
                _validate_schema(d["scope"], schema)
            except (ValueError, TypeError):
                return self._error("INVALID_SCOPE", "Provided scope fields violate the original tool schema")
            if d["tool"] in EVENT_TOOLS and set(d["scope"]) - {"labels", "tmin", "tmax"}:
                return self._error("INVALID_SCOPE", "Event scope is labels/tmin/tmax; no implicit processing transform")
        if len({d["key"] for d in ds}) != len(ds) or not any(d["required"] for d in ds):
            return self._error("DUPLICATE_OR_EMPTY_CONTRACT", "Unique delivery keys and at least one required result are needed")
        if any(self.find_entry(ident) is None for ident in dependencies or []):
            return self._error("INVALID_DEPENDENCY", "Dependencies identify existing result IDs, not future delivery keys or artifact IDs")
        criteria = clone(criteria or [])
        if not isinstance(criteria, list):
            return self._error("INVALID_CRITERION", "Criteria must be a list")
        invalid = self._criteria_check(criteria, ds, record, sources)
        if invalid:
            return invalid
        # Repeated same unfinished purpose is idempotent within its originating
        # request; explicit later recalculation remains possible as a new goal.
        for g in self.subgoals:
            if g.turn == self.turn and g.status != "completed" and (g.record, g.title, g.deliveries, g.criteria) == (record, title, ds, criteria):
                self.last_owner = g.subgoal_id
                return {"status": "unchanged", "subgoal_id": g.subgoal_id, "progress": self.summary(g)}
        if self.active is not None:
            return self._error("ACTIVE_SUBGOAL", "Complete or suspend current work first")
        issues, verified = self._sources_check(ds, record, sources)
        # An explicit record transition must agree with the user or an exact
        # source object; metadata queries themselves are harmless read actions.
        if record != self.active_record and any(d["tool"] not in METADATA for d in ds):
            selected_source = sources.get("record", self._user_source())
            quote = self._quote(selected_source)
            selected_entry = self.find_entry(selected_source.get("result_id")) if isinstance(selected_source, dict) else None
            if not (quote and self._mentioned_records(quote) == {record} or selected_entry and selected_entry.record == record):
                issues.append({"delivery": None, "field": "record", "code": "UNVERIFIED_RECORD_SELECTION"})
        first = ds[0]
        goal = DeliverySubgoal(subgoal_id=f"{self.session_id}-s{len(self.subgoals)+1}", title=title,
            record=record, deliverable=first["tool"], scope=clone(first["scope"]), checks=[], criteria=criteria,
            dependencies=[self.find_entry(x).task_id for x in dependencies or []], implicit=implicit,
            turn=self.turn, deliveries=ds, status="awaiting_input" if issues else "active")
        goal.parameter_sources, goal.verified_sources, goal.admission_issues = self._remember_sources(sources, verified), verified, issues
        goal.contract_revisions = []
        goal.unresolved = [f"{i['delivery'] or 'record'}.{i['field']}: {i['code']}" for i in issues]
        self.subgoals.append(goal)
        self.active, self.active_record, self.last_owner = goal, record, goal.subgoal_id
        self.events.append({"event": "awaiting_input" if issues else "admitted", "subgoal_id": goal.subgoal_id,
                            "turn": self.turn, "issues": clone(issues)})
        return {"status": goal.status, "subgoal_id": goal.subgoal_id, "contract": self.goal_card(goal),
                "issues": clone(issues), "next_action": "ask missing scientific choices, then amend_subgoal" if issues else "execute missing deliveries; successes are linked automatically"}

    def goal_card(self, goal):
        card = super().goal_card(goal)
        card.update(contract_version="reliable_lifecycle_v1", parameter_sources=clone(getattr(goal, "verified_sources", {})),
                    admission_issues=clone(getattr(goal, "admission_issues", [])),
                    contract_revisions=clone(getattr(goal, "contract_revisions", [])))
        card["references"] = {"subgoal_id": goal.subgoal_id, "delivery_keys": [d["key"] for d in goal.deliveries],
                              "result_ids": clone(goal.result_ids),
                              "meaning": "delivery keys name required outputs; dependencies/revision_of need actual result_ids; artifacts come from tool results"}
        card["output_contracts"] = {d["key"]: self.output_contract(d["tool"], goal.record, d["scope"]) for d in goal.deliveries}
        return card

    def output_contract(self, tool, record, scope):
        labels = scope.get("labels", sorted({e.label for e in self.records[record].events.events}) if self.records[record].events else [])
        channels = scope.get("channels", list(self.records[record].channel_names))
        bands = list(self.config.get("freq_bands", {}))
        patterns = {"list_events": [["event_count"], ["labels", "<label>"]],
                    "record_info": [["sfreq"], ["channel_count"], ["sample_count"], ["duration_seconds"]],
                    "amplitude": [["<channel>", k] for k in ("rms", "mean_abs", "min_val", "max_val")],
                    "psd": [["<channel>", "<band>"]],
                    "event_bandpower": [["conditions", "<label>", "epoch_count"], ["conditions", "<label>", "channels", "<channel>", "<band>"], ["frequency_resolution_hz"]],
                    "create_epochs": [["valid_epoch_count"], ["rejected_epoch_count"], ["artifact_id"]],
                    "epoch_summary": [["valid_epoch_count"], ["rejected_epoch_count"], ["artifact_id"]],
                    "epoch_quality": [["epoch_counts", "created"], ["epoch_counts", "quality_usable"], ["threshold_status"]]}
        return {"scalar_path_templates": patterns.get(tool, []), "labels": labels, "channels": channels,
                "bands": bands, "notice": "Schema addresses only, not future values. Missing output is checked after execution."}

    def amend_subgoal(self, subgoal_id, updates=None, parameter_sources=None, criterion_paths=None):
        goal = self.find_subgoal(subgoal_id)
        if goal is None or goal.status == "completed":
            return self._error("NOT_AMENDABLE", "Only pending objectives may be supplemented or technically corrected")
        if self.active not in (None, goal):
            return self._error("ACTIVE_SUBGOAL", "Suspend or complete unrelated current work first")
        old = self.goal_card(goal)
        ds, cs = clone(goal.deliveries), clone(goal.criteria)
        updates = updates or {}
        if not isinstance(updates, dict) or not isinstance(parameter_sources or {}, dict) or not isinstance(criterion_paths or {}, dict):
            return self._error("INVALID_AMENDMENT", "Use delivery-keyed fields/sources and criterion-indexed paths")
        for key, fields in updates.items():
            d = next((d for d in ds if d["key"] == key), None)
            if d is None or not isinstance(fields, dict):
                return self._error("INVALID_AMENDMENT", "Supplement existing delivery keys only")
            for name, value in fields.items():
                if name in getattr(goal, "verified_sources", {}).get(key, {}) and d["scope"].get(name) != value:
                    return self._error("SCIENTIFIC_REVISION_REQUIRED", "Known scientific scope is immutable; declare a new version referencing the old result")
                d["scope"][name] = value
        for index, path in (criterion_paths or {}).items():
            try:
                i = int(index)
                c = cs[i]
                d = next(d for d in ds if d["key"] == c["delivery"])
                valid_old = field_contract(d["tool"], c["path"], self.records[goal.record], d["scope"], self.config)
                valid_new = field_contract(d["tool"], path, self.records[goal.record], d["scope"], self.config)
                desc = self.output_contract(d["tool"], goal.record, d["scope"])
                substitutions = {"<channel>": desc["channels"], "<label>": desc["labels"], "<band>": desc["bands"]}
                candidates = {tuple(p) for template in desc["scalar_path_templates"]
                              for p in product(*(substitutions.get(part, [part]) for part in template))
                              if list(p)[-len(c["path"]):] == c["path"]}
                if valid_old or not valid_new or not isinstance(path, list) or candidates != {tuple(path)}:
                    raise ValueError
                c["path"] = clone(path)
            except (IndexError, TypeError, ValueError, StopIteration):
                return self._error("NOT_TECHNICAL_CORRECTION", "Only an invalid shorthand path may expand to its same-field canonical address; thresholds/requirements cannot change")
        sources = clone(getattr(goal, "parameter_sources", {}))
        for key, incoming in (parameter_sources or {}).items():
            if key in {d["key"] for d in ds}:
                old_fields = clone(getattr(goal, "verified_sources", {}).get(key, {}))
                if isinstance(incoming, dict) and "fields" in incoming:
                    old_fields.update(clone(incoming["fields"]))
                else:
                    target = next(d for d in ds if d["key"] == key)
                    for f in target["scope"]:
                        if f not in old_fields or f in updates.get(key, {}):
                            old_fields[f] = clone(incoming)
                sources[key] = {"fields": old_fields}
            else:
                sources[key] = clone(incoming)
        for key, fields in updates.items():
            mapping = sources.setdefault(key, {}).setdefault("fields", {})
            for name in fields:
                if name not in mapping:
                    mapping[name] = self._user_source()
        invalid = self._criteria_check(cs, ds, goal.record, sources)
        if invalid:
            return invalid
        registry = self.contexts[goal.record].executor.registry
        for d in ds:
            schema = clone(registry.get("create_epochs" if d["tool"] in EVENT_TOOLS else d["tool"]).parameters)
            schema["required"] = []
            try:
                _validate_schema(d["scope"], schema)
            except (ValueError, TypeError):
                return self._error("INVALID_SCOPE", "Supplement violates tool input schema")
        issues, verified = self._sources_check(ds, goal.record, sources)
        if any(i["code"] == "UNVERIFIED_RECORD_SELECTION" for i in getattr(goal, "admission_issues", [])):
            selected = sources.get("record", {})
            quoted = self._quote(selected)
            entry = self.find_entry(selected.get("result_id")) if isinstance(selected, dict) else None
            if not (quoted and self._mentioned_records(quoted) == {goal.record} or entry and entry.record == goal.record and self._binding_valid(entry)):
                issues.append({"delivery": None, "field": "record", "code": "UNVERIFIED_RECORD_SELECTION"})
        goal.deliveries, goal.criteria, goal.scope = ds, cs, clone(ds[0]["scope"])
        goal.parameter_sources, goal.verified_sources, goal.admission_issues = self._remember_sources(sources, verified), verified, issues
        goal.contract_revisions.append({"turn": self.turn, "kind": "technical_correction" if criterion_paths else "parameter_supplement",
                                        "before": {"deliveries": old["deliveries"], "criteria": old["criteria"]},
                                        "updates": clone(updates), "criterion_paths": clone(criterion_paths or {})})
        goal.status = "awaiting_input" if issues else "active"
        goal.unresolved = [f"{i['delivery']}.{i['field']}: {i['code']}" for i in issues]
        self.active, self.active_record, self.last_owner = goal, goal.record, goal.subgoal_id
        self.events.append({"event": "contract_amended", "subgoal_id": goal.subgoal_id, "turn": self.turn,
                            "retained_result_ids": clone(goal.result_ids), "issues": clone(issues)})
        return {"status": goal.status, "subgoal_id": goal.subgoal_id, "contract": self.goal_card(goal), "progress": self.completion_check(goal)}

    def completion_check(self, goal):
        result = super().completion_check(goal)
        if getattr(goal, "admission_issues", []):
            result.update(valid=False, code="SCIENTIFIC_PARAMETERS_UNCONFIRMED", admission_issues=clone(goal.admission_issues))
            return result
        for d, state in zip(goal.deliveries, result["deliveries"]):
            if state["status"] not in {"satisfied", "condition_unsatisfied"}:
                continue
            entry = self.find_entry(state["result_id"])
            for c in (c for c in goal.criteria if c["delivery"] == d["key"]):
                expected = field_contract(d["tool"], c["path"], self.records[goal.record], d["scope"], self.config)
                if expected is None:
                    state.update(status="invalid_condition", error_code="UNKNOWN_RESULT_FIELD")
                    break
                try:
                    value = read_scalar(entry.result, c["path"])
                except UnsupportedResultField:
                    state.update(status="invalid_condition", error_code="RESULT_FIELD_ABSENT")
                    break
                try:
                    if d["tool"] != "list_events":
                        result_field_semantics(d["tool"], c["path"], entry.result, parameters=entry.parameters, analysis_configuration=entry.evidence["analysis_configuration"])
                    valid_type = isinstance(value, str) if expected == "string" else type(value) is int if expected == "integer" else type(value) in {str, float, int} and math.isfinite(float(value))
                    if not valid_type:
                        raise ValueError
                    if expected in {"integer", "number"}:
                        value = float(value)
                    ok = value == c["value"] if c["op"] == "eq" else value >= c["value"] if c["op"] == "gte" else value <= c["value"]
                except (TypeError, ValueError, UnsupportedResultField):
                    state.update(status="invalid_condition", error_code="RESULT_FIELD_TYPE_MISMATCH")
                    break
                if not ok:
                    state.update(status="condition_unsatisfied", error_code="DATA_CONDITION_NOT_MET")
                    break
                state["status"] = "satisfied"
        result["valid"] = all(s["status"] == "satisfied" for s in result["deliveries"] if s["required"])
        result["code"] = None if result["valid"] else next((s.get("error_code") for s in result["deliveries"] if s["required"] and s.get("error_code")), "INCOMPLETE_DELIVERIES")
        return result

    def execute_numeric(self, name, arguments, parameter_sources=None, record=None):
        if record is not None:
            if record not in self.records:
                return self._error("RECORD_NOT_FOUND", "Choose a visible record alias")
            if self.active is not None and self.active.record != record:
                return self._error("ACTIVE_RECORD_MISMATCH", "An action cannot silently change the active objective's record")
            if record != self.active_record and name not in METADATA:
                quote = self._quote(parameter_sources or self._user_source())
                if not quote or self._mentioned_records(quote) != {record}:
                    return self._error("UNVERIFIED_RECORD_SELECTION", "Use a quoted scientific request for the selected record")
            if record != self.active_record:
                self.events.append({"event": "record_selected", "record": record, "turn": self.turn})
                self.active_record = record
        if name in METADATA and self.active and self.active.status == "awaiting_input":
            pending = self.active
            self.active = None
            out = super().execute_numeric(name, arguments)
            self.active = pending
            return out
        if self.active is not None and getattr(self.active, "admission_issues", []):
            return {**self._error("SCIENTIFIC_PARAMETERS_UNCONFIRMED", "Ask for missing choices; use amend_subgoal after the user's reply"),
                    "subgoal_id": self.active.subgoal_id, "issues": clone(self.active.admission_issues)}
        if self.active is None and name not in METADATA:
            if name in EVENT_TOOLS:
                return self._error("SUBGOAL_REQUIRED", "Declare an event purpose and grounded scope before numerical artifact actions")
            started = self.begin_subgoal(name, self.active_record, name, arguments,
                implicit=True, parameter_sources={"main": parameter_sources or self._user_source()})
            if started["status"] != "active":
                return started
        out = super().execute_numeric(name, arguments)
        goal = self.find_subgoal(out.get("subgoal_id"))
        if goal:
            out["progress"] = self.completion_check(goal)
            out["next_action"] = "All required deliveries satisfied: close_subgoal; do not bind newly computed results again" if out["progress"]["valid"] else "Continue only missing deliveries, or clarify unresolved conditions"
        return out

    def reuse_result(self, delivery_key, task_id):
        goal = self.active
        entry = self.find_entry(task_id)
        if goal and entry:
            state = next((s for s in self.completion_check(goal)["deliveries"] if s["key"] == delivery_key), None)
            if state and state["result_id"] == entry.task_id and state["status"] == "satisfied":
                self.last_owner = goal.subgoal_id
                return {"status": "unchanged", "task_id": entry.task_id, "progress": self.completion_check(goal),
                        "message": "Already linked automatically or previously reused; no scientific progress or recomputation"}
        return super().reuse_result(delivery_key, task_id)

    def resume_subgoal(self, subgoal_id):
        goal = self.find_subgoal(subgoal_id)
        if goal and getattr(goal, "admission_issues", []):
            return {**self._error("SCIENTIFIC_PARAMETERS_UNCONFIRMED", "Supplement pending scientific choices using amend_subgoal"), "issues": clone(goal.admission_issues)}
        return super().resume_subgoal(subgoal_id)
