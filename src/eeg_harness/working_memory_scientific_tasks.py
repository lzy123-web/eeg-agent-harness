"""Scientific result instances and task lifecycle on the original EEG Executor.

The result contract is an output set, not an action sequence or an independent
proof of natural-language intent completeness. A declared scope is never a
source of numerical authorization. Missing fields can be bound only by an
actually admitted action. Original managed/task-memory implementations remain
available unchanged.
"""

import hashlib

from .executor import _validate_schema
from .working_memory import NUMERIC_TOOLS, WorkingMemoryStore, clone, encoded
from .working_memory_actions import ActionWorkingMemoryStore
from .working_memory_deliveries import DeliverySubgoal, MultiResultWorkingMemoryStore
from .working_memory_lifecycle import ReliableWorkingMemoryStore, EVENT_TOOLS, METADATA
from .research.integrated_method.v3 import REQUIRED_PARAMETERS, RESULT_UNITS
from .research.task_memory import TaskEntry


def canonical_scope(scope):
    """Compare scientific selections without changing numerical tool inputs."""
    out = clone(scope)
    for key in ("channels", "labels"):
        if isinstance(out.get(key), list):
            out[key] = sorted(out[key])
    for key in ("start", "end", "tmin", "tmax", "line_frequency"):
        if type(out.get(key)) in {int, float}:
            out[key] = float(out[key])
    return out


def requirement_identity(requirement):
    """Output wording is not a new computation or scientific authorization."""
    return (requirement["tool"], requirement["record"], canonical_scope(requirement["scope"]))


class RequirementValidationError(ValueError):
    def __init__(self, errors):
        super().__init__("Correct the listed result requirements using the actual tool scope; output selection belongs in output_request")
        self.errors = errors


