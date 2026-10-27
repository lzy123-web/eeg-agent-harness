"""Task working context with program-owned facts, on the original Agent loop.

The model chooses scientific work and semantic completion. Real actions supply
facts; archival and evidence identity never depend on a repeated coverage form.
"""
import json

from .executor import _validate_schema
from .result_semantics import result_field_semantics, UnsupportedResultField
from .working_memory import NUMERIC_TOOLS, clone, encoded
from .working_memory_agent import WorkingMemoryController, control, STRING, STRINGS
from .research.task_memory_evidence import _entry_meta, scalar_paths


MANAGED_SYSTEM = """你是多轮EEG分析助手。用户请求、真实记录元信息与历史是输入，所有数值来自科学工具。
你负责选择有意义的科学任务和下一动作、解释真正歧义及完成回答；程序自动记录结果、来源、版本和工件，不要填写旧版来源/coverage登记表。
简单任务可直接调用数值工具；复杂任务可focus_task(title,expected_tools)组织多个结果。独立的合法动作可继续，不因另一项缺参而全部停止。
只使用用户实际给出的科学参数；不猜事件相对窗口。当前请求含多个范围或对象时，request_span可引用相关原文子句一次定位科学选择。继承旧条件可指定inherit_result；程序继承实际参数，不需要重抄。改变窗口要保留旧结果及修订来源。
已有结果有效时不重算。工件必须来自真实create_epochs结果；沿用原试次要使用原artifact_id，内容相同不等于同一对象。此模式不支持基线校正、筛选或其它新处理变换。
历史请求始终真实存在。任务摘要的结果条件/小型精确事实可直接使用；定位项不是数值。read_result读真实精确字段；restore_task恢复原任务行动观察，只有需要处理过程继续分析才用，不强迫恢复。
任务当前实际行动观察用于下一步决策，已完成摘要和外部完整过程共同保存。程序能核验动作，不能证明原请求全部意图已覆盖，请按原请求检查遗漏。
用finish_task输出完整中文回答(status=completed)，或准确说明未完成项(partial)、真正缺少的科学参数(clarification_required)。资源停止不是用户缺参。
最终给必要值、单位、对象/时间基准及限制。优先使用程序给出的canonical_display，幅值V、功率V²、计数无量纲；原功率不是ERD/ERS或诊断。没有运行质量测量只能说尚未测量，不能声称质量通过或系统没有阈值。"""


def managed_controls():
    return [
        control("focus_task", "Optional semantic organization of a scientific task, not an execution plan. Facts and archival are automatic.", {
            "title": STRING, "record": STRING, "expected_tools": STRINGS}, ["title"]),
        control("read_result", "Read an exact immutable result. The program derives its record, scope and version; no copied provenance is needed.", {
            "result_id": STRING, "record": STRING, "fields": {"type": "array", "items": {"type": "array", "items": {"type": ["string", "integer"]}}}}, ["result_id"]),
        control("restore_task", "Restore a real archived task's action-observation process for subsequent work, distinct from a scalar read.", {
            "task_id": STRING, "reason": STRING}, ["task_id", "reason"]),
        control("finish_task", "Deliver original request results, genuine clarification or honest partial work. No repeated coverage/source form.", {
            "status": {"type": "string", "enum": ["completed", "partial", "clarification_required"]},
            "answer": STRING, "unresolved": STRINGS}, ["status", "answer"]),
    ]


