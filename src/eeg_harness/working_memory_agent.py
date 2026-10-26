"""Opt-in working-memory hooks for EEGAgent, not a second agent/executor loop."""

import json
import time

from .agent import EEGAgent
from .executor import _validate_schema
from .tooling import ToolResult
from .working_memory import WorkingMemoryStore, NUMERIC_TOOLS, TERMINALS, clone, encoded
from .research.task_memory_evidence import merge_evidence, _entry_meta, scalar_paths, MAX_EVIDENCE_BYTES
from .result_semantics import result_field_semantics, UnsupportedResultField, read_scalar


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


def multi_result_controls():
    controls = clone(CONTROLS)
    controls[0] = control("begin_subgoal", "Declare one scientific purpose with required and optional delivery items, not an action sequence. Different scopes of the same tool are separate items.", {
        "title": STRING, "record": STRING,
        "deliveries": {"type": "array", "items": {"type": "object", "properties": {
            "key": STRING, "tool": {"type": "string", "enum": sorted(NUMERIC_TOOLS)},
            "scope": {"type": "object", "description": "Continuous: channels/start/end; event: labels/tmin/tmax; record metadata: {}. No output-channel selector in event scope."},
            "required": {"type": "boolean"}, "revision_of": STRING},
            "required": ["key", "tool", "scope"], "additionalProperties": False}},
        "dependencies": STRINGS,
        "criteria": {"type": "array", "items": {"type": "object", "properties": {
            "delivery": STRING, "path": {"type": "array"}, "op": {"type": "string", "enum": ["eq", "gte", "lte"]},
            "value": {}}, "required": ["delivery", "path", "op", "value"], "additionalProperties": False}},
    }, ["title", "record", "deliveries"])
    controls.append(control("reuse_result", "Bind a previously computed exact result to an active delivery instead of recomputing. Program verifies record, scope, version and current object identity. This is not reading a scalar or restoring a trajectory.", {
        "delivery_key": STRING, "task_id": STRING}, ["delivery_key", "task_id"]))
    return controls


MULTI_RESULT_SYSTEM = """
你是合成 EEG 研究助手；不作诊断，不猜参数、标签或科学阈值。用户原文持续可见。
每次一个工具，依据实际观察再决定下一步。简单记录/连续查询可直接执行并自动归档，默认记录见 active_record。
当前采用多结果交付契约：begin_subgoal 的 deliveries 列出同一科学目的的必需/可选工具结果及各自 scope，而不是预先决定动作序列。相同工具的不同窗口须分别声明。
连续 scope 为通道和记录绝对时间 start/end；事件 scope 为 labels/tmin/tmax 相对秒，不含输出通道选择。先获得真实 Epoch ID 再测量；不支持基线校正、筛选、重参考或模型推理，不能假装已执行。
每个成功结果都有独立 task_id；整个子目标有 subgoal_id，多个结果时二者不可混用。修订使用对应 delivery 的 revision_of 指向准确旧结果。
已成功结果立即可读，子目标完成须所有 required 项及 criteria 满足；可选失败保留限制但不否定已完成必需项。
criteria 用 delivery 键和真实字段表达用户明确要求的条件；工具成功不代表科学条件成立。未满足时不能宣称成功。
恢复过程使用 restore_subgoal；在同一真实工件上继续计算可直接使用恢复出的 artifact_id。已有适用结果用 reuse_result 绑定到相同交付项，不必重复计算。参数变更须新结果，不能拿旧窗口顶替。
摘要的 results 列出所有实际结果、读回地址、修订关系；历史结果存在不等于仍满足当前数据状态，binding_valid=false 时不可作当前证据。
read_evidence 查精确字段；restore_subgoal 查处理过程，二者有不同用途。索引不是数值。频带绝对功率单位 V²，幅值 V，保持来源、版本和时间基准。
close_subgoal(completed) 需通过程序检查；未决时 suspend，继续原范围可 resume_subgoal。finish_task 区分完成、部分交付、缺参澄清；回答不能省略必要结果或把试次窗口功率解释为 ERD/ERS、诊断或能力评分。
"""

