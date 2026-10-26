"""Opt-in working-memory hooks for EEGAgent, not a second agent/executor loop."""

import json
import time

from .agent import EEGAgent
from .executor import _validate_schema
from .tooling import ToolResult
from .working_memory import WorkingMemoryStore, NUMERIC_TOOLS, TERMINALS, clone, encoded
from .research.task_memory_evidence import merge_evidence, _entry_meta, scalar_paths


def control(name, description, properties, required):
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties,
                           "required": required, "additionalProperties": False}}}


STRING = {"type": "string"}
STRINGS = {"type": "array", "items": STRING}
CONTROLS = [
    control("begin_subgoal", "Declare ONE scientific delivery contract before multi-action analysis or a revision. Do not specify a whole action sequence.", {
        "title": STRING, "record": STRING, "deliverable": {"type": "string", "enum": sorted(TERMINALS)},
        "scope": {"type": "object", "description": "Computational scope, not output selection. Continuous: channels,start,end. Event: labels,tmin,tmax only (tools compute all channels; select requested output channel later). Record info/list_events: {}."},
        "checks": {**STRINGS, "description": "Required prerequisite tools for this delivery, e.g. epoch_quality. Completion checks actual successes on the same artifact."},
        "criteria": {"type": "array", "items": {"type": "object", "properties": {
            "tool": STRING, "path": {"type": "array"}, "op": {"type": "string", "enum": ["eq", "gte", "lte"]},
            "value": {}}, "required": ["tool", "path", "op", "value"], "additionalProperties": False},
            "description": "Optional user-stated acceptance conditions on actual observation fields; not inferred scientific thresholds."},
        "revision_of": STRING, "dependencies": STRINGS,
    }, ["title", "record", "deliverable", "scope"]),
    control("close_subgoal", "Archive only after actual delivery, or suspend with an unresolved question. Never infer scientific success from API success.", {
        "subgoal_id": {"type": "string", "description": "Optional exact pending subgoal. Verified close after suspension/restoration needs no numerical rerun."},
        "status": {"type": "string", "enum": ["completed", "suspended"]},
        "unresolved": STRINGS}, ["status"]),
    control("resume_subgoal", "Resume an unchanged suspended scientific scope. Changed parameters require a new subgoal/version.", {
        "subgoal_id": STRING}, ["subgoal_id"]),
    control("read_evidence", "Read exact archived result or up to four scalar paths. Use displayed task id, record and exact parameters. Index alone is not a value.", {
        "task_id": STRING, "record": STRING, "parameters": {"type": "object"},
        "field_paths": {"type": "array", "items": {"type": "array"}}},
        ["task_id", "record", "parameters"]),
    control("restore_subgoal", "Restore an archived subgoal's real action-observation trajectory for a processing decision or unresolved issue. Scalar lookups use read_evidence; do not restore unnecessarily.", {
        "subgoal_id": STRING, "reason": STRING}, ["subgoal_id", "reason"]),
    control("finish_task", "Deliver the current user's answer or a specific clarification. This does not prove intent completeness. Values must be grounded in visible evidence.", {
        "status": {"type": "string", "enum": ["completed", "partial", "clarification_required"]},
        "answer": STRING, "unresolved": STRINGS}, ["status", "answer"]),
]

SYSTEM = """你是合成 EEG 研究助手。通过原 EEG 工具逐步分析，不作诊断。
用户请求的全部原文持续可见，禁止操作不得被摘要覆盖；不要猜科学参数或标签。
每次只调用一个工具，读取真实观察后再决定下一行动。简单连续/记录查询可直接调用数值工具，自动记录单步子目标；默认记录见 active_record。
多步任务、跨记录或参数修订用 begin_subgoal：按科学交付物而非每个工具划分。scope 连续是绝对秒 start/end/channels；事件是相对事件秒 labels/tmin/tmax，不是 artifact_id。本模式不执行基线校正。
事件分析先获得真实 Epoch 工件 ID，再用原工具检查和分析；checks 声明用户要求的必要检查。criteria 可声明用户给定的可核查条件，如 create_epochs.valid_epoch_count >= 2；不要发明科学阈值。只有实际满足条件才继续。
完成子目标用 close_subgoal；程序验证实际交付与同工件检查，随后用摘要替换详细历史。失败或未决条件用 suspended/clarification，不得宣称已成功。
用户修改已完成分析参数时，新子目标使用 revision_of 指向旧 task_id 或已完成 subgoal_id（程序解析同一版本）；引用旧分析用 dependencies。不暗改旧结果。不支持的筛选、重参考、模型推理等应说明范围并澄清。
小型事实已可见可直接使用。read_evidence 查具体结果，restore_subgoal 恢复旧行动—观察以核查处理过程/继续分析；二者不同，不为展示机制多读。
精确证据字段含路径、值、来源、科学范围和单位，索引不是值。绝对频带功率 V²，幅值 V；不同记录/时间基准/版本不可混同。
用 finish_task 输出完整中文回答或明确缺参问题，保留局限；不得只返回无工具的文字。完成状态只是可核查的执行契约，不证明全部科学意图。
"""


