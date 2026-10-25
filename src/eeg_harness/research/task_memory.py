"""Opt-in multi-turn EEG task memory over the existing v3 execution core.

All policies see the same immutable task entries and use the same read_task API.
Only working-context selection differs; no EEG numerical algorithm is replaced.
"""

from dataclasses import dataclass, replace
import json
import re
from pathlib import Path
import time

import numpy as np

from ..context import ExecutionContext
from ..demo import build_synthetic_event_record
from ..events import EEGEvent, EventSet
from ..executor import Executor
from ..pipeline import load_config
from ..profiles import EDF_NATIVE
from ..tools import build_default_registry
from .integrated_method.v3 import (EVENT_CAPABILITIES, EVENT_SCOPE_KEYS,
                                   GoalInstance, InstanceTaskRequest,
                                   capability_catalog, run_instances)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG = load_config(PROJECT_ROOT / "config" / "baseline.json")
PROTOCOL = PROJECT_ROOT / "config" / "point1_task_memory_protocol_v1.json"
ALLOWED_GOALS = frozenset({"record_info", "record_quality", "amplitude", "psd",
                           "epoch_summary", "epoch_quality", "event_bandpower"})


def synthetic_records():
    """Two distinguishable synthetic records; no private EEG is loaded."""
    base = build_synthetic_event_record()
    output = {}
    for alias, scale, late_gain, events in (
        ("A", 1.0, 1.4, (("stimulus", 1), ("control", 2), ("stimulus", 3),
                              ("control", 4), ("stimulus", 5))),
        ("B", 0.63, 1.8, (("stimulus", 1.5), ("control", 2.5),
                               ("stimulus", 4.5), ("control", 5.5))),
    ):
        data = base.data.copy() * scale
        data[:, int(3 * base.sfreq):] *= late_gain
        table = EventSet(tuple(EEGEvent(label, float(onset), source_index=index)
                               for index, (label, onset) in enumerate(events)),
                         f"synthetic://task-memory-{alias}-events")
        output[alias] = replace(base, data=data, events=table,
                                source=f"synthetic://task-memory-{alias}",
                                metadata={**base.metadata, "record_alias": alias,
                                          "is_synthetic": True})
    return output


