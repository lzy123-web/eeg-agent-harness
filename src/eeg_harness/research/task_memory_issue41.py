"""Issue #41: compact exact-result cards and bounded field evidence retrieval.

This is an opt-in representation/read adapter over the existing task episode,
Registry and Executor. It does not calculate EEG or replace the agent runtime.
"""

import argparse
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import time

import numpy as np

from ..llm import OpenAICompatibleClient
from .integrated_method.v2_validation import JournaledBudgetClient, PRIVATE_ROOT
from .task_memory import PROJECT_ROOT, live_turn
from .task_memory_issue39_budget import (Issue39BudgetClient, StageBudgetExhausted,
                                         ledger_totals, _rows)
from .task_memory_v2 import independent_oracle, protocol_records
from .task_memory_v3 import (EpisodeMemorySession, scientific_read_mismatch,
                             select_context_v3)


SPEC_PATH = PROJECT_ROOT / "config" / "point1_task_memory_issue41.json"
OLD_PATH = PROJECT_ROOT / "config" / "point1_task_memory_protocol_v2.json"
PRIVATE = PRIVATE_ROOT / "point1_task_memory" / "issue41"
LEDGER = PRIVATE / "budget.jsonl"
EVIDENCE_ACTION = [{"type": "function", "function": {
    "name": "submit_evidence_action",
    "description": "Answer from visible exact evidence, read full/selected evidence, or clarify.",
    "parameters": {"type": "object", "properties": {
        "operation": {"type": "string", "enum": ["answer", "read_full", "read_fields", "clarify"]},
        "task_id": {"type": "string"}, "answer": {"type": "string"},
        "field_paths": {"type": "array", "items": {"type": "array", "items": {
            "anyOf": [{"type": "string"}, {"type": "integer"}]}}},
        "question": {"type": "string"},
    }, "required": ["operation"]},
}}]


def load_spec():
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def _shape(value, depth=0):
    """Real result keys only; neither future request nor numerical gold enters."""
    if depth >= 8:
        return "…"
    if isinstance(value, dict):
        if all(not isinstance(child, (dict, list)) for child in value.values()):
            return list(value)
        return {str(key): _shape(child, depth + 1) for key, child in value.items()}
    if isinstance(value, list):
        return {"list_length": len(value)}
    return None


def result_view(entry, *, inline_max=256):
    """Size-bounded deterministic result representation, no task-name switch."""
    raw = _encoded(entry.result)
    if len(raw) <= inline_max:
        return {"exact_result": entry.result, "result_view": "exact"}
    # Top-level result_fields and scientific provenance already live in the
    # task card. Index only deeper result branches; never repeat source or
    # parameters already present in that card.
    nested = {key: _shape(value) for key, value in entry.result.items()
              if isinstance(value, dict) and key not in {"source", "parameters"}}
    return {"field_index": nested, "result_view": "indexed"}


def protocol_records41(script):
    records = protocol_records(script)
    for alias, factor in script.get("signal_scales", {}).items():
        if alias not in records or not isinstance(factor, (int, float)) or factor <= 0:
            raise ValueError("Invalid synthetic signal scale")
        base = records[alias]
        records[alias] = replace(
            base, data=np.asarray(base.data * factor, dtype=base.data.dtype),
            source=f"synthetic://issue41-{script['id']}-{alias}-scale-{factor}",
            metadata={**base.metadata, "issue41_signal_scale": factor})
    return records


def build_session(script):
    """Write one real-tool history; step keys are scorer-only afterwards."""
    session = GranularEpisodeSession(script["id"], protocol_records41(script))
    keys = {}
    for step in script["steps"]:
        parent = keys[step["revision_of"]].task_id if "revision_of" in step else None
        result = session.analyze(step["record"], step["capability"],
                                 step["parameters"], step["text"],
                                 revision_of=parent)
        if result["status"] != "completed":
            raise RuntimeError(f"Protocol tool failure at {step['key']}: {result}")
        keys[step["key"]] = session.entries[-1]
    return session, keys