SOURCE_SCHEMA = {"type": "object", "description":
    "Scientific parameter provenance. User: {kind:'user',turn:1,quote:'exact relevant user span'}; "
    "inherit: {kind:'result',result_id:'actual task_id'}; artifact: {kind:'artifact',artifact_id:'actual id'}. "
    "For mixed origins use {fields:{start:source,end:source,channels:source}}. "
    "Only literal supported values and matching record/scope pass; source:user alone is not authority."}


def lifecycle_controls(request_closure=False):
    controls = multi_result_controls()
    begin = controls[0]["function"]
    begin["parameters"]["properties"]["parameter_sources"] = {
        "type": "object", "description": "Map each delivery key to its scientific parameter source; optional 'record' source for record selection. Missing or unsupported scope is saved awaiting clarification."}
    begin["parameters"]["properties"]["dependencies"]["description"] = (
        "Existing result/task IDs only, not future delivery keys. Omit when no actual historical result is needed.")
    begin["parameters"]["properties"]["criteria"]["description"] = (
        "Only an explicit user acceptance threshold, not invented tool prerequisites. No criteria needed merely to query a count or power. Use declared field paths, e.g. list_events.labels.<label>.")
    begin["parameters"]["properties"]["recompute_source"] = SOURCE_SCHEMA
    if request_closure:
        begin["parameters"]["properties"]["requirements"] = {"type": "array", "items": {
            "type": "object", "properties": {"quote": STRING, "delivery_keys": STRINGS},
            "required": ["quote", "delivery_keys"], "additionalProperties": False},
            "description": "Alongside this goal, quote the original requested outputs and associate each with local delivery keys; not an action sequence or an independent proof of full intent."}
        finish = next(c["function"] for c in controls if c["function"]["name"] == "finish_task")
        finish["parameters"]["properties"].update(coverage={"type": "array", "items": {
            "type": "object", "properties": {"quote": STRING, "result_ids": {
                **STRINGS, "description": "Actual visible evidence only; stored unread locators are not evidence. Use [] for an undelivered item and describe it in unresolved."}, "unresolved": STRING},
            "required": ["quote", "result_ids"], "additionalProperties": False}}, coverage_complete={"type": "boolean"})
        finish["parameters"]["required"] += ["coverage", "coverage_complete"]
    controls.append(control("amend_subgoal", "Correct technical field expressions or fill previously missing scientific parameters in the SAME pending goal; cannot weaken conditions or change known scope. A scientific revision needs a new goal with revision_of.", {
        "subgoal_id": STRING,
        "updates": {"type": "object", "description": "Map delivery key to only missing scope fields"},
        "parameter_sources": {"type": "object", "description": "Same per-delivery provenance format as begin_subgoal"},
        "criterion_paths": {"type": "object", "description": "Map criterion index string to corrected path array; op/value/required remain fixed"}}, ["subgoal_id"]))
    return controls


LIFECYCLE_SYSTEM = """你是合成EEG科学分析助手。所有数值来自原工具，不作诊断。用户原文与真实状态持续可见。
用户目的可包含多项交付。begin_subgoal仅声明所需结果，不给固定动作序列；缺科学参数时仍可用部分scope声明，程序保存awaiting_input。通过finish_task(clarification_required)询问缺项。用户补充后amend_subgoal补入同一目的，不重建无关目标。
科学scope必须有依据：parameter_sources按delivery key给原用户逐字quote及turn，或准确旧result_id/实际artifact_id；混合来源用fields。不要改写quote、猜时间窗或把全部元数据当成用户选择。常规执行默认不需要用户重填；record默认当前选择，换记录需可核对来源。
连续scope是channels/start/end记录绝对秒；事件scope是labels/tmin/tmax相对秒，工具计算全部通道。不同时间窗必须不同交付；修订用对应delivery.revision_of指向准确旧结果，保留旧数值。
记录/事件列表可直接查。已知范围的简单分析可直接调用并提供parameter_sources，多结果用begin_subgoal。缺参时不得先执行相关数值动作。
当前接口在原循环中串行执行同一响应的多个动作。独立动作可同批；依赖尚未返回的结果/工件必须等实际观察后再调用，绝不猜ID。subgoal_id是目的，task_id是实际结果，delivery key只是该目的内的项目名，artifact_id是数据对象。
每次数值成功已自动记录并关联delivery_check；本目标刚算出的结果无需reuse_result。不必反复绑定。reuse_result只用于已有适用历史结果；无变化会明示。
criteria仅表达用户明确的验收条件，无阈值就不要添加条件。查询0个事件也可以完整。条件字段错误、无结果和真实条件不满足不同，依据诊断修正技术表达；不得删条件/改阈值/把必需降成可选换取完成。
目标required齐全后close_subgoal(completed)，缺项则继续或明确暂停；用户未声明的目的遗漏仍不能算完整交付。
read_evidence读取准确字段；restore_subgoal恢复真实行动—观察以继续旧过程/说明处理，非必要不恢复。恢复提供的实际工件可以继续测量；不同记录/版本/相同数值不代表同一证据。依赖旧值时声明dependencies或读取它。
本模式只开放记录信息、连续幅值/PSD/质量和事件Epoch/计数/质量/绝对功率。不支持筛选、基线校正、重参考或模型推理。质量标准未配置就说明，不编造合格阈值。
finish_task区分完整、部分和澄清，回答提供请求的关键值/比较、范围、单位及限制。功率V²、幅值V、频率Hz、计数无量纲，以字段语义为准。不得只在存储中完成而省略最后答案。
"""