class ScientificTaskStore(ActionWorkingMemoryStore):
    """One scientific purpose can own multiple records, scopes and results.

    ``goal.record`` is explicitly the synchronous execution cursor required by
    the original WorkingMemoryStore.execute_numeric entry. It is assigned only
    after record admission, never used as a historical identity, and never
    temporarily swapped/restored. Requirements, deliveries, observations,
    TaskEntry and artifact pins each carry their own actual record. This store,
    like the original Agent loop, executes one action at a time.
    """

    def begin_subgoal(self, *args, **kwargs):
        # Legacy numerical auto-start would create a different goal shape.
        # Its public entry remains available through the frozen old store.
        return self._error("USE_SCIENTIFIC_ACTION", "Use focus_task or execute_action in this opt-in mode")

    def _parse_requirements(self, requirements, record):
        if requirements is None:
            return []
        if not isinstance(requirements, list) or not 1 <= len(requirements) <= 12:
            raise ValueError("Declare one to twelve result requirements")
        parsed, errors = [], []
        for index, item in enumerate(requirements):
            name = item.get("tool") if isinstance(item,dict) else None
            alias = item.get("record",record) if isinstance(item,dict) else record
            allowed = []
            schema = None
            if isinstance(name,str) and name in NUMERIC_TOOLS and isinstance(alias,str) and alias in self.records:
                registry = self.contexts[alias].executor.registry
                schema = clone(registry.get("create_epochs" if name in EVENT_TOOLS else name).parameters)
                allowed = sorted({"labels","tmin","tmax"} if name in EVENT_TOOLS else set(schema.get("properties",{})))
                schema["properties"] = {k:v for k,v in schema.get("properties",{}).items() if k in allowed}
                schema["required"], schema["additionalProperties"] = [], False
            try:
                if not isinstance(item,dict) or set(item)-{"tool","record","scope","output_request"}:
                    raise ValueError("Requirements contain only tool, record, scope and optional textual output_request")
                scope, output = item.get("scope",{}), item.get("output_request")
                if schema is None or not isinstance(scope,dict):
                    raise ValueError("An enabled tool, known record and structured scientific scope are required")
                if output is not None and (not isinstance(output,str) or len(output)>1200):
                    raise ValueError("output_request must be plain text of at most 1200 characters; it is not an executable condition")
                _validate_schema(scope,schema)
                invalid = ReliableWorkingMemoryStore._scientific_contract_check(self,name,scope,alias)
                if invalid:
                    raise ValueError(invalid["message"])
                row = {"tool":name,"record":alias,"scope":canonical_scope(scope)}
                if output:
                    row["output_request"] = output
                previous = next((r for r in parsed if requirement_identity(r)==requirement_identity(row)),None)
                if previous is not None:
                    if output and output != previous.get("output_request"):
                        self._merge_output_request(previous,row)
                    else:
                        raise ValueError("Duplicate identical computation requirements are not two scientific outputs")
                else:
                    parsed.append(row)
            except (ValueError,TypeError) as exc:
                errors.append({"index":index,"tool":clone(name),"record":clone(alias),
                    "allowed_scope_fields":allowed,"actual_error":{"code":"INVALID_REQUIREMENT","message":str(exc)},
                    "guidance":"Omit missing values rather than null; keep requested report fields in textual output_request. Unsupported processing choices are not normalized or authorized."})
        if errors:
            raise RequirementValidationError(errors)
        return parsed

    @staticmethod
    def _merge_output_request(existing, proposed):
        text = proposed.get("output_request")
        if text and text != existing.get("output_request"):
            old = existing.get("output_request")
            if old and text in old.splitlines():
                return
            existing["output_request"] = f"{old}\n{text}" if old else text

    def focus_task(self, title, record=None, requirements=None):
        if record is None:
            resumable = [g for g in self.subgoals if g.title == title and
                         g.status in {"active", "blocked", "suspended"}]
            if self.active in resumable:
                record = self.active.default_record
            elif len(resumable) == 1:
                record = resumable[0].default_record
            elif len(resumable) > 1:
                return self._error("AMBIGUOUS_TASK", "Several pending purposes share this title; specify the default record")
            else:
                record = self.active_record
        if not isinstance(title, str) or not title.strip() or len(title) > 400 or record not in self.records:
            return self._error("INVALID_TASK", "A short scientific purpose and a known default record are required")
        try:
            requested = self._parse_requirements(requirements, record)
        except RequirementValidationError as exc:
            return {**self._error("INVALID_REQUIREMENTS",str(exc)),"requirement_errors":clone(exc.errors)}
        except (ValueError, TypeError) as exc:
            return self._error("INVALID_REQUIREMENTS", str(exc))
        candidates = [g for g in self.subgoals if g.title == title and
                      getattr(g, "default_record", g.record) == record and g.status in {"active", "suspended", "blocked"}]
        goal = self.active if self.active in candidates else (candidates[0] if len(candidates) == 1 else None)
        if self.active is not None and self.active is not goal:
            self.settle_active()
        if goal is None:
            goal = DeliverySubgoal(subgoal_id=f"{self.session_id}-s{len(self.subgoals)+1}",
                title=title, record=record, deliverable="", scope={}, checks=[], turn=self.turn)
            goal.default_record, goal.requirements = record, []
            goal.declared_requirements = []
            goal.implicit_contract = False
            goal.requirement_results, goal.requirement_attempts = {}, {}
            goal.expected_tools, goal.pending_actions = [], []
            goal.scientific_facts, goal.pinned_artifacts = [], {}
            self.subgoals.append(goal)
            event = "task_focused"
        else:
            event = "task_resumed" if goal.status == "suspended" else "task_refocused"
        # Refocusing may add outputs; it cannot silently drop an unfinished one.
        for row in requested:
            existing = next((i for i,r in enumerate(goal.requirements)
                if requirement_identity(r)==requirement_identity(row) or
                   requirement_identity(goal.declared_requirements[i])==requirement_identity(row)),None)
            if existing is None:
                goal.requirements.append(row)
                goal.declared_requirements.append(clone(row))
            else:
                self._merge_output_request(goal.requirements[existing],row)
                self._merge_output_request(goal.declared_requirements[existing],row)
        goal.status = "active"
        self.active, self.active_record, self.last_owner = goal, record, goal.subgoal_id
        self.events.append({"event": event, "subgoal_id": goal.subgoal_id,
                            "record": record, "requirements": clone(goal.requirements), "turn": self.turn})
        return {"status": "active", "task": self.summary(goal)}

    def goal_card(self, goal):
        card = super().goal_card(goal)
        records = sorted({r["record"] for r in goal.requirements} |
                         {self.find_entry(i).record for i in goal.result_ids if self.find_entry(i)})
        card.update(contract_version="scientific_result_instances_v1",
                    record=records[0] if len(records) == 1 else None,
                    records=records, default_record=goal.default_record,
                    current_execution_record=goal.record,
                    requirements=clone(goal.requirements))
        card.pop("expected_tools", None)
        return card

    def summary(self, goal):
        card = super().summary(goal)
        card["available_control"] = (
            "Continue scientific actions; each requested record/tool/scope needs its own valid result. "
            "At finish or task switch the program archives only a complete result set, otherwise suspends it. "
            "read_result reads exact evidence; restore_task restores the actual process.")
        return card

    @staticmethod
    def _required_fields(name):
        return ("labels", "tmin", "tmax") if name in EVENT_TOOLS else REQUIRED_PARAMETERS.get(name, ())

    def _bind_requirement(self, goal, name, record, scope, entry_id=None, success=True):
        actual = canonical_scope(scope)
        exact = [i for i,r in enumerate(goal.requirements)
                 if (r["tool"], r["record"], r["scope"]) == (name, record, actual)]
        compatible = [i for i,r in enumerate(goal.requirements)
                      if r["tool"] == name and r["record"] == record and
                      all(k in actual and actual[k] == v for k,v in r["scope"].items())]
        selected = exact if exact else compatible
        if len(selected) != 1:
            return  # Extra measurements are real evidence, not arbitrary contract fulfilment.
        index = selected[0]
        if success:
            # The scope came from an admitted action/real artifact, not a model
            # requirement or an opportunistic scan of the historical archive.
            goal.requirements[index]["scope"] = actual
            goal.requirement_results[index] = entry_id
        else:
            goal.requirement_results.pop(index, None)
        goal.requirement_attempts[index] = "satisfied" if success else "failed"

    @staticmethod
    def _remember_implicit_output(goal, name, record, scope):
        if goal.implicit_contract:
            row = {"tool": name, "record": record, "scope": canonical_scope(scope)}
            if not any(requirement_identity(row)==requirement_identity(r) for r in goal.requirements):
                goal.requirements.append(row)
                goal.declared_requirements.append(clone(row))

    def completion_check(self, goal):
        states = []
        for index, requirement in enumerate(goal.requirements):
            missing = [k for k in self._required_fields(requirement["tool"])
                       if requirement["scope"].get(k) in (None, "", [])]
            entry = self.find_entry(goal.requirement_results.get(index))
            state = "awaiting_parameter" if missing else goal.requirement_attempts.get(index, "missing")
            if entry:
                matches = (entry.record == requirement["record"] and entry.capability == requirement["tool"] and
                           canonical_scope(entry.parameters) == requirement["scope"])
                state = "satisfied" if matches and self._binding_valid(entry) else "stale"
            states.append({**clone(requirement), "status": state,
                           "result_id": entry.task_id if entry else None, "missing_fields": missing})
        # Same record and event scope must name the same *actual* Epoch object.
        groups = {}
        for state in states:
            if state["status"] == "satisfied":
                entry = self.find_entry(state["result_id"])
                ident = entry.evidence["binding"]["artifact_id"]
                if ident:
                    groups.setdefault(encoded([entry.record, canonical_scope(entry.parameters)]), []).append((ident, state))
        for group in groups.values():
            if len({ident for ident,_ in group}) > 1:
                for _, state in group:
                    state["status"] = "artifact_mismatch"
        pending = clone(goal.pending_actions)
        ready = bool(states) and all(r["status"] == "satisfied" for r in states) and not pending
        return {"valid": ready, "ready": ready, "code": None if ready else "TASK_REQUIREMENTS_PENDING",
                "requirements": states, "deliveries": clone(states), "pending_actions": pending,
                "intent_completeness": "model_declaration_not_independent_natural_language_proof"}

    def settle_active(self, unresolved=None):
        if self.active is None:
            return {"status": "unchanged"}
        check = self.completion_check(self.active)
        if check["ready"]:
            return MultiResultWorkingMemoryStore.close_subgoal(self, "completed")
        missing = list(unresolved or []) + [
            f"{r['status']}: {r['record']}/{r['tool']} {r['scope']}"
            for r in check["requirements"] if r["status"] != "satisfied"]
        missing += [f"{p['code']}: {p['record']}/{p['tool']}" for p in check["pending_actions"]]
        return MultiResultWorkingMemoryStore.close_subgoal(self, "suspended",
            unresolved=missing or ["No independently checkable scientific output has been declared"])

    def _pending(self, name, arguments, code, message, **details):
        goal = self.active
        if goal:
            record = goal.record
            if code in {"ARTIFACT_NOT_FOUND", "ARTIFACT_IDENTITY_MISMATCH", "AMBIGUOUS_ARTIFACT"}:
                # A rejected guessed handle is not an immutable requirement.
                # Correct use of the real object may recover this same action.
                details.setdefault("confirmed_arguments", {})
            row = {"tool": name, "record": record, "arguments": clone(arguments),
                   "code": code, "message": message, **details}
            goal.pending_actions = [p for p in goal.pending_actions
                if (p["record"],p["tool"],p["arguments"]) != (record,name,arguments)] + [row]
            goal.unresolved = [f"{p['code']}: {p['record']}/{p['tool']}" for p in goal.pending_actions]
            self.last_owner = goal.subgoal_id
            self.events.append({"event": "action_not_admitted", "subgoal_id": goal.subgoal_id,
                "record": record, "tool": name, "code": code, "turn": self.turn})
        return {**self._error(code, message), **details, "independent_actions_remain_available": True,
                "subgoal_id": goal.subgoal_id if goal else None}

    def remember_observation(self, goal, observation, context):
        """Original immutable TaskEntry contract, with record-qualified targets."""
        observation["scientific_sources"] = clone(self._action_sources or {})
        result, record = observation["result"], observation["record"]
        name, scope = observation["request"]["name"], observation["scope"]
        target = next((d for d in goal.deliveries if (d["record"],d["tool"],canonical_scope(d["scope"])) ==
                       (record,name,canonical_scope(scope))), None)
        if target:
            goal.reused.pop(target["key"], None)
        if not result["success"]:
            self._bind_requirement(goal,name,record,scope,success=False)
            return
        artifact_id = (result["data"] or {}).get("artifact_id")
        binding = self._binding(context,name,artifact_id)
        parent = target["revision_of"] if target else None
        task_id = f"{self.session_id}-t{len(self.entries)+1}"
        meta = {"sfreq":context.record.sfreq,"reference":context.record.reference,"montage":context.record.montage,
            "processing_metadata":clone(list(context.record.processing_metadata)),
            "time_reference":"event_relative" if name in EVENT_TOOLS else "record_absolute",**binding["config"]}
        proof = {"result":result["data"],"record":record,"scope":scope,"binding":binding,"tool":name,"revision_of":parent}
        evidence = {"source":context.record.source,"source_stage":"event_epochs" if artifact_id else "loaded_record",
            "analysis_configuration":meta,"unit_or_kind":RESULT_UNITS.get(name,"Epoch artifact descriptor" if name == "create_epochs" else "event metadata"),
            "evidence_token":"wm-set:"+hashlib.sha256(encoded(proof)).hexdigest(),"binding":binding,
            "subgoal_id":goal.subgoal_id,"delivery_key":target["key"] if target else None}
        entry = TaskEntry(task_id,len(self.entries)+1,record,name,clone(scope),goal.title,parent,"completed",
                          clone(result["data"]),evidence,(clone(observation),))
        self.entries.append(entry)
        goal.result_ids.append(task_id)
        observation["result_id"] = task_id
        self._remember_implicit_output(goal,name,record,scope)
        self._bind_requirement(goal,name,record,scope,task_id)

    def _scope_error(self, goal, request, context):
        if self._action_sources is None:
            return "ACTION_NOT_ADMITTED"
        scope = self._scientific_scope(request.name,dict(request.arguments),context)
        if scope is None:
            return "ARTIFACT_NOT_FOUND"
        if context.executor.registry.get(request.name).consumes_artifact:
            artifact = context.artifacts[request.arguments["artifact_id"]]
            if artifact.source != context.record.source or artifact.baseline is not None:
                return "SCIENTIFIC_SCOPE_MISMATCH"
            pinned = goal.pinned_artifacts.get(encoded([goal.record,canonical_scope(scope)]))
            if pinned and pinned != artifact.artifact_id:
                return "ARTIFACT_IDENTITY_MISMATCH"
        return None  # execute_action has admitted this exact scientific object.

    def execute_action(self,name,arguments,record=None,request_span=None,inherit_result=None,recompute=False,channel_reference=None):
        from .scientific_request_binding import resolve_action_source, ground_bound_scope
        if name not in NUMERIC_TOOLS or not isinstance(arguments,dict) or type(recompute) is not bool:
            return self._error("INVALID_ACTION","Use an enabled numerical tool and ordinary parameters")
        inherited = self.find_entry(inherit_result) if inherit_result else None
        record = record or (inherited.record if inherited else self.active.record if self.active else self.active_record)
        if record not in self.records:
            return self._error("RECORD_NOT_FOUND","Select an available record")
        if inherit_result and (inherited is None or inherited.record != record or not self._binding_valid(inherited)
                or self._family(inherited.capability) != self._family(name)):
            return self._error("INVALID_INHERITED_RESULT","Use a valid result of the same record and scientific object type")
        if channel_reference is not None and (name in METADATA or self._family(name) != "continuous"):
            return self._error("INVALID_CHANNEL_REFERENCE","Channel-name references apply only to continuous selections")
        context,args = self.contexts[record],clone(arguments)
        if inherited and not context.executor.registry.get(name).consumes_artifact:
            args = {**clone(inherited.parameters),**args}
        if self.active is None:
            # An unadmitted proposal is not a scientific requirement. Short
            # implicit work acquires its output identity from actual success;
            # failures remain pending/observed without pinning guessed scopes.
            started = self.focus_task(name,record)
            if started.get("status") != "active":
                return started
            self.active.implicit_contract = True
        goal = self.active
        # Explicit synchronous execution cursor for the unchanged Executor path.
        goal.record = record
        self.active_record = record
        resolution = resolve_action_source(self,name,args,record,request_span,inherited=inherited)
        if not resolution.ok:
            return self._pending(name,args,resolution.code,resolution.message,confirmed_arguments={})
        if name in METADATA:
            scope,sources = clone(args),{}
        elif context.executor.registry.get(name).consumes_artifact:
            artifact = context.artifacts.get(args.get("artifact_id"))
            owners = [e for e in self.entries if e.record == record and
                      e.evidence["binding"]["artifact_id"] == args.get("artifact_id") and self._binding_valid(e)]
            if artifact is None or not owners:
                return self._pending(name,args,"ARTIFACT_NOT_FOUND","Use an actual valid artifact in this record")
            if inherited and inherited.evidence["binding"]["artifact_id"] != args.get("artifact_id"):
                return self._pending(name,args,"ARTIFACT_IDENTITY_MISMATCH","Use the exact inherited artifact")
            scope = self._scientific_scope(name,args,context)
            sources = {k:{"kind":"artifact","artifact_id":artifact.artifact_id,"record":record} for k in scope}
        else:
            scope = clone(args)
            invalid = ReliableWorkingMemoryStore._scientific_contract_check(self,name,scope,record)
            if invalid:
                return self._pending(name,args,invalid["code"],invalid["message"])
            try:
                sources,missing,ungrounded = ground_bound_scope(self,name,scope,record,resolution,inherited,channel_reference)
            except ValueError as exc:
                return self._pending(name,args,"INVALID_CHANNEL_REFERENCE",str(exc),confirmed_arguments={})
            if missing:
                return self._pending(name,args,"MISSING_SCIENTIFIC_PARAMETER","Ask only for missing scientific values; independent work can continue",
                    missing_fields=missing,confirmed_arguments={k:clone(v) for k,v in args.items() if k in sources})
            if ungrounded:
                return self._pending(name,args,"SCIENTIFIC_SCOPE_UNGROUNDED","Use the whole user scientific object or an actual inherited result",
                    ungrounded_fields=ungrounded,confirmed_arguments={k:clone(v) for k,v in args.items() if k in sources})
        invalid = ReliableWorkingMemoryStore._scientific_contract_check(self,name,scope,record)
        if invalid:
            return self._pending(name,args,invalid["code"],invalid["message"])
        try:
            _validate_schema(args,context.executor.registry.get(name).parameters)
        except (TypeError,ValueError):
            return self._pending(name,args,"INVALID_TOOL_PARAMETERS","Use the actual numerical tool contract")
        artifact_id = args.get("artifact_id")
        scope_key = encoded([record,canonical_scope(scope)])
        pinned = goal.pinned_artifacts.get(scope_key)
        if artifact_id and pinned and pinned != artifact_id:
            return self._pending(name,args,"ARTIFACT_IDENTITY_MISMATCH","This scientific object already owns a different actual artifact")
        recompute_source = {"kind":"user","turn":self.turn,"quote":self.user_requests[-1] if self.user_requests else ""}
        if recompute and not ReliableWorkingMemoryStore._recompute_authorized(self,recompute_source):
            return self._pending(name,args,"UNAUTHORIZED_RECOMPUTATION","An unchanged valid result needs current-user recomputation authorization")
        binding = self._binding(context,name,artifact_id)
        force_key = encoded([self.turn,record,name,canonical_scope(scope),binding])
        force = recompute and force_key not in self.recompute_used
        candidates = [e for e in self.entries if (e.record,e.capability,canonical_scope(e.parameters)) ==
                      (record,name,canonical_scope(scope)) and self._binding_valid(e) and
                      (not artifact_id or e.evidence["binding"]["artifact_id"] == artifact_id)]
        if name == "create_epochs":
            if inherited and inherited.evidence["binding"]["artifact_id"]:
                candidates = [e for e in candidates if e.evidence["binding"]["artifact_id"] == inherited.evidence["binding"]["artifact_id"]]
            if len({e.evidence["binding"]["artifact_id"] for e in candidates}) > 1 and not force:
                return self._pending(name,args,"AMBIGUOUS_ARTIFACT","Select an exact existing artifact before reuse")
            if pinned and candidates and candidates[-1].evidence["binding"]["artifact_id"] != pinned and not force:
                return self._pending(name,args,"ARTIFACT_IDENTITY_MISMATCH","Cannot replace this task's original artifact")
        parent = inherited if inherited and inherited.capability == name else None
        if parent is None:
            object_key = "labels" if self._family(name) == "event" else "channels"
            previous = [e for e in self.entries if e.record == record and e.capability == name and
                        e.parameters.get(object_key) == scope.get(object_key) and self._binding_valid(e)]
            if len(previous) == 1:
                parent = previous[0]
        target = next((d for d in goal.deliveries if (d["record"],d["tool"],canonical_scope(d["scope"])) ==
                       (record,name,canonical_scope(scope))),None)
        if target is None:
            target = {"key":f"result_{len(goal.deliveries)+1}","record":record,"tool":name,"scope":clone(scope),
                "required":True,"revision_of":parent.task_id if parent and (force or parent.parameters != scope) else None}
            goal.deliveries.append(target)
        goal.pending_actions = [p for p in goal.pending_actions if not
            (p["record"] == record and self._pending_resolved(p,name,args))]
        goal.status = "active"
        if candidates and not force:
            entry = candidates[-1]
            target["revision_of"] = entry.revision_of
            goal.reused[target["key"]] = entry.task_id
            self.last_owner = goal.subgoal_id
            self.events.append({"event":"action_result_reused","result_id":entry.task_id,"subgoal_id":goal.subgoal_id,"turn":self.turn})
            self._remember_implicit_output(goal,name,record,scope)
            self._bind_requirement(goal,name,record,scope,entry.task_id)
            out = {"status":"reused","task_id":entry.task_id,"subgoal_id":goal.subgoal_id,
                   "scientific_sources":clone(sources),"no_numerical_execution":True}
            result_artifact = entry.evidence["binding"]["artifact_id"]
        else:
            self._action_sources = sources
            try:
                out = WorkingMemoryStore.execute_numeric(self,name,args)
            finally:
                self._action_sources = None
            observation = out.get("observation",{})
            result_artifact = (observation.get("result",{}).get("data") or {}).get("artifact_id")
            if force and observation.get("result",{}).get("success"):
                self.recompute_used.add(force_key)
        if result_artifact:
            goal.pinned_artifacts[scope_key] = result_artifact
        out["progress"] = self.completion_check(goal)
        # Ready is not archived: the next model decision still sees active AO.
        return out