class GranularEpisodeSession(EpisodeMemorySession):
    """Same task store and scientific guard; all arms may read scalar fields."""

    def __init__(self, session_id, records=None):
        super().__init__(session_id, records)
        self.field_focus = None
        self.field_reads = 0
        self.full_reads = 0
        self.read_payload_bytes = 0

    def analyze(self, alias, capability, parameters, text, *, revision_of=None):
        self.field_focus = None
        return super().analyze(alias, capability, parameters, text,
                               revision_of=revision_of)

    def switch(self, alias, text):
        self.field_focus = None
        return super().switch(alias, text)

    def read_task(self, task_id, text, *, record_message=True):
        result = super().read_task(task_id, text, record_message=record_message)
        if record_message and result["status"] == "read":
            self.full_reads += 1
            self.read_payload_bytes += len(_encoded(result))
            self.field_focus = None
        return result

    def read_task_fields(self, task_id, paths, text):
        entry = next((item for item in self.entries if item.task_id == task_id), None)
        if entry is None:
            return {"status": "clarification_required", "code": "TASK_NOT_FOUND"}
        mismatch = scientific_read_mismatch(self, entry, text)
        if mismatch:
            return {"status": "clarification_required", "code": "SCIENTIFIC_SCOPE_MISMATCH",
                    "reason": mismatch}
        if not isinstance(paths, list) or not 1 <= len(paths) <= 4:
            return {"status": "invalid_field", "code": "FIELD_COUNT_INVALID"}
        values = []
        for path in paths:
            if not isinstance(path, list) or not 1 <= len(path) <= 8:
                return {"status": "invalid_field", "code": "FIELD_PATH_INVALID"}
            # A generic summary may display a nested path as "parent/child".
            # Preserve a literal key if it exists; otherwise accept that
            # display form only when every split component resolves exactly.
            if (len(path) == 1 and isinstance(path[0], str)
                    and "/" in path[0] and path[0] not in entry.result):
                path = path[0].split("/")
                if not all(path) or len(path) > 8:
                    return {"status": "invalid_field", "code": "FIELD_PATH_INVALID"}
            value = entry.result
            for key in path:
                if isinstance(value, dict) and isinstance(key, str) and key in value:
                    value = value[key]
                elif (isinstance(value, list) and type(key) is int
                      and 0 <= key < len(value)):
                    value = value[key]
                else:
                    return {"status": "invalid_field", "code": "FIELD_NOT_FOUND"}
            small_list = (isinstance(value, list) and len(value) <= 16
                          and all(item is None or type(item) in {str, int, float, bool}
                                  for item in value)
                          and len(_encoded(value)) <= 256)
            if not (value is None or type(value) in {str, int, float, bool}
                    or small_list):
                return {"status": "invalid_field", "code": "FIELD_NOT_SCALAR"}
            values.append({"path": path, "value": value})
        # Only after path validation invoke the shared scientific read guard
        # and restoration accounting; the full artifact is never returned.
        checked = super().read_task(task_id, text)
        if checked["status"] != "read":
            return checked
        result = {"status": "read_fields", "task_id": entry.task_id,
                  "record": entry.record, "capability": entry.capability,
                  "parameters": entry.parameters, "revision_of": entry.revision_of,
                  "source": entry.evidence["source"],
                  "source_stage": entry.evidence["source_stage"],
                  "analysis_configuration": entry.evidence["analysis_configuration"],
                  "unit_or_kind": entry.evidence["unit_or_kind"],
                  "evidence_token": entry.evidence["evidence_token"],
                  "fields": values}
        self.field_reads += 1
        self.read_payload_bytes += len(_encoded(result))
        self.focused_task_id = None
        self.field_focus = result
        return result


