"""Action-local scientific admission and automatic factual task bookkeeping.

This opt-in store reuses the original numerical Executor, observation archive,
binding checks and multi-result task objects. The model chooses scientific
actions; it does not restate per-field provenance or maintain result identities.
Literal grounding is deliberately bounded: it checks typed values and their
co-occurrence, not the full meaning or completeness of arbitrary language.
"""
import re

from .executor import _validate_schema
from .working_memory import NUMERIC_TOOLS, WorkingMemoryStore, clone, encoded
from .working_memory_deliveries import DeliverySubgoal, MultiResultWorkingMemoryStore
from .working_memory_lifecycle import ReliableWorkingMemoryStore, EVENT_TOOLS, METADATA, RANGE, NUMBER
from .research.integrated_method.v3 import REQUIRED_PARAMETERS


class ActionWorkingMemoryStore(MultiResultWorkingMemoryStore):
    """Scientific actions are checked individually; tasks are memory units."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_requests = []
        self.admitted_scopes = []
        self.recompute_used = set()
        self._action_sources = None

    def focus_task(self, title, record=None, expected_tools=None):
        record = record or self.active_record
        expected = expected_tools or []
        if (not isinstance(title, str) or not title.strip() or len(title) > 400 or
                record not in self.records or not isinstance(expected, list) or
                len(expected) > 12 or any(t not in NUMERIC_TOOLS for t in expected)):
            return self._error("INVALID_TASK", "A short purpose, known record and optional enabled expected tools are required")
        if self.active and self.active.title == title and self.active.record == record:
            # A repeat focus is not a new task or fresh numerical permission.
            self.active.expected_tools = list(dict.fromkeys(self.active.expected_tools + expected))
            return {"status": "active", "task": self.summary(self.active)}
        if self.active:
            self.settle_active()
        pending = [g for g in self.subgoals if g.status == "suspended" and g.title == title and g.record == record]
        if len(pending) == 1:
            goal = pending[0]
            goal.status = "active"
            goal.expected_tools = list(dict.fromkeys(goal.expected_tools + expected))
            self.active, self.active_record, self.last_owner = goal, record, goal.subgoal_id
            self.events.append({"event": "task_resumed", "subgoal_id": goal.subgoal_id, "turn": self.turn})
            return {"status": "active", "task": self.summary(goal)}
        goal = DeliverySubgoal(subgoal_id=f"{self.session_id}-s{len(self.subgoals)+1}",
            title=title, record=record, deliverable="", scope={}, checks=[], turn=self.turn)
        goal.expected_tools = list(dict.fromkeys(expected))
        goal.pending_actions = []
        goal.scientific_facts = []
        goal.pinned_artifacts = {}
        self.active = goal
        self.active_record = record
        self.last_owner = goal.subgoal_id
        self.subgoals.append(goal)
        self.events.append({"event": "task_focused", "subgoal_id": goal.subgoal_id,
                            "record": record, "turn": self.turn})
        return {"status": "active", "task": self.summary(goal)}

    def goal_card(self, goal):
        card = super().goal_card(goal)
        card.update(contract_version="action_local_v1",
                    expected_tools=clone(getattr(goal, "expected_tools", [])),
                    pending_actions=clone(getattr(goal, "pending_actions", [])),
                    scientific_facts=clone(getattr(goal, "scientific_facts", [])))
        return card

    def completion_check(self, goal):
        base = super().completion_check(goal)
        successful = {self.find_entry(i).capability for i in goal.result_ids + list(goal.reused.values())
                      if self.find_entry(i) and self._binding_valid(self.find_entry(i))}
        missing = sorted(set(getattr(goal, "expected_tools", [])) - successful)
        pending = clone(getattr(goal, "pending_actions", []))
        base.update(missing_tools=missing, pending_actions=pending)
        base["valid"] = bool(successful) and base["valid"] and not missing and not pending
        base["code"] = None if base["valid"] else "TASK_DELIVERY_PENDING"
        return base

    def summary(self, goal):
        card = super().summary(goal)
        card["available_control"] = (
            "Archival is automatic. Continue scientific work with focus_task or a numerical action; "
            "read_result accesses exact evidence, restore_task accesses its actual process; "
            "finish_task delivers a complete, partial or clarification answer.")
        return card

    def settle_active(self, unresolved=None):
        """Program-owned bookkeeping at task switch or response boundary."""
        if self.active is None:
            return {"status": "unchanged"}
        goal = self.active
        check = self.completion_check(goal)
        if check["valid"]:
            return super().close_subgoal("completed")
        missing = list(unresolved or []) + [f"Missing actual tool result: {t}" for t in check["missing_tools"]]
        missing += [p["code"] + ": " + p["tool"] for p in check["pending_actions"]]
        return super().close_subgoal("suspended", unresolved=missing or ["Scientific purpose not fully delivered"])

    @staticmethod
    def _family(name):
        return "event" if name in EVENT_TOOLS else "continuous"

    def _source_text(self, request_span):
        whole = self.user_requests[-1] if self.user_requests else ""
        if request_span is None:
            return whole
        if not isinstance(request_span, str) or not request_span.strip() or request_span not in whole:
            return None
        return request_span

    @staticmethod
    def _contains(text, value):
        return bool(re.search(r"(?<![A-Za-z0-9_-])" + re.escape(value) + r"(?![A-Za-z0-9_-])", text))

    def _mentioned_records(self, text):
        return ReliableWorkingMemoryStore._mentioned_records(self, text)

    def _quote(self, source):
        return ReliableWorkingMemoryStore._quote(self, source)

    def _scientific_clauses(self, text, anchors):
        """Split ordinary punctuation while preserving typed lists/ranges.

        This uses literal metadata identities, not vocabulary for EEG tasks.
        Commas within an object list or numeric interval are not boundaries.
        """
        starts, pieces = 0, []
        for delimiter in re.finditer(r"[;；。\n,，]", text):
            if delimiter.group() in {",", "，"}:
                left, right = text[:delimiter.start()], text[delimiter.end():]
                numeric_pair = (re.search(rf"(?<![A-Za-z0-9_.-])({NUMBER})\s*$", left) and
                                re.match(rf"\s*({NUMBER})(?![A-Za-z0-9_.])", right))
                object_pair = (any(re.search(r"(?<![A-Za-z0-9_-])" + re.escape(x) + r"\s*$", left) for x in anchors) and
                               any(re.match(r"\s*" + re.escape(x) + r"(?![A-Za-z0-9_-])", right) for x in anchors))
                if numeric_pair or object_pair:
                    continue
            pieces.append(text[starts:delimiter.start()])
            starts = delimiter.end()
        pieces.append(text[starts:])
        return [p for p in pieces if p.strip()]

    def _pending(self, name, arguments, code, message, **details):
        goal = self.active
        if goal:
            row = {"tool": name, "arguments": clone(arguments), "code": code, "message": message, **details}
            goal.pending_actions = [p for p in goal.pending_actions
                                    if (p["tool"], p["arguments"]) != (name, arguments)] + [row]
            goal.unresolved = [p["code"] + ": " + p["tool"] for p in goal.pending_actions]
            self.last_owner = goal.subgoal_id
            self.events.append({"event": "action_not_admitted", "subgoal_id": goal.subgoal_id,
                                "tool": name, "code": code, "turn": self.turn})
        return {**self._error(code, message), **details,
                "independent_actions_remain_available": True,
                "subgoal_id": goal.subgoal_id if goal else None}

    def _ground_scope(self, name, scope, record, text, inherited):
        """Return confirmed sources and unresolved fields; never infer values."""
        family = self._family(name)
        required = ("labels", "tmin", "tmax") if name in EVENT_TOOLS else REQUIRED_PARAMETERS.get(name, ())
        missing = [k for k in required if scope.get(k) in (None, "", [])]
        known = {}
        current_fingerprint = self._binding(self.contexts[record], name)["record_fingerprint"]
        if inherited:
            for key, value in scope.items():
                if key in inherited.parameters and inherited.parameters[key] == value:
                    known[key] = {"kind": "result", "result_id": inherited.task_id, "field": key}
        object_key = "labels" if family == "event" else "channels"
        if self.active:
            for fact in self.active.scientific_facts:
                if (fact["record"] == record and fact["family"] == family and
                        fact["scope"].get(object_key) == scope.get(object_key) and
                        fact["record_fingerprint"] == current_fingerprint):
                    # Never form a Cartesian product of independent scientific
                    # scopes. A full fact supplies its range only as one coherent
                    # scope; identity alone may survive a new user window.
                    coherent = all(scope.get(k) == v for k, v in fact["scope"].items())
                    for key, value in fact["scope"].items():
                        if (coherent or key == object_key) and scope.get(key) == value and key in fact["sources"]:
                            known.setdefault(key, clone(fact["sources"][key]))
        for fact in self.admitted_scopes:
            if (fact["record"], fact["family"], fact["scope"], fact["record_fingerprint"]) == (record, family, scope, current_fingerprint):
                known.update(clone(fact["sources"]))
        anchors = list(scope.get("labels" if family == "event" else "channels", []))
        pieces = self._scientific_clauses(text, anchors)
        source_record = self.contexts[record].record
        event_labels = list({e.label for e in source_record.events.events}) if source_record.events else []
        other_objects = list(source_record.channel_names) if family == "event" else event_labels
        # One unresolved clause containing both time-reference domains cannot
        # assign its ranges reliably. Ask for a narrower scientific clause;
        # never borrow a continuous interval as an event-relative interval.
        range_pieces = [p for p in pieces if not any(self._contains(p, x) for x in other_objects)]
        # A range must be tied to the relevant actual object in the same clause.
        # A later user supplement may omit the object when that same task has
        # already admitted its identity; no unrelated task gets this privilege.
        object_known = object_key in known
        candidate_pieces = [p for p in range_pieces if anchors and all(self._contains(p, x) for x in anchors)]
        if not candidate_pieces and object_known:
            # A shorthand continuation is safe only if it does not explicitly
            # name another actual object. Metadata, not a task-word lexicon,
            # supplies these identities.
            available = list(source_record.channel_names) + ([e.label for e in source_record.events.events]
                         if source_record.events else [])
            foreign = [x for x in available if x not in anchors]
            candidate_pieces = [p for p in range_pieces if not any(self._contains(p, x) for x in foreign)]
            whole_clauses = self._scientific_clauses(self.user_requests[-1], anchors) if self.user_requests else []
            # An abbreviated request_span cannot remove a neighbouring real
            # object from its source clause and turn that object's range into
            # a shorthand supplement for the previously admitted object.
            candidate_pieces = [p for p in candidate_pieces if not any(
                p.strip() in original and any(self._contains(original, x) for x in foreign)
                for original in whole_clauses)]
        sources = dict(known)
        for key, value in scope.items():
            if key in sources:
                continue
            matched = None
            if key in {"channels", "labels"}:
                matched = next((p for p in pieces if all(self._contains(p, x) for x in value)), None)
            elif key in {"start", "end", "tmin", "tmax"}:
                pair = ("tmin", "tmax") if key in {"tmin", "tmax"} else ("start", "end")
                if all(k in scope for k in pair):
                    requested = (float(scope[pair[0]]), float(scope[pair[1]]))
                    matched = next((p for p in candidate_pieces
                                    if {(float(a), float(b)) for a, b in RANGE.findall(p)} == {requested}), None)
                    # One explicitly inherited endpoint plus one newly stated
                    # scalar is a legitimate parameter edit. This is literal
                    # value validation; the model still chooses the field.
                    other = pair[1] if key == pair[0] else pair[0]
                    if matched is None and other in known:
                        matched = next((p for p in candidate_pieces if not RANGE.search(p) and
                            {float(x) for x in re.findall(rf"(?<![A-Za-z0-9.])({NUMBER})(?![\d.])", p)} == {float(value)}), None)
                # Incomplete windows are retained, but never executed. Their
                # endpoints need an actual numeric occurrence in this clause.
                else:
                    matched = next((p for p in candidate_pieces if float(value) in {
                        float(x) for x in re.findall(rf"(?<![A-Za-z0-9.])({NUMBER})(?![\d.])", p)}), None)
            elif key == "line_frequency":
                matched = next((p for p in pieces if any(float(x) == value for x in re.findall(
                    rf"(?<![A-Za-z0-9.])({NUMBER})\s*(?:Hz|赫兹)", p, re.I))), None)
            if matched is not None:
                sources[key] = {"kind": "user", "turn": self.turn, "span": matched}
        unresolved = [k for k in scope if k not in sources]
        fact = {"record": record, "family": family, "scope": clone(scope), "sources": clone(sources),
                "record_fingerprint": current_fingerprint}
        if self.active and fact not in self.active.scientific_facts:
            self.active.scientific_facts.append(fact)
        if not missing and not unresolved and fact not in self.admitted_scopes:
            self.admitted_scopes.append(fact)
        return sources, missing, unresolved

    def remember_observation(self, goal, observation, context):
        # Attach the factual sources before the immutable TaskEntry trace is
        # copied by the existing result archiver.
        observation["scientific_sources"] = clone(self._action_sources or {})
        super().remember_observation(goal, observation, context)

    @staticmethod
    def _pending_resolved(pending, name, args):
        confirmed = pending.get("confirmed_arguments", pending["arguments"])
        return (pending["tool"] == name and
                all(k in args and args[k] == v for k, v in confirmed.items()))

    def execute_action(self, name, arguments, record=None, request_span=None,
                       inherit_result=None, recompute=False):
        if name not in NUMERIC_TOOLS or not isinstance(arguments, dict) or type(recompute) is not bool:
            return self._error("INVALID_ACTION", "Use an enabled numerical tool and its ordinary parameters")
        record = record or (self.active.record if self.active else self.active_record)
        if record not in self.records:
            return self._error("RECORD_NOT_FOUND", "Select an available record")
        inherited = self.find_entry(inherit_result) if inherit_result else None
        if inherit_result and (inherited is None or inherited.record != record or not self._binding_valid(inherited)
                               or self._family(inherited.capability) != self._family(name)):
            return self._error("INVALID_INHERITED_RESULT", "The exact prior result must be valid and have the same record and scientific object type")
        text = self._source_text(request_span)
        if text is None:
            return self._error("INVALID_SOURCE_SPAN", "Optional request_span selects one actual current-user clause, not per-field bookkeeping")
        mentioned = self._mentioned_records(text)
        if mentioned and mentioned != {record}:
            return self._error("RECORD_SCOPE_CONFLICT", "Select a single record's actual user clause; do not combine record-specific parameters")
        if self.active is None or self.active.record != record:
            self.focus_task(name, record, expected_tools=[name])
        goal = self.active
        context = self.contexts[record]
        args = clone(arguments)
        if inherited and not context.executor.registry.get(name).consumes_artifact:
            args = {**clone(inherited.parameters), **args}
        # Metadata needs no user scientific choice and cannot authorize changes.
        if name in METADATA:
            scope, sources = clone(args), {}
        elif context.executor.registry.get(name).consumes_artifact:
            artifact = context.artifacts.get(args.get("artifact_id"))
            owners = [e for e in self.entries if e.record == record and
                      e.evidence["binding"]["artifact_id"] == args.get("artifact_id") and self._binding_valid(e)]
            if artifact is None or not owners:
                return self._pending(name, args, "ARTIFACT_NOT_FOUND", "Use an actual valid artifact in this record")
            if inherited and inherited.evidence["binding"]["artifact_id"] != args.get("artifact_id"):
                return self._pending(name, args, "ARTIFACT_IDENTITY_MISMATCH", "Use the exact inherited artifact, not an equal-content substitute")
            scope = self._scientific_scope(name, args, context)
            sources = {k: {"kind": "artifact", "artifact_id": artifact.artifact_id} for k in scope}
        else:
            scope = clone(args)
            invalid = ReliableWorkingMemoryStore._scientific_contract_check(self, name, scope, record)
            if invalid:
                return self._pending(name, args, invalid["code"], invalid["message"])
            sources, missing, ungrounded = self._ground_scope(name, scope, record, text, inherited)
            if missing:
                return self._pending(name, args, "MISSING_SCIENTIFIC_PARAMETER", "Ask only for genuinely missing scientific values; independent actions can continue", missing_fields=missing,
                                     confirmed_arguments={k: clone(v) for k, v in args.items() if k in sources})
            if ungrounded:
                return self._pending(name, args, "SCIENTIFIC_SCOPE_UNGROUNDED", "Use one relevant user clause or a real inherited result; do not invent a scientific choice", ungrounded_fields=ungrounded,
                                     confirmed_arguments={k: clone(v) for k, v in args.items() if k in sources})
        invalid = ReliableWorkingMemoryStore._scientific_contract_check(self, name, scope, record)
        if invalid:
            return self._pending(name, args, invalid["code"], invalid["message"])
        try:
            _validate_schema(args, context.executor.registry.get(name).parameters)
        except (TypeError, ValueError):
            return self._pending(name, args, "INVALID_TOOL_PARAMETERS", "Use the actual tool's input contract")
        artifact_id = args.get("artifact_id")
        scope_key = encoded(scope)
        pinned = goal.pinned_artifacts.get(scope_key)
        if artifact_id and pinned and pinned != artifact_id:
            return self._pending(name, args, "ARTIFACT_IDENTITY_MISMATCH", "This task is already bound to a different original artifact")
        recompute_source = {"kind": "user", "turn": self.turn, "quote": self.user_requests[-1] if self.user_requests else ""}
        if recompute and not ReliableWorkingMemoryStore._recompute_authorized(self, recompute_source):
            return self._pending(name, args, "UNAUTHORIZED_RECOMPUTATION", "An unchanged valid result needs explicit current-user recomputation authorization")
        binding = self._binding(context, name, artifact_id)
        force_key = encoded([self.turn, record, name, scope, binding])
        force = recompute and force_key not in self.recompute_used
        candidates = [e for e in self.entries if (e.record, e.capability, e.parameters) == (record, name, scope)
                      and self._binding_valid(e) and (not artifact_id or e.evidence["binding"]["artifact_id"] == artifact_id)]
        if name == "create_epochs":
            if inherited and inherited.evidence["binding"]["artifact_id"]:
                candidates = [e for e in candidates if e.evidence["binding"]["artifact_id"] == inherited.evidence["binding"]["artifact_id"]]
            if len({e.evidence["binding"]["artifact_id"] for e in candidates}) > 1 and not force:
                return self._pending(name, args, "AMBIGUOUS_ARTIFACT", "Select an exact inherited result before using one of multiple original artifacts")
            if pinned and candidates and candidates[-1].evidence["binding"]["artifact_id"] != pinned and not force:
                return self._pending(name, args, "ARTIFACT_IDENTITY_MISMATCH", "Cannot replace this task's original artifact")
        parent = inherited if inherited and inherited.capability == name else None
        if parent is None:
            object_key = "labels" if self._family(name) == "event" else "channels"
            previous = [e for e in self.entries if e.record == record and e.capability == name
                        and e.parameters.get(object_key) == scope.get(object_key) and self._binding_valid(e)]
            if len(previous) == 1:
                parent = previous[0]
        target = next((d for d in goal.deliveries if d["tool"] == name and d["scope"] == scope), None)
        if target is None:
            target = {"key": f"result_{len(goal.deliveries)+1}", "tool": name, "scope": clone(scope),
                      "required": True, "revision_of": parent.task_id if parent and (force or parent.parameters != scope) else None}
            goal.deliveries.append(target)
        # Successful correction clears only this action's pending issue. Other
        # independent pending actions retain their requirements and provenance.
        goal.pending_actions = [p for p in goal.pending_actions if not self._pending_resolved(p, name, args)]
        goal.status = "active"
        if candidates and not force:
            entry = candidates[-1]
            target["revision_of"] = entry.revision_of
            goal.reused[target["key"]] = entry.task_id
            self.last_owner = goal.subgoal_id
            self.events.append({"event": "action_result_reused", "result_id": entry.task_id,
                                "subgoal_id": goal.subgoal_id, "turn": self.turn})
            out = {"status": "reused", "task_id": entry.task_id, "subgoal_id": goal.subgoal_id,
                   "scientific_sources": clone(sources), "no_numerical_execution": True}
            result_artifact = entry.evidence["binding"]["artifact_id"]
        else:
            # Sole numerical execution path: the existing WorkingMemoryStore
            # delegates to the original ExecutionContext and Executor.
            self._action_sources = sources
            try:
                out = WorkingMemoryStore.execute_numeric(self, name, args)
            finally:
                self._action_sources = None
            observation = out.get("observation", {})
            result_artifact = (observation.get("result", {}).get("data") or {}).get("artifact_id")
            if force and observation.get("result", {}).get("success"):
                self.recompute_used.add(force_key)
        if result_artifact:
            goal.pinned_artifacts[scope_key] = result_artifact
        out["progress"] = self.completion_check(goal)
        # Explicit expected output sets can be settled automatically. Open-ended
        # purposes remain active until a natural task switch or final response.
        if getattr(goal, "expected_tools", []) and out["progress"]["valid"]:
            out["archive"] = self.settle_active()
        return out

    def _scope_error(self, goal, request, context):
        mismatch = super()._scope_error(goal, request, context)
        if mismatch:
            return mismatch
        if context.executor.registry.get(request.name).consumes_artifact:
            scope = self._scientific_scope(request.name, request.arguments, context)
            pinned = goal.pinned_artifacts.get(encoded(scope))
            if pinned and pinned != request.arguments.get("artifact_id"):
                return "ARTIFACT_IDENTITY_MISMATCH"
        return None