class ManagedMemoryController(WorkingMemoryController):
    def __init__(self, store, **kwargs):
        kwargs.pop("request_closure", None)
        super().__init__(store, request_closure=False, **kwargs)
        self.lifecycle = True  # original loop's valid sequential native batches
        self.request_closure = True  # shared budget hook, NOT old coverage layer
        self.request_progress = None
        self.last_view = None
        self.retrieved = {}

    def begin_turn(self, request):
        if self.store.active:
            self.store.settle_active()
        super().begin_turn(request)
        self.last_view, self.retrieved = None, {}

    def control_definitions(self):
        return managed_controls()

    def tool_definitions(self):
        if getattr(self, "final_only", False):
            return self.final_tools()
        registry = next(iter(self.store.contexts.values())).executor.registry
        tools = []
        for name in sorted(NUMERIC_TOOLS):
            spec = registry.get(name)
            tool = clone(spec.public_definition())
            props = tool["function"]["parameters"]["properties"]
            props.update(record=STRING,
                request_span={**STRING, "description": "Optional one exact clause of the current request when multiple scientific scopes are present. No per-field quotes."},
                inherit_result={**STRING, "description": "Actual result handle to inherit unchanged scope and record; changed fields still require current user support."},
                recompute={"type": "boolean", "description": "Only an explicitly requested fresh calculation; otherwise valid existing results are reused."})
            # Missing scientific parameters may be supplied by an exact parent.
            # Actual admission/Executor still checks every required field.
            tool["function"]["parameters"]["required"] = []
            tool["function"]["description"] += " Actual prerequisites: " + json.dumps(spec.preconditions)
            tools.append(tool)
        return tools + self.control_definitions()

    def _field(self, entry, path, value):
        out = {"path": path, "value": clone(value)}
        try:
            semantics = result_field_semantics(entry.capability, path, entry.result,
                parameters=entry.parameters, analysis_configuration=entry.evidence["analysis_configuration"])
            unit = semantics["unit_or_kind"]
            out["semantics"] = {"kind": semantics["kind"], "unit": unit}
            out["canonical_display"] = f"{value} {unit}"
            if unit in {"V", "V²"}:
                scaled = float(value) * (1e6 if unit == "V" else 1e12)
                out["scaled_display"] = f"{scaled:.8g} " + ("µV" if unit == "V" else "µV²")
        except (UnsupportedResultField, ValueError, TypeError):
            pass
        return out

    def _evidence(self, entry, fields=None, limit=None):
        all_values = list(scalar_paths(entry.result))
        values = all_values if fields is None else [(f["path"], f["value"]) for f in fields]
        use = values if limit is None else values[:limit]
        return {**_entry_meta(entry), "artifact_id": entry.evidence["binding"]["artifact_id"],
                "fields": [self._field(entry, path, value) for path, value in use],
                "omitted_fields": len(all_values)-len(use)}

    def _merge_seen_fields(self, entry, fields):
        """Accumulate only verified fields actually returned or presented now.

        This is a turn-local handoff, not archive prefetch. In particular, two
        partial reads of one result must not erase each other's evidence.
        """
        if not self.store._binding_valid(entry):
            return
        available = {encoded(path): value for path, value in scalar_paths(entry.result)}
        merged = {encoded(f["path"]): clone(f)
                  for f in self.retrieved.get(entry.task_id, {}).get("fields", [])}
        for field in fields:
            path, value = field.get("path"), field.get("value")
            key = encoded(path)
            if key in available and encoded(value) == encoded(available[key]):
                merged[key] = {"path": clone(path), "value": clone(value)}
        if merged:
            self.retrieved[entry.task_id] = self._evidence(entry, fields=list(merged.values()))

    def _remember_presented(self, messages):
        """Retain valid evidence from the real decision view, excluding proposals."""
        def scan(value):
            if isinstance(value, dict):
                ident = value.get("task_id") or value.get("result_id")
                entry = self.store.find_entry(ident) if isinstance(ident, str) else None
                if entry and self.store._binding_valid(entry):
                    result = value.get("result")
                    if isinstance(result, dict) and result.get("success") and result.get("data") == entry.result:
                        self._merge_seen_fields(entry, [{"path": p, "value": v} for p,v in scalar_paths(entry.result)])
                    elif isinstance(value.get("fields"), list):
                        self._merge_seen_fields(entry, value["fields"])
                for child in value.values():
                    if isinstance(child, (dict, list)):
                        scan(child)
            elif isinstance(value, list):
                for child in value:
                    scan(child)
        for message in messages:
            if message.get("role") not in {"user", "tool"}:
                continue
            try:
                scan(json.loads(message.get("content") or "null"))
            except (ValueError, TypeError):
                pass

    def _full_observation_ids(self, values):
        """Which results already appear in full in actual AO/restored content?"""
        found = set()
        def scan(value):
            if isinstance(value, dict):
                ident, result = value.get("result_id"), value.get("result")
                entry = self.store.find_entry(ident) if isinstance(ident, str) else None
                if (entry and isinstance(result, dict) and result.get("success") and
                        result.get("data") == entry.result and self.store._binding_valid(entry)):
                    found.add(ident)
                for child in value.values():
                    if isinstance(child, (dict, list)):
                        scan(child)
            elif isinstance(value, list):
                for child in value:
                    scan(child)
        scan(values)
        return found

    def _card(self, goal, *, facts=False, omit_fact_ids=()):
        card = {k: clone(v) for k,v in self.store.goal_card(goal).items() if k in {
            "subgoal_id", "title", "record", "created_turn", "status", "expected_tools", "pending_actions", "unresolved"}}
        card["delivery_check"] = self.store.completion_check(goal)
        card["results"] = []
        for ident in dict.fromkeys(goal.result_ids + list(goal.reused.values())):
            entry = self.store.find_entry(ident)
            if entry is None:
                continue
            row = {**_entry_meta(entry), "artifact_id": entry.evidence["binding"]["artifact_id"],
                   "binding_valid": self.store._binding_valid(entry),
                   "readable_fields": [p for p,_ in scalar_paths(entry.result)][:64]}
            if facts and row["binding_valid"] and ident not in omit_fact_ids:
                row.update(self._evidence(entry, limit=64 if self.context_mode == "summary" else 12))
            card["results"].append(row)
        return card

    def _view(self):
        s = self.store
        if self.context_mode == "full":
            pairs = self.exchanges
        else:
            pairs = list(s.active.exchanges) if s.active else []
            if self.pending and (not pairs or pairs[-1] != self.pending):
                pairs += [self.pending]
        native = [clone(m) for pair in pairs for m in pair]
        observed = []
        for message in native:
            if message.get("role") == "tool":
                try:
                    observed.append(json.loads(message.get("content") or "null"))
                except (TypeError, ValueError):
                    pass
        full_ids = self._full_observation_ids(observed + list(self.restored.values()))
        seen_ids = {ident for ident in self.retrieved
                    if s.find_entry(ident) and s._binding_valid(s.find_entry(ident))}
        archive = [self._card(g, facts=self.context_mode != "full" and g.subgoal_id not in self.restored,
                             omit_fact_ids=seen_ids | full_ids)
                   for g in s.subgoals if g is not s.active]
        payload = {"current_request": self.requests[-1], "user_requests": clone(self.requests), "current_turn": s.turn,
            "records": {k:{"source":r.source,"sfreq":r.sfreq,"duration_seconds":r.duration_seconds,
                "channels":list(r.channel_names),"reference":r.reference,
                "event_labels":sorted({e.label for e in r.events.events}) if r.events else []}
                for k,r in s.records.items()},
            "task_summaries": archive,
            "active_task": self._card(s.active) if s.active else None,
            "retrieved_evidence": [v for k,v in self.retrieved.items() if k in seen_ids and k not in full_ids],
            "restored_trajectories": list(self.restored.values()),
            "feedback": self.feedback,
            "responsibilities": "Actual sources/results/version bookkeeping is automatic; model scientific interpretation and original-request completeness remain fallible."}
        return [{"role":"system","content":MANAGED_SYSTEM},
                {"role":"user","content":encoded(payload).decode("utf8")}] + native

    def build_messages(self, *, record_decision=True, final_preview=None):
        if getattr(self, "delivery_checkpoint", None):
            return super().build_messages(record_decision=record_decision)
        messages = self._view()
        if len(json.dumps(messages,ensure_ascii=False).encode("utf8")) > self.max_context_bytes:
            if record_decision:
                self.stop_reason = "context_capacity"
            return []
        if record_decision:
            self._remember_presented(messages)
            self.last_view = clone(messages)
            self.visible_evidence_ids = self._visible_results(messages)
            self.decisions.append({"turn":self.store.turn,"messages":clone(messages),
                "active_subgoal":self.store.active.subgoal_id if self.store.active else None,
                "context_bytes":len(encoded(messages)),"before_action":len(self.exchanges)+1})
        return messages

    def build_final_messages(self, reason="resource_reserve"):
        # Keep only facts actually available in the current view; never fetch
        # unseen archive values based on an expected answer or a future query.
        view = self.last_view or self._view()
        evidence = {}
        def scan(value):
            if isinstance(value, dict):
                ident = value.get("task_id") or value.get("result_id")
                entry = self.store.find_entry(ident) if isinstance(ident,str) else None
                if entry and self.store._binding_valid(entry):
                    raw_result = value.get("result")
                    if isinstance(raw_result, dict) and raw_result.get("success") is True:
                        evidence[ident] = self._evidence(entry)
                    elif value.get("fields"):
                        actual = {encoded(p):v for p,v in scalar_paths(entry.result)}
                        fields = [f for f in value["fields"] if encoded(f.get("path")) in actual and
                                  encoded(f.get("value")) == encoded(actual[encoded(f["path"])])]
                        if fields:
                            prior = evidence.setdefault(ident, self._evidence(entry, fields=[]))
                            known = {encoded(f["path"]) for f in prior["fields"]}
                            prior["fields"] += [self._field(entry,f["path"],f["value"]) for f in fields if encoded(f["path"]) not in known]
                for x in value.values(): scan(x)
            elif isinstance(value,list):
                for x in value:scan(x)
        for m in view:
            if m["role"] not in {"user","tool"}:continue
            try:scan(json.loads(m.get("content", "")))
            except (ValueError,TypeError):pass
        payload = {"user_requests":clone(self.requests),"current_request":self.requests[-1],
            "available_evidence":list(evidence.values()),
            "task_status":[self._card(g) for g in self.store.subgoals],
            "delivery_reason":reason,
            "instruction":"Use actual available values and units. State any unmet original demand. Resource limitations are not scientific missing parameters."}
        return [{"role":"system","content":MANAGED_SYSTEM},
                {"role":"user","content":encoded(payload).decode("utf8")}], self.final_tools()

    def _dispatch(self, request):
        name, args = request.name, dict(request.arguments)
        s = self.store
        if self.final_only and name != "finish_task":
            return s._error("FINAL_DELIVERY_ONLY", "Only evidence-grounded delivery is currently reserved")
        if name in NUMERIC_TOOLS:
            controls = {k:args.pop(k) for k in ("record","request_span","inherit_result","recompute") if k in args}
            result = s.execute_action(name,args,**controls)
            # A reused result is an actual read, with its original identity.
            if result.get("status") == "reused" and result.get("task_id"):
                entry = s.find_entry(result["task_id"])
                self._merge_seen_fields(entry, [{"path": p, "value": v} for p,v in scalar_paths(entry.result)])
            return result
        spec = next((x["function"] for x in managed_controls() if x["function"]["name"] == name),None)
        if not spec:return s._error("TOOL_NOT_AVAILABLE","Use an advertised tool")
        _validate_schema(args,spec["parameters"])
        if name == "focus_task":return s.focus_task(**args)
        if name == "read_result":
            entry = s.find_entry(args["result_id"])
            if entry is None or not s._binding_valid(entry):return s._error("INVALID_RESULT","Unknown or stale immutable result")
            mentions = s._mentioned_records(self.requests[-1])
            if args.get("record",entry.record) != entry.record or (mentions and entry.record not in mentions):
                return s._error("RECORD_MISMATCH","Selected result belongs to a different record")
            result = s.read_evidence(entry.task_id,entry.record,entry.parameters,field_paths=args.get("fields"))
            if result.get("evidence"):
                result["evidence"] = self._evidence(entry,result["evidence"]["fields"])
                self._merge_seen_fields(entry, result["evidence"]["fields"])
            return result
        if name == "restore_task":
            if self.restore_count >= self.max_restores:return s._error("RESTORE_LIMIT","Restoration bound reached")
            goal = s.find_subgoal(args["task_id"])
            if goal is None:
                entry = s.find_entry(args["task_id"])
                goal = s.find_subgoal(entry.evidence["subgoal_id"]) if entry else None
            if goal is None:return s._error("TASK_NOT_FOUND","Choose a task or actual result shown in history")
            if any(not s._binding_valid(s.find_entry(i)) for i in goal.result_ids):
                return s._error("STALE_TASK","Historical process is no longer valid for this record")
            result = s.restore_subgoal(goal.subgoal_id)
            if result["status"] == "restored":
                result.pop("native_exchanges",None)
                result["reason"] = args["reason"]
                self.restored[goal.subgoal_id] = clone(result)
                self.restore_count += 1
                s.events.append({"event":"restored","subgoal_id":goal.subgoal_id,"turn":s.turn,"reason":args["reason"]})
            return result
        if name == "finish_task":
            status = args["status"]
            unresolved = args.get("unresolved",[])
            if status != "completed" and not unresolved:
                return s._error("UNRESOLVED_REQUIRED","Describe the actual missing science or resource limitation")
            if getattr(self,"checkpoint_stale",False) and status != "partial":
                return s._error("CHECKPOINT_PARTIAL_ONLY","Only the earlier visible snapshot is reserved; report partial delivery")
            if status == "completed" and (unresolved or not self.visible_evidence_ids):
                return s._error("NO_VISIBLE_DELIVERY","Complete only with actual visible evidence and no reported unmet items")
            if status == "completed" and s.active and not s.completion_check(s.active)["valid"]:
                return {**s._error("UNFINISHED_CURRENT_TASK","Current observed task has unmet science; continue independent work or explicitly report partial/clarification"),"progress":s.completion_check(s.active)}
            s.settle_active(unresolved)
            self.stop_reason,self.final_answer = status,args["answer"]
            return {"status":status,"answer":args["answer"],"unresolved":unresolved,
                    "meaning":"Semantic original-request completion remains model responsibility, not a proof by result count"}