def select_context41(session, text, policy, *, inline_max=256):
    if policy not in {"F", "S", "H", "HC"}:
        raise ValueError("Unknown memory policy")
    selected = select_context_v3(session, text, "H" if policy == "HC" else policy)
    payload = selected["payload"]
    if policy == "HC":
        by_id = {entry.task_id: entry for entry in session.entries}
        for name in ("completed_index", "working_tasks"):
            for card in payload[name]:
                entry = by_id[card["task_id"]]
                view = result_view(entry, inline_max=inline_max)
                card.update(view)
                if view["result_view"] == "exact":
                    card.pop("result_fields", None)
    if session.field_focus is not None:
        payload["focused_field_evidence"] = session.field_focus
    payload["field_read_interface"] = "read_task_fields(task_id, field_paths<=4)"
    encoded = _encoded(payload)
    return {**selected, "payload": payload, "characters": len(encoded),
            "estimated_tokens": (len(encoded) + 3) // 4}


def _visible_exact(selection, task_id):
    payload = selection["payload"]
    cards = list(payload.get("cards", ())) + list(payload.get("working_tasks", ()))
    cards += list(payload.get("completed_index", ()))
    for card in cards:
        if card.get("task_id") == task_id and (
                "result_preview" in card or "exact_result" in card):
            return True
        for child in card.get("rolling_summary", ()):
            if child.get("task_id") == task_id and (
                    "result_preview" in child or "exact_result" in child):
                return True
    focus = payload.get("focused_evidence")
    return bool(focus and focus.get("task_id") == task_id and
                "result_preview" in focus)


def same_history_turn(session, policy, query, client, *, inline_max=256):
    """Shared one-or-two completion interface with optional scalar projection."""
    selected = select_context41(session, query, policy, inline_max=inline_max)
    system = (
        "你是研究用途 EEG 历史分析助手。仅用当前可见的真实任务证据，不诊断、不猜数值。"
        "所有方案拥有同样的 read_full 和 read_fields 权限。若精确数值已在当前上下文，"
        "可直接 answer 并注明其真实 task_id；若只有索引，用 read_fields 按真实字段路径"
        "读取最多四个小字段，字段路径必须来自可见字段结构；不确定路径或需要完整结果时用"
        " read_full。确有条件、记录或版本歧义才 clarify。空归档索引不代表工作任务不存在。"
        "不得把功率 V² 写成 V²/Hz；分析范围、版本、单位需忠实于证据。")
    first = client.complete([
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps({"request": query,
                                               "memory": selected["payload"]},
                                              ensure_ascii=False, allow_nan=False)},
    ], EVIDENCE_ACTION, tool_choice={"type": "function", "function": {
        "name": "submit_evidence_action"}})
    calls = first.get("tool_calls") or []
    if not 1 <= len(calls) <= 4 or any(
            call.get("function", {}).get("name") != "submit_evidence_action"
            for call in calls):
        return {"status": "invalid_action", "action": None, "answer": None,
                "selection": selected, "read": None}
    try:
        actions = [json.loads(call["function"]["arguments"]) for call in calls]
    except (TypeError, ValueError, KeyError):
        return {"status": "invalid_action", "action": None, "answer": None,
                "selection": selected, "read": None}
    if len(actions) > 1 and any(action.get("operation") not in
                                {"read_full", "read_fields"} for action in actions):
        return {"status": "invalid_action", "action": None, "answer": None,
                "selection": selected, "read": None}
    action = actions[0]
    operation = action.get("operation")
    if operation == "answer":
        answer = action.get("answer")
        return {"status": "answered" if isinstance(answer, str) and answer.strip()
                else "invalid_answer", "action": action, "answer": answer,
                "selection": selected, "read": None}
    if operation == "clarify":
        return {"status": "clarification_required", "action": action,
                "answer": action.get("question"), "selection": selected, "read": None}
    reads = []
    for item in actions:
        if item.get("operation") == "read_full":
            observed = session.read_task(item.get("task_id"), query)
        elif item.get("operation") == "read_fields":
            observed = session.read_task_fields(item.get("task_id"),
                                                item.get("field_paths"), query)
        else:
            return {"status": "invalid_action", "action": item, "answer": None,
                    "selection": selected, "read": None}
        reads.append(observed)
    successful = [item for item in reads if item["status"] in {"read", "read_fields"}]
    if not successful:
        return {"status": reads[0]["status"], "action": actions[0],
                "actions": actions, "answer": None,
                "selection": selected, "read": reads[0], "reads": reads}
    second = client.complete([
        {"role": "system", "content": (
            "只据下列真实 EEG 任务证据回答当前问题，准确注明记录、科学条件、时间窗、"
            "版本、数值和单位。若证据不足须明确说明，不能编造或诊断。")},
        {"role": "user", "content": json.dumps({"request": query,
                                               "evidence": reads[0] if len(reads) == 1
                                               else reads},
                                              ensure_ascii=False, allow_nan=False)},
    ], [])
    answer = second.get("content") if isinstance(second, dict) else None
    return {"status": "answered" if isinstance(answer, str) and answer.strip()
            else "invalid_answer", "action": action, "actions": actions,
            "answer": answer, "selection": selected, "read": reads[0],
            "reads": reads}