class WorkingMemoryController:
    def __init__(self, store, *, context_mode="working", max_restores=4,
                 max_context_bytes=96000, no_progress_limit=3, timeout_seconds=300):
        if context_mode not in {"working", "full"}:
            raise ValueError("Unknown context mode")
        self.store = store
        self.context_mode = context_mode
        self.max_restores = max_restores
        self.max_context_bytes = max_context_bytes
        self.no_progress_limit = no_progress_limit
        self.timeout_seconds = timeout_seconds
        self.cancelled = False
        self.requests = []
        self.exchanges = []
        self.decisions = []
        self.outcomes = []
        self.restored = {}

    def begin_turn(self, request):
        if not isinstance(request, str) or not request.strip():
            raise ValueError("A natural language request is required")
        self.store.turn += 1
        self.requests.append(request)
        self.stop_reason = None
        self.final_answer = ""
        self.errors = 0
        self.last_error = None
        self.repeats = {}
        self.restore_count = 0
        self.turn_evidence = []
        self.restored = {}
        self.pending = []
        self.feedback = None
        self.started = time.monotonic()

    def tool_definitions(self):
        registry = next(iter(self.store.contexts.values())).executor.registry
        return [registry.get(n).public_definition() for n in sorted(NUMERIC_TOOLS)] + clone(CONTROLS)

    def check_stop(self):
        if self.cancelled:
            return "cancelled"
        if time.monotonic() - self.started > self.timeout_seconds:
            return "deadline_exceeded"
        if self.errors >= self.no_progress_limit:
            return "no_progress"
        return self.stop_reason

    def build_messages(self):
        store = self.store
        summaries = [store.summary(g) for g in store.subgoals if g is not store.active]
        visible = []
        for card in summaries:
            entry = store.find_entry(card["task_id"])
            if entry:
                visible.append({**_entry_meta(entry), "fields": [
                    {**f, "via": ["summary"]} for f in card["evidence"]["fields"]]})
        union, _ = merge_evidence(visible, self.turn_evidence)
        if union["status"] != "ok":
            self.stop_reason = "evidence_capacity"
            return []
        metadata = {key: {"source": r.source, "sfreq": r.sfreq,
                          "channels": list(r.channel_names), "duration": r.duration_seconds,
                          "event_labels": sorted({e.label for e in r.events.events}) if r.events else []}
                    for key, r in store.records.items()}
        payload = {"user_requests": self.requests, "current_request": self.requests[-1],
                   "records": metadata, "active_record": store.active_record,
                   "archived_summaries": summaries,
                   "active_subgoal": store.summary(store.active) if store.active else None,
                   "restored_trajectories": list(self.restored.values()),
                   "exact_evidence": union["items"], "control_feedback": self.feedback}
        messages = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": encoded(payload).decode("utf-8")}]
        if self.context_mode == "full":
            pairs = self.exchanges
        else:
            pairs = list(store.active.exchanges) if store.active else []
            # Successful close/restore is already represented in the grounded
            # archive/restoration payload. Retain neither half of that duplicate
            # protocol pair. Rejections still remain observable for recovery.
            pending = self.pending
            if pending and pending[-1]["name"] in {"restore_subgoal", "close_subgoal"} and json.loads(pending[-1]["content"])["success"]:
                pending = []
            if pending and (not pairs or pairs[-1] != pending):
                pairs = pairs + [pending]
        for pair in pairs:
            messages.extend(clone(pair))
        if len(encoded(messages)) > self.max_context_bytes:
            self.stop_reason = "context_capacity"
            return []
        self.decisions.append({"turn": store.turn, "before_action": len(self.exchanges) + 1,
                               "active_subgoal": store.active.subgoal_id if store.active else None,
                               "messages": clone(messages), "context_bytes": len(encoded(messages))})
        return messages

    def _dispatch(self, request):
        name, args = request.name, dict(request.arguments)
        store = self.store
        if name in NUMERIC_TOOLS:
            return store.execute_numeric(name, args)
        spec = next((c["function"] for c in CONTROLS if c["function"]["name"] == name), None)
        if spec is None:
            return store._error("TOOL_NOT_AVAILABLE", "Tool is not enabled in this mode")
        _validate_schema(args, spec["parameters"])
        if name == "restore_subgoal":
            if self.restore_count >= self.max_restores:
                return store._error("RESTORE_LIMIT", "Trajectory restoration limit reached")
            if not isinstance(args["reason"], str) or not args["reason"].strip():
                return store._error("REASON_REQUIRED", "State the processing question, not private reasoning")
            result = store.restore_subgoal(args["subgoal_id"])
            if result["status"] == "restored":
                self.restore_count += 1
                # Native protocol is retained in external archive; embed observations
                # as data here, never orphan tool-role messages.
                result.pop("native_exchanges", None)
                result["reason"] = args["reason"]
                self.restored[args["subgoal_id"]] = clone(result)
                store.events.append({"event": "restored", "subgoal_id": args["subgoal_id"],
                                     "reason": args["reason"], "turn": store.turn})
            return result
        if name == "finish_task":
            status = args["status"]
            unresolved = args.get("unresolved", [])
            if status not in {"completed", "partial", "clarification_required"}:
                return store._error("INVALID_STATUS", "Unknown delivery status")
            pending = [g for g in store.subgoals if g.status != "completed" and
                       (g.turn == store.turn or g.subgoal_id in self.restored)]
            if status == "completed" and (store.active or unresolved or pending):
                return {**store._error("UNFINISHED_SUBGOAL", "Resolve or explicitly report pending work"),
                        "pending": [store.summary(g) for g in pending]}
            if status != "completed" and (not unresolved or not isinstance(unresolved, list)):
                return store._error("UNRESOLVED_REQUIRED", "Name the missing information or limitation")
            if status in {"completed", "partial"} and not store.entries:
                return store._error("NO_EVIDENCE", "No actual analysis has been delivered")
            self.stop_reason, self.final_answer = status, args["answer"]
            return {"status": status, "unresolved": unresolved, "answer": self.final_answer}
        return getattr(store, name)(**args)

    def execute(self, request, *, batch_size=1):
        self.store.last_owner = None
        before = len(self.store.entries)
        start = time.perf_counter()
        try:
            if batch_size != 1:
                result = self.store._error("SEQUENTIAL_ACTION_REQUIRED", "Observe each action before selecting the next")
            else:
                result = self._dispatch(request)
        except (ValueError, TypeError, KeyError):
            result = self.store._error("INVALID_CONTROL_ARGUMENT", "Check the advertised schema and scientific scope")
        except Exception:
            result = self.store._error("INTERNAL_CONTROL_ERROR", "Control failed safely; no traceback is sent to the model")
        successful = result.get("status") not in {"rejected", "blocked"}
        # Rejected multi-call batches are one failed decision. Distinct corrected
        # input errors are not evidence of repeating the same non-progress loop.
        signature = (request.name, result.get("code", "TOOL_BLOCKED"))
        self.errors = (0 if successful else self.errors + 1 if signature == self.last_error else 1)
        self.last_error = None if successful else signature
        key = encoded({"tool": request.name, "args": dict(request.arguments)})
        self.repeats[key] = self.repeats.get(key, 0) + 1
        if self.repeats[key] > self.no_progress_limit:
            self.stop_reason = "repeated_action"
        if successful and request.name == "read_evidence" and result.get("evidence"):
            self.turn_evidence.append(result["evidence"])
        for entry in self.store.entries[before:]:
            self.turn_evidence.append({**_entry_meta(entry), "fields": [
                {"path": p, "value": v, "via": ["executed_this_turn"]}
                for p, v in scalar_paths(entry.result)]})
        return ToolResult(request.request_id, request.name, successful, data=result,
                          error_code=None if successful else result.get("code", "TOOL_BLOCKED"),
                          error_message=None if successful else result.get("message", "Inspect actual observation"),
                          duration_ms=(time.perf_counter() - start) * 1000)

    def observe_exchange(self, assistant, responses):
        pair = [{"role": "assistant", "content": assistant.get("content"),
                 "tool_calls": clone(assistant["tool_calls"])}] + clone(responses)
        self.exchanges.append(pair)
        self.pending = pair
        owner = self.store.find_subgoal(self.store.last_owner)
        if owner:
            owner.exchanges.append(pair)
        self.feedback = None

    def on_unstructured_answer(self, answer):
        self.errors += 1
        self.feedback = "Use finish_task to distinguish delivery, partial work and clarification. No task was completed by free text."
        self.outcomes.append({"turn": self.store.turn, "event": "unstructured_answer", "answer": answer})

    def on_stop(self, reason):
        if self.store.active:
            self.store.active.status = "awaiting_input" if reason == "clarification_required" else "suspended"
            self.store.active.unresolved = self.store.active.unresolved or [reason]
        self.outcomes.append({"turn": self.store.turn, "stop_reason": reason, "answer": self.final_answer})

    def snapshot(self):
        return {"session_id": self.store.session_id, "context_mode": self.context_mode,
                "requests": clone(self.requests), "subgoals": [self.store.summary(g) for g in self.store.subgoals],
                "events": clone(self.store.events), "decisions": clone(self.decisions),
                "exchanges": clone(self.exchanges), "outcomes": clone(self.outcomes),
                "record_traces": {k: c.trace.to_dict() for k, c in self.store.contexts.items()}}


class WorkingMemoryEEGAgent(EEGAgent):
    """Convenience constructor; run/continue use the original EEGAgent.run."""

    def __init__(self, llm_client, records, *, session_id="wm", max_rounds=24,
                 max_tool_calls=24, config=None, **memory_options):
        store = WorkingMemoryStore(session_id, records, config=config)
        controller = WorkingMemoryController(store, **memory_options)
        super().__init__(llm_client, next(iter(store.contexts.values())), max_rounds,
                         max_tool_calls, working_memory=controller)

    def continue_run(self, user_request):
        return self.run(user_request)

    def cancel(self):
        self.working_memory.cancelled = True
