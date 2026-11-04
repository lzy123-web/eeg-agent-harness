"""Issue #40: same-history, synthetic-only memory attribution and bounded calls."""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time

import numpy as np

from ..llm import OpenAICompatibleClient
from .integrated_method.v2_validation import JournaledBudgetClient, PRIVATE_ROOT
from .task_memory import PROJECT_ROOT
from .task_memory_issue39_budget import (Issue39BudgetClient, StageBudgetExhausted,
                                         ledger_totals, _rows)
from .task_memory_v2 import (build_protocol_session, independent_oracle,
                             protocol_records, score_read_semantics)
from .task_memory_v3 import EpisodeMemorySession, live_turn_v3, select_context_v3


SPEC_PATH = PROJECT_ROOT / "config" / "point1_task_memory_issue40.json"
HISTORY_PATH = PROJECT_ROOT / "config" / "point1_task_memory_protocol_v2.json"
PRIVATE = PRIVATE_ROOT / "point1_task_memory" / "issue40"
LEDGER = PRIVATE / "budget.jsonl"
READ_ACTION = [{"type": "function", "function": {
    "name": "submit_evidence_action",
    "description": "Answer directly from visible evidence, read a task, or clarify.",
    "parameters": {"type": "object", "properties": {
        "operation": {"type": "string", "enum": ["answer", "read", "clarify"]},
        "task_id": {"type": "string"}, "answer": {"type": "string"},
        "question": {"type": "string"},
    }, "required": ["operation"]},
}}]


def load_spec():
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _save(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                               allow_nan=False) + "\n", encoding="utf-8")


def _new_output(phase):
    PRIVATE.mkdir(parents=True, exist_ok=True)
    path = PRIVATE / f"{phase}_{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}.json"
    if path.exists():
        raise FileExistsError("Issue40 outputs must be append-only")
    return path


def _number_matches(answer, oracle):
    """A screening signal only; final answer needs separate scientific review."""
    numbers = re.findall(r"(?<![A-Za-z0-9])[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", answer)
    for token in numbers:
        value = float(token)
        if np.isclose(value, oracle, rtol=0.05, atol=5e-13):
            return True
    return False


def _direct_evidence_visible(selection, task_id):
    """A direct numerical answer needs a visible result, not merely an index."""
    if selection is None:
        return False
    payload = selection["payload"]
    cards = payload.get("cards", []) + payload.get("working_tasks", [])
    for card in cards:
        if card.get("task_id") == task_id and "result_preview" in card:
            return True
        for child in card.get("rolling_summary", []):
            if child.get("task_id") == task_id and "result_preview" in child:
                return True
    focused = payload.get("focused_evidence")
    return bool(focused and focused.get("task_id") == task_id
                and "result_preview" in focused)


def same_history_turn(session, policy, query, client):
    """One shared read/answer opportunity, at most two model completions."""
    selected = select_context_v3(session, query, policy)
    payload = {"request": query, "memory": selected["payload"]}
    messages = [
        {"role": "system", "content": (
            "你是研究用途 EEG 历史分析助手。只依据提供的历史证据回答，不推断未显示数值，"
            "不作诊断。选择 submit_evidence_action：若目标结果及精确数值已在可见上下文，"
            "用 answer 并给出处 task_id 和自然语言答复；否则用 read 并指定真实 task_id；"
            "任务或科学范围确有歧义才用 clarify。不要猜测数据、记录、条件或版本。"
            "所有策略有相同的 read_task 权限；不必为了读取而读取。")},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, allow_nan=False)},
    ]
    first = client.complete(messages, READ_ACTION,
                            tool_choice={"type": "function", "function": {
                                "name": "submit_evidence_action"}})
    calls = first.get("tool_calls") or []
    if len(calls) != 1 or calls[0].get("function", {}).get("name") != "submit_evidence_action":
        return {"status": "invalid_action", "action": None, "answer": None,
                "selection": selected, "read": None}
    try:
        action = json.loads(calls[0]["function"]["arguments"])
    except (KeyError, ValueError, TypeError):
        return {"status": "invalid_action", "action": None, "answer": None,
                "selection": selected, "read": None}
    operation = action.get("operation")
    if operation == "answer":
        answer = action.get("answer")
        status = "answered" if isinstance(answer, str) and answer.strip() else "invalid_action"
        return {"status": status, "action": action, "answer": answer,
                "selection": selected, "read": None}
    if operation == "clarify":
        return {"status": "clarification_required", "action": action,
                "answer": action.get("question"), "selection": selected, "read": None}
    if operation != "read":
        return {"status": "invalid_action", "action": action,
                "answer": None, "selection": selected, "read": None}
    observed = session.read_task(action.get("task_id"), query)
    if observed["status"] != "read":
        return {"status": observed["status"], "action": action, "answer": None,
                "selection": selected, "read": observed}
    second = client.complete([
        {"role": "system", "content": (
            "仅依据下面真实读取的 EEG 任务证据回答用户问题。准确表述记录、分析类型、"
            "条件/窗口/版本、数值和单位；不能混用其他任务的结果，不诊断。")},
        {"role": "user", "content": json.dumps({"request": query, "evidence": observed},
                                               ensure_ascii=False, allow_nan=False)},
    ], [])
    answer = second.get("content") if isinstance(second, dict) else None
    status = "answered" if isinstance(answer, str) and answer.strip() else "invalid_answer"
    return {"status": status, "action": action, "answer": answer,
            "selection": selected, "read": observed}