def _number_in_answer(answer, expected):
    superscript = str.maketrans("⁻⁺⁰¹²³⁴⁵⁶⁷⁸⁹", "-+0123456789")
    answer = re.sub(
        r"([-+]?(?:\d+\.?\d*|\.\d+))\s*[×x]\s*10([⁻⁺⁰¹²³⁴⁵⁶⁷⁸⁹]+)",
        lambda match: f"{match.group(1)}e{match.group(2).translate(superscript)}",
        answer)
    numbers = re.findall(r"(?<![A-Za-z0-9])[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", answer)
    return any(math.isclose(float(token), float(expected), rel_tol=0.05,
                            abs_tol=1e-30) for token in numbers)


def score_turn(session, script, query, keys, observed):
    """Independent post-hoc screen; full scientific language is manually audited."""
    if query.get("expect_clarify"):
        valid = (observed.get("status") == "clarification_required"
                 and isinstance(observed.get("answer"), str)
                 and bool(observed["answer"].strip()))
        return {"valid_screen": valid, "category": "correct_clarification" if valid
                else "unsafe_assumption", "requires_answer_review": True}
    action = observed.get("action") or {}
    chosen = action.get("task_id")
    target = keys[query["target"]]
    step = next(item for item in script["steps"] if item["key"] == query["target"])
    actions = observed.get("actions") or [action]
    same_task = any(item.get("task_id") == target.task_id for item in actions)
    fields = query.get("fields") or [query["field"]]
    oracles = [independent_oracle(session.records[step["record"]], step, field)
               for field in fields]
    answer = observed.get("answer") or ""
    numbers_match = all(_number_in_answer(answer, value) for value in oracles)
    read = observed.get("read")
    direct_visible = (action.get("operation") != "answer" or
                      _visible_exact(observed["selection"], chosen))
    if any(item.get("operation") in {"read_fields", "read_full"} for item in actions):
        targeted_reads = [item for item in (observed.get("reads") or [read])
                          if item and item.get("task_id") == target.task_id]
        paths = [field["path"] for item in targeted_reads
                 for field in item.get("fields", ())]
        read_covers = bool(targeted_reads) and (
            any(item.get("status") == "read" for item in targeted_reads)
            or all(field in paths for field in fields))
    else:
        read_covers = True
    actual_valid = True
    for field, expected in zip(fields, oracles):
        value = target.result
        try:
            for part in field:
                value = value[part]
            actual_valid &= math.isclose(float(value), float(expected),
                                         rel_tol=5e-3, abs_tol=1e-30)
        except (KeyError, IndexError, TypeError, ValueError):
            actual_valid = False
    unit = target.evidence["unit_or_kind"]
    positive_unit_text = re.sub(r"(?:非|不是|并非|不等于|not)\s*V²(?:/Hz)?",
                                "", answer, flags=re.IGNORECASE)
    unit_screen = ("V²" in positive_unit_text and "V²/Hz" not in positive_unit_text
                   if unit == "V²" else
                   "V" in positive_unit_text and "V²" not in positive_unit_text if unit == "V"
                   else True)
    valid = bool(same_task and actual_valid and numbers_match and direct_visible
                 and read_covers and unit_screen and observed.get("status") == "answered")
    return {"valid_screen": valid, "target_match": same_task,
            "source_scope_version_valid": same_task and actual_valid,
            "oracle_values": oracles, "numeric_screen_match": numbers_match,
            "unit_screen_match": unit_screen,
            "direct_evidence_visible": direct_visible, "read_covers_fields": read_covers,
            "requires_answer_review": True,
            "category": ("correct_screen" if valid else
                         "wrong_task_or_scope" if not same_task else
                         "unsupported_direct_answer" if not direct_visible else
                         "incomplete_projection" if not read_covers else
                         "answer_or_unit_error")}


def _sources(spec):
    old = json.loads(OLD_PATH.read_text(encoding="utf-8"))
    return {"v2": {script["id"]: script for script in old["sessions"]},
            "issue41": {script["id"]: script for script in spec["confirmation_scripts"]}}


def _admit_pair(spec, phase, unit_id):
    totals = ledger_totals(LEDGER)
    if any(row.get("event") == "reserved" and
           row.get("context", {}).get("unit_id") == unit_id for row in _rows(LEDGER)):
        raise StageBudgetExhausted("Already attempted: preserve first response")
    reserve = spec["unit_reservation"]
    protected = ((40, 120000) if phase == "development" else (12, 30000))
    if (totals["attempts"] + reserve["completions"] + protected[0] >
            spec["max_external_completions"] or
        totals["charged_tokens"] + reserve["tokens"] + protected[1] >
            spec["max_external_tokens"]):
        raise StageBudgetExhausted("Insufficient budget for full four-arm unit and reserve")