REQUEST_CLOSURE_SYSTEM = """
本入口同时维护原请求进度：复杂目的在begin_subgoal同轮可用requirements把用户原文要求关联到delivery_keys；不用额外登记回合。当前request_progress区分声明已完成与原请求完整，不可漏掉原文中的其它输出。
相同科学结果有效时用返回的旧结果和进度，不因换title/key重算；明确用户重算才给recompute_source，科学范围改变走新版本。
归档不是重新开始的信号。已完成原需求就finish_task，coverage逐项引用相关用户原文和实际看见的result_ids，coverage_complete只是你对原需求的复核声明，程序不会证明所有语言语义。
finish_task可以依据真实完成检查自动归档已有效的当前目的，无需为了收尾再调用close。缺项、能力限制或资源限制用partial/clarification_required和真实未决事项，不写completed。
质量阈值只能根据实际质量工具结果说明；用户未给验收阈值不等于系统没有经验规则，未测量不能声称质量合格。普通两值相对差不是基线归一化ERD/ERS。
"""


class WorkingMemoryController:
    def __init__(self, store, *, context_mode="working", max_restores=4,
                 max_context_bytes=96000, no_progress_limit=3, timeout_seconds=300,
                 request_closure=False):
        if context_mode not in {"working", "full", "summary"}:
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
        self.lifecycle = hasattr(store, "amend_subgoal")
        self.request_closure = request_closure
        if request_closure and not self.lifecycle:
            raise ValueError("Request closure uses the scientifically grounded lifecycle")
        from .working_memory_request import RequestProgress
        self.request_progress = RequestProgress(self) if request_closure else None

    def begin_turn(self, request):
        if not isinstance(request, str) or not request.strip():
            raise ValueError("A natural language request is required")
        self.store.turn += 1
        self.requests.append(request)
        if self.lifecycle:
            self.store.user_requests = clone(self.requests)
            # A pending old objective remains discoverable but cannot hold an
            # unrelated new request hostage. Resumption is an explicit action.
            if self.store.active:
                if self.store.active.status == "active":
                    self.store.active.status = "suspended"
                self.store.active = None
        self.action_owners = {}
        self.touched_goals = set()
        self.stop_reason = None
        self.final_answer = ""
        self.errors = 0
        self.last_error = None
        self.repeats = {}
        self.restore_count = 0
        self.turn_evidence = []
        self.turn_entry_start = len(self.store.entries)
        self.restored = {}
        self.pending = []
        self.feedback = None
        self.started = time.monotonic()
        self.final_only = False
        self.finalization_reason = None
        self.visible_evidence_ids = set()
        if self.request_progress:
            self.request_progress.begin_turn(request)

    def tool_definitions(self):
        if self.request_closure and getattr(self, "final_only", False):
            return self.final_tools()
        registry = next(iter(self.store.contexts.values())).executor.registry
        numeric = [clone(registry.get(n).public_definition()) for n in sorted(NUMERIC_TOOLS)]
        if self.lifecycle:
            for tool in numeric:
                tool["function"]["parameters"]["properties"]["parameter_sources"] = SOURCE_SCHEMA
                tool["function"]["parameters"]["properties"]["record"] = {
                    "type": "string", "description": "Optional known record alias for a direct short task; no alias means current record. An active scientific goal cannot silently switch records."}
                if self.request_closure:
                    spec = registry.get(tool["function"]["name"])
                    if spec.preconditions:
                        tool["function"]["description"] += " Actual execution prerequisites: " + json.dumps(spec.preconditions)
        return numeric + self.control_definitions()

    def control_definitions(self):
        if self.lifecycle:
            return lifecycle_controls(self.request_closure)
        return multi_result_controls() if hasattr(self.store, "reuse_result") else clone(CONTROLS)

    def check_stop(self):
        if self.cancelled:
            return "cancelled"
        if time.monotonic() - self.started > self.timeout_seconds:
            return "deadline_exceeded"
        if self.errors >= self.no_progress_limit:
            return "no_progress"
        return self.stop_reason

    def final_tools(self):
        return [c for c in self.control_definitions() if c["function"]["name"] == "finish_task"]

    def prepare_finalization(self, reason="budget_reserve"):
        self.final_only, self.finalization_reason = True, reason

    def build_final_messages(self, reason="budget_reserve"):
        return self.build_messages(record_decision=False, final_preview=reason), self.final_tools()

    def build_messages(self, *, record_decision=True, final_preview=None):
        store = self.store
        summaries = [store.summary(g) for g in store.subgoals if g is not store.active]
        visible = []
        cards = summaries + ([store.summary(store.active)] if store.active and hasattr(store, "reuse_result") else [])
        selected = self._required_evidence_ids()
        for card in cards:
            for result_card in card.get("results", [card]):
                entry = store.find_entry(result_card["task_id"])
                if entry and entry.task_id in selected:
                    visible.append({**_entry_meta(entry), "fields": [
                        {**f, "via": ["summary"]} for f in result_card["evidence"]["fields"]]})
        union, _ = merge_evidence(visible, self.turn_evidence)
        if union["status"] != "ok":
            self.stop_reason = "evidence_capacity"
            return []
        for item in union["items"]:
            entry = store.find_entry(item["task_id"])
            owner = store.find_subgoal(entry.evidence.get("subgoal_id"))
            if owner is None:
                owner = next((g for g in store.subgoals if g.task_id == entry.task_id), None)
            item["created_turn"] = owner.turn if owner else None
            item["acquired_this_turn"] = entry.sequence > self.turn_entry_start
            item["unit_scope"] = "tool category only; use field semantics for each value"
            for field in item["fields"]:
                try:
                    semantics = result_field_semantics(entry.capability, field["path"], entry.result,
                        parameters=entry.parameters, analysis_configuration=entry.evidence["analysis_configuration"])
                    field["semantics"] = {"kind": semantics["kind"], "unit": semantics["unit_or_kind"]}
                except UnsupportedResultField:
                    field["semantics"] = {"kind": "unregistered", "unit": None}
        if len(encoded(union["items"])) > MAX_EVIDENCE_BYTES:
            self.stop_reason = "evidence_capacity"
            return []
        metadata = {key: {"source": r.source, "sfreq": r.sfreq,
                          "channels": list(r.channel_names), "duration": r.duration_seconds,
                          "event_labels": sorted({e.label for e in r.events.events}) if r.events else []}
                    for key, r in store.records.items()}
        index_card = self._lifecycle_index if self.lifecycle else self._index_summary
        payload = {"user_requests": self.requests, "current_request": self.requests[-1], "current_turn": store.turn,
                   "records": metadata, "active_record": store.active_record,
                   "archived_summaries": [index_card(c, selected) for c in summaries],
                   "active_subgoal": index_card(store.summary(store.active), selected) if store.active else None,
                   "restored_trajectories": list(self.restored.values()),
                   "exact_evidence": union["items"], "control_feedback": self.feedback,
                   "evidence_workspace": {"selected_result_ids": sorted(selected | {e["task_id"] for e in self.turn_evidence}),
                       "stored_result_count": len(store.entries),
                       "policy": "current-turn results, explicit dependencies/revisions, reuse/read/restore; archive indexes are not values"}}
        if self.context_mode == "summary":
            # A strong generic cumulative factual summary: all completed and
            # pending purposes, records, versions and small result facts survive.
            # Uses no EEG-specific retrieval weights or future query/gold.
            payload["generic_summary"] = self._generic_summary(selected)
            payload.pop("archived_summaries")
        if self.request_progress:
            payload["request_progress"] = self.request_progress.view()
            if self.final_only or final_preview:
                payload["delivery_phase"] = {"reason": final_preview or self.finalization_reason,
                    "instruction": "Resources are protected for delivery; this is not a claim that the API token allowance is exhausted. Only finish_task is available. Cite actual visible results; leave result_ids empty for unread/missing evidence and describe unresolved work. Report only scientifically checked conditions, not unexecuted assumptions."}
        messages = [{"role": "system", "content": (LIFECYCLE_SYSTEM if self.lifecycle else MULTI_RESULT_SYSTEM if hasattr(store, "reuse_result") else SYSTEM) + (REQUEST_CLOSURE_SYSTEM if self.request_closure else "")},
                    {"role": "user", "content": encoded(payload).decode("utf-8")}]
        if self.context_mode == "full":
            pairs = self.exchanges
        else:
            pairs = list(store.active.exchanges) if store.active else []
            if self.lifecycle or self.context_mode == "summary":
                # Grounded progress and exact values already carry resolved
                # observations. Keep the latest feedback; full native traces
                # remain recoverable outside the bounded working view.
                # pending is the complete latest native batch. Appending it
                # beside a goal-projected subset would duplicate that batch.
                pairs = []
            # Successful close/restore is already represented in the grounded
            # archive/restoration payload. Retain neither half of that duplicate
            # protocol pair. Rejections still remain observable for recovery.
            pending = self.pending
            if not self.request_closure and pending and pending[-1]["name"] in {"restore_subgoal", "close_subgoal"} and json.loads(pending[-1]["content"])["success"]:
                pending = []
            if pending and (not pairs or pairs[-1] != pending):
                pairs = pairs + [pending]
        for pair in pairs:
            messages.extend(clone(pair))
        message_bytes = len(json.dumps(messages, ensure_ascii=False).encode("utf-8")) if self.request_closure else len(encoded(messages))
        if message_bytes > self.max_context_bytes:
            if record_decision:
                self.stop_reason = "context_capacity"
            return []
        if record_decision:
            self.visible_evidence_ids = self._visible_results(messages) if self.request_closure else {e["task_id"] for e in union["items"]}
            self.decisions.append({"turn": store.turn, "before_action": len(self.exchanges) + 1,
                               "active_subgoal": store.active.subgoal_id if store.active else None,
                               "messages": clone(messages), "context_bytes": len(encoded(messages)),
                               "input_components_bytes": {
                                   "system": len(encoded(messages[0])),
                                   "tool_schema": len(encoded(self.tool_definitions())),
                                   "user_original": len(encoded({k:payload[k] for k in ("user_requests", "current_request")})),
                                   "current_state": len(encoded({k:payload[k] for k in ("records", "active_record", "active_subgoal", "control_feedback", "evidence_workspace", "request_progress", "delivery_phase") if k in payload})),
                                   "history_index_or_summary": len(encoded(payload.get("generic_summary", payload.get("archived_summaries", [])))),
                                   "exact_evidence": len(encoded(payload["exact_evidence"])),
                                   "active_or_full_trajectory": len(encoded(pairs)),
                                   "restored_trajectory": len(encoded(payload["restored_trajectories"])),
                               }})
        return messages

    def _visible_results(self, messages):
        """Recognize actual values across ALL shared context representations.

        Strong summary/full may answer directly from an exact fact outside the
        selected union. A locator alone never counts. This is result-level
        provenance, not a proof that every assertion in final prose is true.
        """
        visible = set()
        def scan(value):
            if isinstance(value, list):
                for item in value:
                    scan(item)
            elif isinstance(value, dict):
                ident = value.get("task_id")
                entry = self.store.find_entry(ident) if isinstance(ident, str) else None
                fields = value.get("fields") or (value.get("evidence") or {}).get("fields")
                if entry and isinstance(fields, list) and fields and self.store._binding_valid(entry):
                    try:
                        if all(isinstance(f, dict) and read_scalar(entry.result, f["path"]) == f["value"] for f in fields):
                            visible.add(entry.task_id)
                    except (KeyError, TypeError, ValueError, UnsupportedResultField):
                        pass
                ident = value.get("result_id")
                entry = self.store.find_entry(ident) if isinstance(ident, str) else None
                result = value.get("result") if isinstance(value.get("result"), dict) else {}
                if entry and result.get("success") and result.get("data") == entry.result and self.store._binding_valid(entry):
                    visible.add(entry.task_id)
                for item in value.values():
                    if isinstance(item, (dict, list)):
                        scan(item)
        for message in messages:
            if message.get("role") not in {"user", "tool"}:
                # Assistant free text and proposed tool arguments are not
                # observations, even if they imitate a real evidence shape.
                continue
            try:
                scan(json.loads(message.get("content") or "null"))
            except (ValueError, TypeError):
                pass
        return visible

    def _generic_summary(self, selected):
        summary = []
        for goal in self.store.subgoals:
            card = self.store.summary(goal)
            facts = []
            for result in card.get("results", [card]):
                if not result.get("task_id"):
                    continue
                facts.append({k: clone(result[k]) for k in ("task_id", "record", "capability", "parameters", "revision_of", "evidence", "artifact_id", "binding_valid") if k in result})
                # The same current exact values are already present in the
                # common workspace, not repeated here.
                if result["task_id"] in selected and facts[-1].get("evidence"):
                    facts[-1]["evidence"].pop("fields", None)
            summary.append({"subgoal_id": goal.subgoal_id, "purpose": goal.title, "record": goal.record,
                            "status": goal.status, "unresolved": clone(goal.unresolved),
                            "progress": card.get("delivery_check"), "facts": facts})
        return summary

    def _required_evidence_ids(self):
        """No gold, query keywords, or automatic all-history injection.

        A turn is a delivery unit: do not silently evict an earlier required
        value when another is read. Capacity applies to this working set, not
        the external archive. Oversized simultaneous delivery still stops.
        """
        store = self.store
        selected = {e.task_id for e in store.entries[self.turn_entry_start:]}
        for goal in store.subgoals:
            if goal is store.active or goal.turn == store.turn or goal.subgoal_id in self.restored or goal.subgoal_id in self.touched_goals:
                selected.update(getattr(goal, "result_ids", []))
                if goal.task_id:
                    selected.add(goal.task_id)
                selected.update(goal.dependencies)
                selected.update(getattr(goal, "reused", {}).values())
                if goal.revision_of:
                    selected.add(goal.revision_of)
                selected.update(d["revision_of"] for d in getattr(goal, "deliveries", []) if d.get("revision_of"))
        return selected

    @staticmethod
    def _index_summary(card, selected):
        """Discoverable scientific locators outside the exact-value workspace."""
        index = clone(card)
        # The legacy single-result archive keeps prerequisite observations as
        # checked facts. Retain them only for explicitly relevant/current work.
        if card.get("task_id") not in selected:
            index.pop("checked_facts", None)
        for result in index.get("results", [index]):
            proof = result.get("evidence")
            if proof:
                fields = proof.pop("fields", [])
                proof["preview_field_count"] = len(fields)
                proof.pop("omitted_fields", None)
                proof["representation"] = "index_only; read_evidence returns exact values"
        return index

    @staticmethod
    def _lifecycle_index(card, selected):
        """A locator/progress view, not a second serialization of the archive.

        Full sources, criterion revision history and scientific configuration
        remain in the actual goal/results and are restored verbatim. Current
        exact evidence retains values/units/configuration in the common union.
        """
        keep = ("subgoal_id", "title", "created_turn", "record", "status", "deliveries", "criteria",
                "dependencies", "unresolved", "admission_issues", "delivery_check", "result_ids",
                "references", "failed_attempts", "recompute_source", "prior_equivalent_results")
        out = {k: clone(card[k]) for k in keep if k in card}
        grouped = {}
        for delivery, fields in card.get("parameter_sources", {}).items():
            groups = {}
            for name, source in fields.items():
                ident = encoded(source)
                groups.setdefault(ident, {"fields": [], "source": clone(source)})["fields"].append(name)
            grouped[delivery] = list(groups.values())
        out["verified_sources"] = grouped
        out["contract_revision_count"] = len(card.get("contract_revisions", []))
        if card.get("status") != "completed":
            out["output_contracts"] = clone(card.get("output_contracts", {}))
        out["results"] = []
        for result in card.get("results", []):
            row = {k: clone(result[k]) for k in ("task_id", "record", "capability", "parameters",
                    "revision_of", "delivery_key", "binding_valid", "superseded_by", "artifact_id") if k in result}
            proof = result.get("evidence", {})
            row.update(source=proof.get("source"), unit_or_kind=proof.get("unit_or_kind"),
                       readable_fields=clone(proof.get("readable_fields", [])),
                       representation="locator; current exact values are in exact_evidence, otherwise read_evidence")
            out["results"].append(row)
        return out

    def _dispatch(self, request):
        name, args = request.name, dict(request.arguments)
        store = self.store
        if self.request_closure and self.final_only and name != "finish_task":
            return store._error("FINAL_DELIVERY_ONLY", "Resources are reserved for a grounded final or partial answer, not further numerical actions")
        if name in NUMERIC_TOOLS:
            if self.lifecycle:
                sources = args.pop("parameter_sources", None)
                record = args.pop("record", None)
                return store.execute_numeric(name, args, parameter_sources=sources, record=record)
            return store.execute_numeric(name, args)
        spec = next((c["function"] for c in self.control_definitions() if c["function"]["name"] == name), None)
        if spec is None:
            return store._error("TOOL_NOT_AVAILABLE", "Tool is not enabled in this mode")
        _validate_schema(args, spec["parameters"])
        if name == "begin_subgoal" and self.request_progress:
            requirements = args.pop("requirements", [])
            problem = self.request_progress.validate_requirements(requirements, args.get("deliveries", []))
            if problem:
                return store._error("INVALID_REQUEST_REQUIREMENT", problem)
            result = store.begin_subgoal(**args)
            goal = store.find_subgoal(result.get("subgoal_id"))
            if result.get("status") not in {"rejected", "blocked"} and goal:
                self.request_progress.bind(requirements, args.get("deliveries", []), goal)
            return result
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
            if self.request_progress:
                problem = self.request_progress.review(status, args.get("coverage"), args.get("coverage_complete"))
                if problem:
                    return {**store._error("REQUEST_COVERAGE_NOT_DELIVERED", problem),
                            "recovery": {
                                "actual_visible_result_ids": sorted(self.visible_evidence_ids),
                                "stored_unread_result_ids": [e.task_id for e in store.entries
                                    if store._binding_valid(e) and e.task_id not in self.visible_evidence_ids],
                                "delivery_only": self.final_only,
                                "allowed_path": ("For partial/clarification, cite only visible results; use an empty result_ids list and unresolved for unmet items. A stored locator does not prove a numerical answer."
                                    if self.final_only else "Read required evidence or report a genuinely unresolved item with an empty result_ids list.")}}
                if status == "completed" and store.active and store.completion_check(store.active)["valid"]:
                    # Programmatic closure verifies the actual contract; the
                    # model still owns the final scientific answer and review.
                    store.close_subgoal("completed")
            pending = [g for g in store.subgoals if g.status != "completed" and
                       (g.turn == store.turn or g.subgoal_id in self.restored or g.subgoal_id in self.touched_goals)]
            if status == "completed" and (store.active or unresolved or pending):
                return {**store._error("UNFINISHED_SUBGOAL", "Resolve or explicitly report pending work"),
                        "pending": [store.summary(g) for g in pending]}
            if status != "completed" and (not unresolved or not isinstance(unresolved, list)):
                return store._error("UNRESOLVED_REQUIRED", "Name the missing information or limitation")
            if (status == "completed" or (status == "partial" and not self.request_closure)) and not store.entries:
                return store._error("NO_EVIDENCE", "No actual analysis has been delivered")
            self.stop_reason, self.final_answer = status, args["answer"]
            if self.request_progress:
                self.request_progress.frames[-1]["coverage_review"]["accepted"] = True
            return {"status": status, "unresolved": unresolved, "answer": self.final_answer}
        return getattr(store, name)(**args)

    def execute(self, request, *, batch_size=1):
        self.store.last_owner = None
        before = len(self.store.entries)
        owner_before = (self.store.active.subgoal_id if self.store.active else
                        request.arguments.get("subgoal_id"))
        start = time.perf_counter()
        try:
            if batch_size != 1 and not self.lifecycle:
                result = self.store._error("SEQUENTIAL_ACTION_REQUIRED", "Observe each action before selecting the next")
            else:
                result = self._dispatch(request)
        except (ValueError, TypeError, KeyError):
            result = self.store._error("INVALID_CONTROL_ARGUMENT", "Check the advertised schema and scientific scope")
        except Exception:
            result = self.store._error("INTERNAL_CONTROL_ERROR", "Control failed safely; no traceback is sent to the model")
        successful = result.get("status") not in {"rejected", "blocked"}
        owner = self.store.last_owner or owner_before
        self.action_owners[request.request_id] = owner
        if owner:
            self.touched_goals.add(owner)
        if self.lifecycle:
            goal = self.store.find_subgoal(owner)
            if goal:
                result["progress"] = {"subgoal_id": goal.subgoal_id, "status": goal.status,
                                      "deliveries": self.store.completion_check(goal).get("deliveries", []),
                                      "unresolved": clone(goal.unresolved)}
        # Rejected multi-call batches are one failed decision. Distinct corrected
        # input errors are not evidence of repeating the same non-progress loop.
        signature = (request.name, result.get("code", "TOOL_BLOCKED"))
        self.errors = (0 if successful else self.errors + 1 if signature == self.last_error else 1)
        self.last_error = None if successful else signature
        # Identical close arguments on different subgoals are real progress.
        # Do not include generated result IDs: repeated computation/read on the
        # same target must still be bounded even when it emits a fresh ID.
        key = encoded({"tool": request.name, "args": dict(request.arguments),
                       "subgoal": owner_before, "record": self.store.active_record})
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
        # Each goal receives a protocol-valid projection of its OWN actions.
        # The original batch remains intact in the session archive above.
        owners = {self.action_owners.get(r["tool_call_id"]) for r in responses}
        for ident in owners - {None}:
            owner = self.store.find_subgoal(ident)
            if owner:
                chosen = [r for r in responses if self.action_owners.get(r["tool_call_id"]) == ident]
                ids = {r["tool_call_id"] for r in chosen}
                owner.exchanges.append([{"role": "assistant", "content": assistant.get("content"),
                                         "tool_calls": [clone(c) for c in assistant["tool_calls"] if c["id"] in ids]}] + clone(chosen))
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

    def progress_notice(self):
        if not self.lifecycle:
            return ""
        pending = [g for g in self.store.subgoals if g.status != "completed"]
        if self.request_closure:
            return f" 已保留{len(self.store.entries)}项真实结果、{len(pending)}个未完成的已登记目的；这不包含尚未声明的原需求，也不证明本轮请求完整交付。当前仅为保存点，详见状态与错误。"
        return f" 已保留{len(self.store.entries)}项真实结果，{len(pending)}个目的未完成；可在同一会话补充或继续。未执行动作不算成功，详见保存的状态与错误。"

    def snapshot(self):
        return {"session_id": self.store.session_id, "context_mode": self.context_mode,
                "requests": clone(self.requests), "subgoals": [self.store.summary(g) for g in self.store.subgoals],
                "events": clone(self.store.events), "decisions": clone(self.decisions),
                "exchanges": clone(self.exchanges), "outcomes": clone(self.outcomes),
                "request_progress": clone(self.request_progress.frames) if self.request_progress else None,
                "record_traces": {k: c.trace.to_dict() for k, c in self.store.contexts.items()}}


class WorkingMemoryEEGAgent(EEGAgent):
    """Convenience constructor; run/continue use the original EEGAgent.run."""

    def __init__(self, llm_client, records, *, session_id="wm", max_rounds=24,
                 max_tool_calls=24, config=None, memory_version="single", **memory_options):
        if memory_version not in {"single", "multi_result", "lifecycle"}:
            raise ValueError("memory_version must be single, multi_result or lifecycle")
        if memory_version == "lifecycle":
            from .working_memory_lifecycle import ReliableWorkingMemoryStore
            store = ReliableWorkingMemoryStore(session_id, records, config=config)
        elif memory_version == "multi_result":
            from .working_memory_deliveries import MultiResultWorkingMemoryStore
            store = MultiResultWorkingMemoryStore(session_id, records, config=config)
        else:
            store = WorkingMemoryStore(session_id, records, config=config)
        controller = WorkingMemoryController(store, **memory_options)
        super().__init__(llm_client, next(iter(store.contexts.values())), max_rounds,
                         max_tool_calls, working_memory=controller)

    def continue_run(self, user_request):
        return self.run(user_request)

    def cancel(self):
        self.working_memory.cancelled = True