def load_protocol():
    return json.loads(PROTOCOL.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class TaskEntry:
    task_id: str
    sequence: int
    record: str
    capability: str
    parameters: dict
    user_text: str
    revision_of: str | None
    status: str
    result: dict
    evidence: dict
    tool_trace: tuple[dict, ...]

    def card(self, *, compact=False):
        item = {"task_id": self.task_id, "record": self.record,
                "capability": self.capability, "parameters": self.parameters,
                "revision_of": self.revision_of, "status": self.status,
                "sequence": self.sequence}
        if not compact:
            item["request"] = self.user_text
            item["result_preview"] = self.result
        return item


class MultiTurnEEGSession:
    """Common task history, record isolation, execution and read interface."""

    def __init__(self, session_id, records=None):
        self.session_id = session_id
        self.records = records or synthetic_records()
        if not all(record.metadata.get("is_synthetic") is True
                   for record in self.records.values()):
            raise ValueError("Research multi-turn LLM interface is synthetic-only")
        self.active_record = next(iter(self.records))
        self.entries = []
        self.messages = []

    def switch(self, alias, text):
        self.messages.append({"role": "user", "content": text})
        if alias not in self.records:
            return {"status": "clarification_required", "code": "UNKNOWN_RECORD"}
        self.active_record = alias
        return {"status": "switched", "record": alias}

    def analyze(self, alias, capability, parameters, text, *, revision_of=None):
        self.messages.append({"role": "user", "content": text})
        if alias not in self.records or capability not in ALLOWED_GOALS:
            return {"status": "clarification_required", "code": "UNKNOWN_RECORD_OR_GOAL"}
        if revision_of is not None:
            parent = next((item for item in self.entries if item.task_id == revision_of), None)
            if parent is None or parent.record != alias or parent.capability != capability:
                return {"status": "clarification_required", "code": "INVALID_REVISION_PARENT"}
        task_id = f"{self.session_id}-t{len(self.entries) + 1}"
        record = self.records[alias]
        context = ExecutionContext(record, EDF_NATIVE,
                                   Executor(build_default_registry(), CONFIG), task_id)
        result = run_instances(context, InstanceTaskRequest((
            GoalInstance("g1", capability, dict(parameters)),
        )))
        if result["status"] != "completed":
            return {"status": result["status"], "code": result.get("code"),
                    "task_id": None, "tool_trace": result.get("tool_results", [])}
        bundle = result["evidence_bundle"]["goals"][0]
        entry = TaskEntry(task_id, len(self.entries) + 1, alias, capability,
                          dict(parameters), text, revision_of, result["status"],
                          bundle["result"], bundle, tuple(result["tool_results"]))
        self.entries.append(entry)
        self.active_record = alias
        return {"status": "completed", "task_id": task_id,
                "record": alias, "capability": capability,
                "result": bundle["result"], "source": bundle["source"],
                "unit_or_kind": bundle["unit_or_kind"],
                "tool_count": len(result["tool_results"])}

    def read_task(self, task_id, text, *, record_message=True):
        if record_message:
            self.messages.append({"role": "user", "content": text})
        entry = next((item for item in self.entries if item.task_id == task_id), None)
        if entry is None:
            return {"status": "clarification_required", "code": "TASK_NOT_FOUND"}
        return {"status": "read", "task_id": entry.task_id, "record": entry.record,
                "capability": entry.capability, "parameters": entry.parameters,
                "revision_of": entry.revision_of, "result": entry.result,
                "unit_or_kind": entry.evidence["unit_or_kind"],
                "source": entry.evidence["source"],
                "evidence_token": entry.evidence["evidence_token"]}


def _query_features(text, session):
    """Same visible query decomposition for G/E, never an offline target ID."""
    lower = text.casefold()
    records = tuple(alias for alias in session.records
                    if re.search(rf"(?<![a-z]){re.escape(alias.casefold())}(?![a-z])", lower))
    channels = tuple(name for record in session.records.values()
                     for name in record.channel_names if name.casefold() in lower)
    return {"text": lower, "records": records, "channels": tuple(dict.fromkeys(channels)),
            "event_labels": tuple(label for label in ("stimulus", "control") if label in lower),
            "old": any(word in lower for word in ("修改前", "原来", "第一次", "最初")),
            "new": any(word in lower for word in ("修改后", "现在", "最新")),
            "event": any(word in lower for word in ("事件", "试次", "epoch")),
            "psd": any(word in lower for word in ("功率", "频带", "alpha", "psd")),
            "amplitude": any(word in lower for word in ("幅值", "rms", "振幅"))}


def select_context(session, text, policy, *, top_k=3):
    """Return working-context cards; raw entries remain available to every arm."""
    entries = session.entries
    if policy == "F":
        cards = [item.card() for item in entries]
    elif policy == "S":
        cards = ([{"rolling_summary": [item.card(compact=True)
                                       for item in entries[:-top_k]]}]
                 if len(entries) > top_k else [])
        cards += [item.card() for item in entries[-top_k:]]
    elif policy in {"G", "E", "E-no-scope"}:
        query = _query_features(text, session)
        scored = []
        for item in entries:
            card = item.card()
            serialized = json.dumps(card, ensure_ascii=False).casefold()
            generic_terms = ("alpha", "rms", "功率", "幅值", "试次", "事件", "修改", "窗口")
            score = sum(1.0 for term in generic_terms
                        if term in query["text"] and term in serialized)
            score += 3.0 * (item.record in query["records"])
            score += 2.0 * bool(set(query["channels"]) & set(item.parameters.get("channels", ())))
            if policy == "E":
                if query["event"]:
                    score += 2.0 * (item.capability in
                                    {"epoch_summary", "epoch_quality", "event_bandpower"})
                if query["event_labels"]:
                    score += 3.0 * bool(set(query["event_labels"]) &
                                        set(item.parameters.get("labels", ())))
                if query["psd"]:
                    score += 1.5 * (item.capability in {"psd", "event_bandpower"})
                if query["amplitude"]:
                    score += 1.5 * (item.capability == "amplitude")
                if query["old"] and any(other.revision_of == item.task_id for other in entries):
                    score += 3.0
                if query["new"] and item.revision_of is not None:
                    score += 3.0
            scored.append((score, item.sequence, card))
        scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
        cards = [item[2] for item in scored[:top_k]]
    else:
        raise ValueError("Unknown memory policy")
    payload = {"active_record": session.active_record, "cards": cards,
               "record_aliases": sorted(session.records)}
    if policy == "F":
        payload["full_messages"] = list(session.messages)
        payload["full_tool_results"] = [list(item.tool_trace) for item in entries]
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    return {"payload": payload, "shown_task_ids": [card["task_id"] for card in cards
                                                   if "task_id" in card],
            "estimated_tokens": (len(encoded) + 3) // 4,
            "characters": len(encoded)}


def replay_policies(script, policies=("F", "S", "G", "E", "E-no-scope")):
    """Execute each tool once; every arm selects from that exact same history."""
    session = MultiTurnEEGSession(script["id"])
    observations = {policy: [] for policy in policies}
    for turn in script["turns"]:
        selections = {policy: select_context(session, turn["text"], policy)
                      for policy in policies}
        if turn["op"] in {"history", "clarify"}:
            target = f"{script['id']}-t{turn['target']}" if "target" in turn else None
            for policy, selection in selections.items():
                candidate_ids = selection["shown_task_ids"]
                if (policy == "S" and selection["payload"]["cards"]
                        and "rolling_summary" in selection["payload"]["cards"][0]):
                    candidate_ids = ([card["task_id"] for card in
                                      selection["payload"]["cards"][0]["rolling_summary"]]
                                     + candidate_ids)
                observations[policy].append({
                    "turn": turn["text"], "op": turn["op"], "target": target,
                    "top1": candidate_ids[0] if candidate_ids else None,
                    "hit": target in candidate_ids if target else None,
                    "shown": candidate_ids,
                    "estimated_tokens": selection["estimated_tokens"]})
            session.messages.append({"role": "user", "content": turn["text"]})
            continue
        if turn["op"] == "switch":
            result = session.switch(turn["record"], turn["text"])
        else:
            parent = f"{script['id']}-t{turn['parent']}" if turn["op"] == "revise" else None
            result = session.analyze(turn["record"], turn["capability"], turn["parameters"],
                                     turn["text"], revision_of=parent)
        for policy, selection in selections.items():
            observations[policy].append({
                "turn": turn["text"], "op": turn["op"], "status": result["status"],
                "task_id": result.get("task_id"),
                "tool_count": result.get("tool_count", 0),
                "estimated_tokens": selection["estimated_tokens"]})
    entries = [item.card() for item in session.entries]
    return [{"session_id": script["id"], "policy": policy,
             "observations": observations[policy], "entries": entries}
            for policy in policies]


def replay_session(script, policy):
    return replay_policies(script, (policy,))[0]


MEMORY_ACTION_TOOL = [{"type": "function", "function": {
    "name": "submit_memory_action",
    "description": "Choose one grounded multi-turn EEG action. History IDs must come from visible memory.",
    "parameters": {"type": "object", "properties": {
        "operation": {"type": "string", "enum": ["analyze", "revise", "switch", "history", "clarify"]},
        "record": {"type": "string"}, "capability": {"type": "string"},
        "parameters": {"type": "object"}, "parent_task_id": {"type": "string"},
        "task_id": {"type": "string"}, "question": {"type": "string"},
    }, "required": ["operation"]},
}}]


def live_turn(session, policy, text, client, *, deliver_answer=False,
              selector=select_context):
    """One real model decision, then shared real tools/read API. No gold input."""
    selection = selector(session, text, policy)
    metadata = {alias: {"sfreq": record.sfreq,
                        "channels": list(record.channel_names),
                        "duration_seconds": record.duration_seconds,
                        "event_labels": record.events.summary()["labels"] if record.events else {}}
                for alias, record in session.records.items()}
    context = ExecutionContext(session.records[session.active_record], EDF_NATIVE,
                               Executor(build_default_registry(), CONFIG),
                               f"{session.session_id}-catalog")
    catalog = []
    for item in capability_catalog(context):
        if item["name"] not in ALLOWED_GOALS:
            continue
        allowed = (EVENT_SCOPE_KEYS if item["name"] in EVENT_CAPABILITIES
                   else tuple(item["parameters"].get("properties", {})))
        catalog.append({"name": item["name"], "description": item["description"],
                        "scientific_scope": item["scientific_scope"],
                        "unit_or_kind": item["unit_or_kind"],
                        "required": item["required_user_parameters"],
                        "allowed": allowed})
    system = (
        "你是研究用途 EEG 多轮分析助手。只调用 submit_memory_action 一次。"
        "所有历史 task_id 和参数必须来自当前提供的真实任务卡/只读结果；不可猜 ID、记录、窗口、事件或模型结果。"
        "历史查询选 history 并填 task_id；参数修改选 revise 并填 parent_task_id，生成新任务且保留旧结果。"
        "切换记录选 switch；新增计算选 analyze。若多个历史任务同样符合请求，选 clarify 说明歧义。"
        "新分析的能力、科学含义和合法参数均由 CAPABILITIES 声明；"
        "按描述匹配用户需求，仅用 allowed 中字段，不添加自造参数。"
        "所需参数确实缺失才澄清；不要把能力名称与自然语言的字面差异当成缺参。"
        "不要把连续 PSD 与事件窗功率混淆，不诊断。"
        "CAPABILITIES=" + json.dumps(catalog, ensure_ascii=False, allow_nan=False) + "。"
        "RECORDS=" + json.dumps(metadata, ensure_ascii=False, allow_nan=False)
    )
    message = client.complete(
        [{"role": "system", "content": system},
         {"role": "user", "content": json.dumps({"memory": selection["payload"],
                                                   "request": text}, ensure_ascii=False)}],
        MEMORY_ACTION_TOOL,
        tool_choice={"type": "function", "function": {"name": "submit_memory_action"}},
    )
    try:
        calls = message.get("tool_calls") or []
        if len(calls) != 1 or calls[0].get("function", {}).get("name") != "submit_memory_action":
            raise ValueError("Expected one structured memory action")
        action = json.loads(calls[0]["function"]["arguments"])
        operation = action["operation"]
        if operation == "switch":
            outcome = session.switch(action.get("record"), text)
        elif operation in {"analyze", "revise"}:
            outcome = session.analyze(
                action.get("record", session.active_record), action.get("capability"),
                action.get("parameters", {}), text,
                revision_of=action.get("parent_task_id") if operation == "revise" else None)
        elif operation == "history":
            outcome = session.read_task(action.get("task_id"), text)
        elif operation == "clarify":
            session.messages.append({"role": "user", "content": text})
            outcome = {"status": "clarification_required", "question": action.get("question", "请明确历史任务。")}
        else:
            raise ValueError("Unknown action")
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        action = {"operation": "invalid"}
        outcome = {"status": "intent_error", "code": "INVALID_MODEL_ACTION"}
    final_answer = None
    if deliver_answer:
        reply = client.complete([
            {"role": "system", "content": (
                "你是研究用途 EEG 分析助手。仅依据下列真实执行/历史读取结果回答当前问题；"
                "数字、单位、记录和分析条件必须忠实于结果。若需澄清，直接提出澄清问题；"
                "若执行失败，说明失败，不能编造 EEG 数值或临床结论。")},
            {"role": "user", "content": json.dumps({"request": text, "action": action,
                                                   "outcome": outcome},
                                                  ensure_ascii=False, allow_nan=False)},
        ], [])
        final_answer = reply.get("content") if isinstance(reply, dict) else None
        if not isinstance(final_answer, str) or not final_answer.strip():
            final_answer = None
    return {"request": text, "memory_policy": policy,
            "shown_task_ids": selection["shown_task_ids"],
            "working_context_estimated_tokens": selection["estimated_tokens"],
            "action": action, "outcome": outcome,
            "final_answer": final_answer}