def run_pairs(phase, client, *, save):
    spec = load_spec()
    sources = _sources(spec)
    rows = []
    for item in spec[phase]:
        unit_id = f"{phase}:{item['source']}:{item['session']}:{item['query_index']}"
        _admit_pair(spec, phase, unit_id)
        script = sources[item["source"]][item["session"]]
        base, keys = build_session(script)
        query = script["queries"][item["query_index"]]
        ids = {entry.task_id: entry.evidence["evidence_token"] for entry in base.entries}
        for policy in spec["policies"]:
            session = deepcopy(base)
            client.set_context(phase=phase, unit_id=unit_id, policy=policy)
            before_calls = client.request_count
            before_tokens = client.total_usage.get("total_tokens", 0)
            started = time.perf_counter()
            try:
                observed = same_history_turn(
                    session, policy, query["text"], client,
                    inline_max=spec["inline_result_max_utf8_bytes"])
                score = score_turn(session, script, query, keys, observed)
            except Exception as exc:
                observed = {"status": "llm_error", "error_type": type(exc).__name__}
                score = {"valid_screen": False, "category": "llm_error"}
            selection = observed.pop("selection", None)
            rows.append({"unit_id": unit_id, "phase": phase, "policy": policy,
                         "query": query["text"], "history_fingerprint": ids,
                         "task_count": len(base.entries), "observed": observed,
                         "score": score,
                         "context_characters": selection["characters"] if selection else None,
                         "summary_triggered": selection["summary_triggered"] if selection else None,
                         "full_reads": session.full_reads, "field_reads": session.field_reads,
                         "read_payload_bytes": session.read_payload_bytes,
                         "llm_completions": client.request_count - before_calls,
                         "llm_tokens": client.total_usage.get("total_tokens", 0) - before_tokens,
                         "elapsed_ms": round((time.perf_counter() - started) * 1000, 3)})
            save(rows)
            if observed["status"] == "llm_error":
                return rows
    return rows


def run_closed(client, *, save):
    spec = load_spec()
    totals = ledger_totals(LEDGER)
    if (totals["attempts"] + 12 > spec["max_external_completions"] or
        totals["charged_tokens"] + 30000 > spec["max_external_tokens"]):
        raise StageBudgetExhausted("Insufficient budget for both closed-loop arms")
    conf = spec["closed_loop"]
    script = _sources(spec)["issue41"][conf["session"]]
    rows = []
    for policy in conf["policies"]:
        session = GranularEpisodeSession(script["id"], protocol_records41(script))
        keys = {}
        for index in conf["step_indices"]:
            step = script["steps"][index]
            unit_id = f"closed:{policy}:analysis:{index}"
            if any(row.get("event") == "reserved" and
                   row.get("context", {}).get("unit_id") == unit_id for row in _rows(LEDGER)):
                raise StageBudgetExhausted("Closed-loop turn already attempted")
            client.set_context(phase="closed", unit_id=unit_id, policy=policy)
            before = client.request_count
            before_tokens = client.total_usage.get("total_tokens", 0)
            try:
                observed = live_turn(session, policy, step["text"], client,
                                     selector=select_context41)
                if observed["outcome"]["status"] == "completed":
                    keys[step["key"]] = session.entries[-1]
            except Exception as exc:
                observed = {"outcome": {"status": "llm_error",
                                        "error_type": type(exc).__name__}}
            rows.append({"policy": policy, "kind": "analysis", "index": index,
                         "observed": observed, "task_count": len(session.entries),
                         "llm_completions": client.request_count - before,
                         "llm_tokens": client.total_usage.get("total_tokens", 0) - before_tokens})
            save(rows)
            if observed["outcome"]["status"] == "llm_error":
                return rows
        index = conf["query_index"]
        query = script["queries"][index]
        unit_id = f"closed:{policy}:history:{index}"
        if any(row.get("event") == "reserved" and
               row.get("context", {}).get("unit_id") == unit_id for row in _rows(LEDGER)):
            raise StageBudgetExhausted("Closed-loop history already attempted")
        client.set_context(phase="closed", unit_id=unit_id, policy=policy)
        before = client.request_count
        before_tokens = client.total_usage.get("total_tokens", 0)
        try:
            observed = same_history_turn(
                session, policy, query["text"], client,
                inline_max=spec["inline_result_max_utf8_bytes"])
            score = (score_turn(session, script, query, keys, observed)
                     if query["target"] in keys else
                     {"valid_screen": False, "category": "history_absent_after_prior_failure"})
            observed.pop("selection", None)
        except Exception as exc:
            observed = {"status": "llm_error", "error_type": type(exc).__name__}
            score = {"valid_screen": False, "category": "llm_error"}
        rows.append({"policy": policy, "kind": "history", "index": index,
                     "observed": observed, "score": score,
                     "task_count": len(session.entries),
                     "llm_completions": client.request_count - before,
                     "llm_tokens": client.total_usage.get("total_tokens", 0) - before_tokens})
        save(rows)
    return rows