def score_turn(session, script, query, keys, observed):
    """Post-hoc oracle; nothing in this function is sent to the model."""
    action = observed.get("action") or {}
    chosen = action.get("task_id")
    target = keys[query["target"]]
    step = next(item for item in script["steps"] if item["key"] == query["target"])
    oracle = independent_oracle(session.records[step["record"]], step, query["field"])
    read = None
    if chosen:
        read = score_read_semantics(session, script, query, keys, chosen,
                                    observed_read=observed.get("read"))
    answer = observed.get("answer") or ""
    numeric = bool(answer and _number_matches(answer, oracle))
    direct = action.get("operation") == "answer"
    direct_visible = (not direct or _direct_evidence_visible(
        observed.get("selection"), chosen))
    return {"target_match": chosen == target.task_id,
            "semantic_evidence_valid": bool(read and read["valid"]),
            "numeric_screen_match": numeric,
            "direct_evidence_visible": direct_visible,
            "oracle_value": oracle,
            "candidate_id": chosen,
            "valid_screen": bool(read and read["valid"] and numeric and direct_visible
                                 and observed.get("status") == "answered"),
            "requires_answer_review": True,
            "failure_category": ("evidence_selection" if not read or not read["valid"]
                                 else "unsupported_direct_answer" if not direct_visible
                                 else "answer_or_number" if not numeric
                                 else "none"),
            "semantic_checks": read["checks"] if read else None}


def _admit_unit(spec, phase, unit_id):
    totals = ledger_totals(LEDGER)
    rows = _rows(LEDGER)
    if any(row.get("event") == "reserved" and
           row.get("context", {}).get("unit_id") == unit_id for row in rows):
        raise StageBudgetExhausted("Unit already attempted; do not rerun or overwrite")
    reserve = spec["pair_reservation"]
    future = (dict(completions=36, tokens=90000) if phase == "development"
              else dict(completions=12, tokens=30000) if phase == "confirmation"
              else dict(completions=0, tokens=0))
    if (totals["attempts"] + reserve["completions"] + future["completions"] >
            spec["max_external_completions"] or
        totals["charged_tokens"] + reserve["tokens"] + future["tokens"] >
            spec["max_external_tokens"]):
        raise StageBudgetExhausted("Insufficient budget for complete four-arm unit and reserves")


def run_pairs(phase, client, *, save):
    spec = load_spec()
    history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    scripts = {item["id"]: item for item in history["sessions"]}
    rows = []
    for item in spec[phase]:
        unit_id = f"{phase}:{item['session']}:{item['query_index']}"
        _admit_unit(spec, phase, unit_id)
        script = scripts[item["session"]]
        base, keys = build_protocol_session(script, session_class=EpisodeMemorySession)
        query = script["queries"][item["query_index"]]
        fingerprints = {entry.task_id: entry.evidence["evidence_token"]
                        for entry in base.entries}
        for policy in spec["policies"]:
            session = deepcopy(base)
            client.set_context(phase=phase, unit_id=unit_id, policy=policy)
            before_calls = client.request_count
            before_tokens = client.total_usage.get("total_tokens", 0)
            started = time.perf_counter()
            try:
                observed = same_history_turn(session, policy, query["text"], client)
                score = score_turn(session, script, query, keys, observed)
            except Exception as exc:
                observed = {"status": "llm_error", "error_type": type(exc).__name__}
                score = {"valid_screen": False, "failure_category": "llm_error"}
            selected = observed.pop("selection", None)
            row = {"unit_id": unit_id, "phase": phase, "policy": policy,
                   "history_fingerprint": fingerprints, "query": query["text"],
                   "task_count": len(base.entries), "observed": observed, "score": score,
                   "context_characters": selected["characters"] if selected else None,
                   "summary_triggered": selected["summary_triggered"] if selected else None,
                   "llm_completions": client.request_count - before_calls,
                   "llm_tokens": client.total_usage.get("total_tokens", 0) - before_tokens,
                   "elapsed_ms": round((time.perf_counter() - started) * 1000, 3)}
            rows.append(row)
            save(rows)
            if observed["status"] == "llm_error":
                return rows
    return rows