def _new_output(phase):
    PRIVATE.mkdir(parents=True, exist_ok=True)
    path = PRIVATE / f"{phase}_{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}.json"
    if path.exists():
        raise FileExistsError("Outputs must be append-only")
    return path


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_saved_pairing(path):
    """Re-score immutable development/confirmation rows after parser fixes.

    This does not re-run the model, change a scientific oracle, or alter the
    original score embedded in the saved artifact.
    """
    path = Path(path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    phase = saved.get("phase")
    if phase not in {"development", "confirmation"}:
        raise ValueError("Only paired history-answer artifacts can be audited")
    spec = load_spec()
    sources = _sources(spec)
    items = {f"{phase}:{item['source']}:{item['session']}:{item['query_index']}": item
             for item in spec[phase]}
    audited = []
    for row in saved["rows"]:
        item = items[row["unit_id"]]
        script = sources[item["source"]][item["session"]]
        session, keys = build_session(script)
        observed = deepcopy(row["observed"])
        observed["selection"] = select_context41(session, row["query"], row["policy"])
        rescored = score_turn(session, script, script["queries"][item["query_index"]],
                              keys, observed)
        audited.append({"unit_id": row["unit_id"], "policy": row["policy"],
                        "original_valid_screen": row["score"]["valid_screen"],
                        "audited_valid_screen": rescored["valid_screen"],
                        "audited_category": rescored["category"]})
    return {"input_sha256": _sha(path), "phase": phase, "audited_rows": audited}


def run_phase(phase):
    spec = load_spec()
    path = _new_output(phase)
    raw = OpenAICompatibleClient.from_env()
    raw.max_retries = 0
    raw.max_tokens = min(raw.max_tokens, 1000)
    journal = JournaledBudgetClient(raw, path.with_suffix(".responses.jsonl"),
                                    max_requests=spec["max_external_completions"],
                                    max_total_tokens=spec["max_external_tokens"])
    client = Issue39BudgetClient(journal, LEDGER,
                                 max_requests=spec["max_external_completions"],
                                 max_tokens=spec["max_external_tokens"],
                                 model_label=raw.model, phase=phase)

    def save(rows):
        path.write_text(json.dumps({"phase": phase, "synthetic_only": True,
                                    "spec_sha256": _sha(SPEC_PATH),
                                    "old_protocol_sha256": _sha(OLD_PATH),
                                    "requested_model": raw.model,
                                    "reported_models": raw.response_models,
                                    "stage_ledger": ledger_totals(LEDGER),
                                    "rows": rows}, ensure_ascii=False,
                                   indent=2, allow_nan=False) + "\n", encoding="utf-8")

    rows = run_closed(client, save=save) if phase == "closed" else run_pairs(
        phase, client, save=save)
    save(rows)
    return path, rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("development", "confirmation", "closed"))
    parser.add_argument("--enable-paid-issue41", action="store_true")
    parser.add_argument("--ledger-status", action="store_true")
    parser.add_argument("--audit-file", type=Path)
    args = parser.parse_args(argv)
    if args.audit_file is not None:
        print(json.dumps(audit_saved_pairing(args.audit_file), ensure_ascii=False))
        return
    if args.ledger_status:
        print(json.dumps(ledger_totals(LEDGER), ensure_ascii=False))
        return
    if not args.enable_paid_issue41 or args.phase is None:
        parser.error("Paid phase requires --enable-paid-issue41 and --phase")
    path, rows = run_phase(args.phase)
    print(json.dumps({"output": str(path.relative_to(PROJECT_ROOT)),
                      "rows": len(rows), "ledger": ledger_totals(LEDGER)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