def run_closed(client, *, save, direct_history=False):
    spec = load_spec()
    conf = spec["closed_loop"]
    totals = ledger_totals(LEDGER)
    # Admit the complete two-arm closed loop, never spend the last budget on
    # only the candidate or only its full-history comparator.
    if (totals["attempts"] + 12 > spec["max_external_completions"] or
        totals["charged_tokens"] + 30000 > spec["max_external_tokens"]):
        raise StageBudgetExhausted("Insufficient budget for both closed-loop arms")
    history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    script = next(item for item in history["sessions"] if item["id"] == conf["session"])
    rows = []
    for policy in conf["policies"]:
        session = EpisodeMemorySession(script["id"], protocol_records(script))
        keys = {}
        for kind, indices in (("analysis", conf["step_indices"]),
                              ("history", conf["query_indices"])):
            for index in indices:
                text = script["steps" if kind == "analysis" else "queries"][index]["text"]
                prefix = "closed-direct" if direct_history else "closed"
                unit_id = f"{prefix}:{policy}:{kind}:{index}"
                if any(row.get("event") == "reserved" and
                       row.get("context", {}).get("unit_id") == unit_id
                       for row in _rows(LEDGER)):
                    raise StageBudgetExhausted("Closed-loop turn already attempted")
                client.set_context(phase="closed", unit_id=unit_id, policy=policy)
                before_calls = client.request_count
                before_tokens = client.total_usage.get("total_tokens", 0)
                try:
                    if kind == "history" and direct_history:
                        item = same_history_turn(session, policy, text, client)
                        score = (score_turn(session, script, script["queries"][index],
                                            keys, item)
                                 if script["queries"][index]["target"] in keys
                                 else {"valid_screen": False,
                                       "failure_category": "history_absent_after_prior_failure"})
                        item.pop("selection", None)
                    else:
                        item = live_turn_v3(session, policy, text, client,
                                            deliver_answer=(kind == "history"))
                        score = None
                        if kind == "analysis" and item["outcome"]["status"] == "completed":
                            step = script["steps"][index]
                            keys[step["key"]] = session.entries[-1]
                except Exception as exc:
                    item = {"outcome": {"status": "llm_error",
                                        "error_type": type(exc).__name__}}
                    score = {"valid_screen": False, "failure_category": "llm_error"}
                status = (item.get("outcome") or {}).get("status", item.get("status"))
                rows.append({"policy": policy, "kind": kind, "turn_index": index,
                             "request": text, "observed": item,
                             "score": score, "history_interface": (
                                 "direct_or_read" if direct_history else "legacy_history"),
                             "task_count": len(session.entries),
                             "llm_completions": client.request_count - before_calls,
                             "llm_tokens": client.total_usage.get("total_tokens", 0)
                                           - before_tokens})
                save(rows)
                if status == "llm_error":
                    return rows
    return rows


def run_phase(phase):
    spec = load_spec()
    output = _new_output(phase)
    raw = OpenAICompatibleClient.from_env()
    raw.max_retries = 0
    raw.max_tokens = min(raw.max_tokens, 1000)
    journal = JournaledBudgetClient(raw, output.with_suffix(".responses.jsonl"),
                                    max_requests=spec["max_external_completions"],
                                    max_total_tokens=spec["max_external_tokens"])
    client = Issue39BudgetClient(journal, LEDGER,
                                 max_requests=spec["max_external_completions"],
                                 max_tokens=spec["max_external_tokens"],
                                 model_label=raw.model, phase=phase)

    def save(rows):
        _save(output, {"phase": phase, "synthetic_only": True,
                       "spec_sha256": _hash(SPEC_PATH),
                       "history_sha256": _hash(HISTORY_PATH),
                       "requested_model": raw.model,
                       "reported_models": raw.response_models,
                       "stage_ledger": ledger_totals(LEDGER), "rows": rows})

    rows = (run_closed(client, save=save, direct_history=phase == "closed-direct")
            if phase in {"closed", "closed-direct"} else
            run_pairs(phase, client, save=save))
    save(rows)
    return output, rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("development", "confirmation",
                                            "closed", "closed-direct"))
    parser.add_argument("--enable-paid-issue40", action="store_true")
    parser.add_argument("--ledger-status", action="store_true")
    args = parser.parse_args(argv)
    if args.ledger_status:
        print(json.dumps(ledger_totals(LEDGER), ensure_ascii=False))
        return
    if not args.enable_paid_issue40 or args.phase is None:
        parser.error("Paid phase requires --enable-paid-issue40 and --phase")
    output, rows = run_phase(args.phase)
    print(json.dumps({"output": str(output.relative_to(PROJECT_ROOT)),
                      "rows": len(rows), "ledger": ledger_totals(LEDGER)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
