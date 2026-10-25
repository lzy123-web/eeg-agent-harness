"""Issue #42: one bounded entry for complete, synthetic EEG memory workflows.

This composes the existing episode store, Registry/Executor, and Issue #41
context views. It is an evaluation/use entry, not a new EEG executor or planner.
"""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import median
import time

from ..llm import OpenAICompatibleClient
from .integrated_method.v2_validation import JournaledBudgetClient, PRIVATE_ROOT
from .task_memory import PROJECT_ROOT, live_turn
from .task_memory_issue39_budget import (Issue39BudgetClient, StageBudgetExhausted,
                                         _rows, ledger_totals)
from .task_memory_issue41 import (GranularEpisodeSession, _encoded,
                                  _number_in_answer, _visible_exact,
                                  protocol_records41, select_context41)
from .task_memory_v2 import independent_oracle, parse_visible_query
from .task_memory_v3 import _summary as _task_summary, scientific_read_mismatch


SPEC_PATH = PROJECT_ROOT / "config" / "point1_task_memory_issue42.json"
PRIVATE = PRIVATE_ROOT / "point1_task_memory" / "issue42"
LEDGER = PRIVATE / "budget.jsonl"
ACTION_TOOL = [{"type": "function", "function": {
    "name": "submit_evidence_action",
    "description": "Answer from visible evidence, read one or more exact results, or clarify.",
    "parameters": {"type": "object", "properties": {
        "operation": {"type": "string", "enum": ["answer", "read_full", "read_fields", "clarify"]},
        "task_id": {"type": "string"}, "answer": {"type": "string"},
        "field_paths": {"type": "array", "items": {"type": "array", "items": {
            "anyOf": [{"type": "string"}, {"type": "integer"}]}}},
        "scope_quote": {"type": "string", "description":
                        "For comparisons only: verbatim phrase of the user's request that identifies this read's record, condition, window or version."},
        "question": {"type": "string"},
    }, "required": ["operation"]},
}}]


def load_spec():
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def spec_sha():
    return hashlib.sha256(SPEC_PATH.read_bytes()).hexdigest()


def _scope_for_read(session, entry, query, quote):
    """Validate model-supplied verbatim request span; never use evaluator gold.

    A global comparison may mention mutually exclusive records, conditions or
    windows. The old single-target guard must then run on the per-read phrase.
    Empty/underspecified spans cannot erase an explicit distinction.
    """
    if quote is None:
        return query
    if not isinstance(quote, str) or len(quote.strip()) < 4 or quote not in query:
        return None
    whole = parse_visible_query(session, query)
    local = parse_visible_query(session, quote)
    if len(whole.records) > 1 and local.records != (entry.record,):
        return None
    if len(whole.event_labels) > 1 and entry.capability.startswith("event"):
        if not set(local.event_labels) & set(entry.parameters.get("labels", ())):
            return None
    both_scopes = ("事件" in query or "试次" in query) and "连续" in query
    if both_scopes and local.scientific_scope is None:
        return None
    windows = re.findall(r"\d+(?:\.\d+)?\s*(?:到|至|[-~])\s*\d+(?:\.\d+)?\s*(?:秒|s\b)", query)
    if len(set(windows)) > 1 and local.window is None:
        return None
    in_revision_chain = bool(entry.revision_of or any(
        other.revision_of == entry.task_id for other in session.entries))
    if in_revision_chain and ("修改前" in query or "旧版" in query) and (
            "修改后" in query or "新版" in query):
        if local.version is None:
            return None
    if scientific_read_mismatch(session, entry, quote):
        return None
    return quote


def history_turn(session, policy, query, client, *, inline_max=256):
    """Common evidence action for all arms, including multi-object comparisons."""
    selected = select_context41(session, query, policy, inline_max=inline_max)
    system = (
        "你是研究用途 EEG 历史分析助手，仅依真实证据，不诊断、不猜数值。"
        "各方案均可直接 answer、read_fields、read_full 或 clarify；精确值已可见时可直接答。"
        "若比较多个对象需要读取，可一次提交最多四个 read 操作。每次读须有真实 task_id。"
        "当完整请求包含互斥的记录、条件、窗口或版本时，给每个 read 附 scope_quote："
        "从用户原句原样摘取专指该对象的片段；禁止编造或删除限定词。"
        "字段路径只能来自可见字段索引；不明时读完整证据。"
        "回答应区分记录、条件、窗口、版本和单位；绝对功率是 V²，不是 V²/Hz。")
    first = client.complete([
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps({"request": query, "memory": selected["payload"]},
                                              ensure_ascii=False, allow_nan=False)},
    ], ACTION_TOOL, tool_choice={"type": "function", "function": {"name": "submit_evidence_action"}})
    try:
        calls = first.get("tool_calls") or []
        if not 1 <= len(calls) <= 4 or any(
                call.get("function", {}).get("name") != "submit_evidence_action"
                for call in calls):
            raise ValueError("Invalid evidence tool call")
        actions = [json.loads(call["function"]["arguments"]) for call in calls]
        if len(actions) > 1 and any(item.get("operation") not in {"read_full", "read_fields"}
                                    for item in actions):
            raise ValueError("Mixed evidence actions")
    except (ValueError, KeyError, TypeError):
        return {"status": "invalid_action", "actions": [], "answer": None,
                "selection": selected, "reads": []}
    first_action = actions[0]
    if first_action.get("operation") == "answer":
        answer = first_action.get("answer")
        return {"status": "answered" if isinstance(answer, str) and answer.strip()
                else "invalid_answer", "actions": actions, "answer": answer,
                "selection": selected, "reads": []}
    if first_action.get("operation") == "clarify":
        return {"status": "clarification_required", "actions": actions,
                "answer": first_action.get("question"), "selection": selected, "reads": []}
    reads = []
    for action in actions:
        entry = next((item for item in session.entries
                      if item.task_id == action.get("task_id")), None)
        if entry is None:
            reads.append({"status": "clarification_required", "code": "TASK_NOT_FOUND"})
            continue
        scope = _scope_for_read(session, entry, query, action.get("scope_quote"))
        if scope is None:
            reads.append({"status": "clarification_required", "code": "INVALID_SCOPE_QUOTE"})
        elif action.get("operation") == "read_full":
            reads.append(session.read_task(entry.task_id, scope))
        elif action.get("operation") == "read_fields":
            reads.append(session.read_task_fields(entry.task_id,
                                                  action.get("field_paths"), scope))
        else:
            reads.append({"status": "invalid_action", "code": "UNKNOWN_READ"})
    if not any(item.get("status") in {"read", "read_fields"} for item in reads):
        return {"status": reads[0]["status"], "actions": actions, "answer": None,
                "selection": selected, "reads": reads}
    second = client.complete([
        {"role": "system", "content": "只根据下列真实 EEG 证据回答原请求。逐个注明记录、科学条件、窗口、版本、数值、单位；失败的读取不得编造。"},
        {"role": "user", "content": json.dumps({"request": query, "evidence": reads},
                                              ensure_ascii=False, allow_nan=False)},
    ], [])
    answer = second.get("content") if isinstance(second, dict) else None
    return {"status": "answered" if isinstance(answer, str) and answer.strip()
            else "invalid_answer", "actions": actions, "answer": answer,
            "selection": selected, "reads": reads}


def _value_at(result, field):
    for part in field:
        result = result[part]
    return result


def _oracle_values(session, turn):
    return [independent_oracle(session.records[turn["record"]], turn, field)
            for field in turn["fields"]]


def _actual_matches_oracle(entry, turn, session):
    try:
        return all(math.isclose(float(_value_at(entry.result, field)), float(expected),
                                rel_tol=5e-3, abs_tol=5e-13)
                   for field, expected in zip(turn["fields"], _oracle_values(session, turn)))
    except (KeyError, IndexError, ValueError, TypeError):
        return False


def _attributed_in_answer(answer, value, step, peers):
    """Conservative positive screen; an ambiguous sentence needs manual review."""
    # A record label and its value can be separated by a Chinese comma within
    # one valid table/prose line; only sentence/line boundaries split binding.
    records = {item["record"] for item in peers}
    anchors = "|".join(re.escape(record) for record in sorted(records, key=len, reverse=True))
    # Preserve commas within one record's clause; a comma introducing another
    # explicit record starts a new clause. This rejects A/B value swaps without
    # severing "记录 A，通道，窗口：RMS" at its ordinary Chinese commas.
    clauses = []
    for sentence in re.split(r"[；;。\n]+", answer):
        boundary = rf"[,，、]\s*(?=(?:记录\s*)?(?:{anchors})(?![A-Za-z0-9]))"
        clauses.extend(part.strip() for part in re.split(boundary, sentence)
                       if part.strip())
    same_record = [item for item in peers if item["record"] == step["record"]]
    need_window = len({(item["parameters"].get("start"), item["parameters"].get("end"),
                         item["parameters"].get("tmin"), item["parameters"].get("tmax"))
                       for item in same_record}) > 1
    need_scope = len({item["capability"] in {"event_bandpower", "epoch_summary"}
                      for item in same_record}) > 1
    need_label = len({tuple(item["parameters"].get("labels", ()))
                      for item in peers if item["parameters"].get("labels")}) > 1
    params = step["parameters"]
    start = params.get("start", params.get("tmin"))
    end = params.get("end", params.get("tmax"))
    for clause in clauses:
        if not _number_in_answer(clause, value):
            continue
        if len(records) > 1 and not re.search(
                rf"(?<![A-Za-z0-9]){re.escape(step['record'])}(?![A-Za-z0-9])", clause):
            continue
        if need_window and not re.search(
                rf"(?<!\d){start:g}\s*(?:到|至|[-–—~])\s*{end:g}(?!\d)", clause):
            continue
        if need_scope:
            is_event = step["capability"] in {"event_bandpower", "epoch_summary"}
            if is_event != bool(re.search(r"事件|试次|epoch|event", clause, re.I)):
                continue
        if need_label and not any(label in clause for label in params.get("labels", ())):
            continue
        return True
    return False


def score_analysis(session, turn, observed, keys):
    """Scientific and public-action axes stay separate; first failure is kept."""
    action = observed.get("action") or {}
    outcome = observed.get("outcome") or {}
    entry = next((item for item in session.entries
                  if item.task_id == outcome.get("task_id")), None)
    expected_parent = keys.get(turn.get("revision_of"))
    protocol_ok = (action.get("operation") == "revise" if expected_parent else
                   action.get("operation") in {"analyze", "switch_analyze"})
    science_ok = bool(entry and entry.record == turn["record"]
                      and entry.capability == turn["capability"]
                      and entry.parameters == turn["parameters"]
                      and entry.revision_of == (expected_parent.task_id if expected_parent else None)
                      and entry.evidence["source"] == session.records[turn["record"]].source
                      and _actual_matches_oracle(entry, turn, session))
    answer = observed.get("final_answer")
    answer_screen = (None if answer is None else bool(science_ok and all(
        _number_in_answer(answer, value) for value in _oracle_values(session, turn))))
    return {"science_valid_screen": science_ok and answer_screen is not False,
            "execution_science_valid": science_ok, "answer_numeric_screen": answer_screen,
            "protocol_action_valid": protocol_ok,
            "category": "correct_screen" if science_ok and answer_screen is not False else
                        "action_or_execution" if not science_ok else "answer_evidence_error",
            "oracle_values": _oracle_values(session, turn)}


def score_history(session, turn, observed, keys, turns_by_key):
    """No target IDs enter the model; exact targets are evaluator-only."""
    answer = observed.get("answer") or ""
    selection = observed.get("selection")
    actions = observed.get("actions") or []
    reads = observed.get("reads") or []
    checks = []
    peers = [turns_by_key[target["key"]] for target in turn["targets"]]
    for target in turn["targets"]:
        entry = keys.get(target["key"])
        step = turns_by_key[target["key"]]
        oracle = [independent_oracle(session.records[step["record"]], step, field)
                  for field in target["fields"]]
        matched = bool(entry and _actual_matches_oracle(entry, step, session))
        direct = bool(entry and selection and
                      _visible_exact(selection, entry.task_id))
        read = any(item.get("task_id") == entry.task_id and
                   item.get("status") in {"read", "read_fields"}
                   for item in reads) if entry else False
        visible = direct or read
        attributed = all(_attributed_in_answer(answer, value, step, peers)
                         for value in oracle)
        checks.append({"key": target["key"], "target_task_id": entry.task_id if entry else None,
                       "oracle_values": oracle, "source_and_result_valid": matched,
                       "evidence_available": visible,
                       "numeric_screen": all(_number_in_answer(answer, value) for value in oracle),
                       "attribution_screen": attributed})
    unit = "V²" if any(turns_by_key[target["key"]]["capability"] != "amplitude"
                       for target in turn["targets"]) else "V"
    positive = re.sub(r"(?:非|不是|并非|不等于|not)\s*V²(?:/Hz)?", "", answer,
                      flags=re.IGNORECASE)
    unit_ok = ("V²" in positive and "V²/Hz" not in positive if unit == "V²"
               else "V" in positive and "V²" not in positive)
    record_ok = all(turns_by_key[target["key"]]["record"] in answer
                    for target in turn["targets"])
    science_ok = (observed.get("status") == "answered" and all(
        all(check[name] for name in ("source_and_result_valid", "evidence_available",
                                      "numeric_screen", "attribution_screen")) for check in checks)
                  and unit_ok and record_ok)
    protocol_ok = (observed.get("status") == "answered" and
                   (all(action.get("operation") == "answer" for action in actions)
                    or any(action.get("operation") in {"read_full", "read_fields"}
                           for action in actions)))
    return {"science_valid_screen": science_ok, "protocol_action_valid": protocol_ok,
            "target_checks": checks, "unit_screen": unit_ok, "record_screen": record_ok,
            "requires_manual_science_review": True,
            "category": "correct_screen" if science_ok else
                        "history_absent" if any(not check["target_task_id"] for check in checks)
                        else "evidence_selection_or_read" if any(
                            not check["evidence_available"] for check in checks)
                        else "answer_or_scope_error"}


def _session(script):
    records = protocol_records41({**script, "steps": []})
    return GranularEpisodeSession(script["id"], records)


def offline_preflight(spec=None):
    spec = spec or load_spec()
    rows = []
    for script in spec["workflows"]:
        session = _session(script)
        keys = {}
        for turn in script["turns"]:
            if turn["kind"] != "analysis":
                if any(target["key"] not in keys for target in turn["targets"]):
                    raise AssertionError("Historical target precedes its analysis")
                continue
            parent = keys.get(turn.get("revision_of"))
            outcome = session.analyze(turn["record"], turn["capability"],
                                      turn["parameters"], turn["text"],
                                      revision_of=parent.task_id if parent else None)
            if outcome["status"] != "completed":
                raise AssertionError(f"Real tool failure: {script['id']}: {outcome}")
            entry = session.entries[-1]
            if not _actual_matches_oracle(entry, turn, session):
                raise AssertionError(f"Independent oracle mismatch: {script['id']}:{turn['key']}")
            keys[turn["key"]] = entry
        rows.append({"workflow": script["id"], "analysis_tasks": len(keys),
                     "history_turns": sum(turn["kind"] == "history"
                                          for turn in script["turns"]),
                     "sources": {alias: record.source for alias, record in session.records.items()},
                     "task_evidence": {key: entry.evidence["evidence_token"]
                                       for key, entry in keys.items()}})
    return rows


def offline_local_cost(*, repetitions=30):
    """Indicative local summary derivation and context-selection costs, no API."""
    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    rows = []
    for script in load_spec()["workflows"]:
        if script["id"] == "D-short":
            continue
        index = len(script["turns"]) - 1
        session, _ = build_same_history(script, index)
        query = script["turns"][index]["text"]
        for policy in ("F", "S", "H", "HC"):
            select_context41(session, query, policy)
            times = []
            for _ in range(repetitions):
                started = time.perf_counter()
                selected = select_context41(session, query, policy)
                times.append((time.perf_counter() - started) * 1000)
            rows.append({"workflow": script["id"], "operation": "select_context",
                         "policy": policy, "median_ms": round(median(times), 6),
                         "serialized_bytes": len(_encoded(selected["payload"]))})
        times = []
        for _ in range(repetitions):
            started = time.perf_counter()
            [_task_summary(entry) for entry in session.entries]
            times.append((time.perf_counter() - started) * 1000)
        rows.append({"workflow": script["id"], "operation": "derive_all_task_summaries",
                     "policy": "shared", "median_ms": round(median(times), 6),
                     "task_count": len(session.entries)})
    return rows


def _save(path, phase, spec, rows, client=None):
    path.write_text(json.dumps({"phase": phase, "synthetic_only": True,
                                "spec_sha256": spec_sha(),
                                "requested_model": getattr(client, "model", None),
                                "ledger": ledger_totals(LEDGER) if LEDGER.exists() else None,
                                "rows": rows}, ensure_ascii=False, allow_nan=False,
                               indent=2) + "\n", encoding="utf-8")


def _admit_unit(spec, unit_id, *, reserve_calls, reserve_tokens):
    rows = _rows(LEDGER)
    if any(row.get("event") == "reserved" and
           row.get("context", {}).get("unit_id") == unit_id for row in rows):
        raise StageBudgetExhausted("Unit already attempted; preserve first response")
    totals = ledger_totals(LEDGER)
    if (totals["attempts"] + reserve_calls > spec["max_external_completions"] or
            totals["charged_tokens"] + reserve_tokens > spec["max_external_tokens"]):
        raise StageBudgetExhausted("Insufficient stage budget for complete paired unit")


def _record_row(client, before, started, policy, script, mode, index, observed, score,
                session):
    selection = observed.pop("selection", None)
    return {"workflow": script["id"], "mode": mode, "turn_index": index,
            "policy": policy, "request": script["turns"][index]["text"],
            "observed": observed, "score": score,
            "context_characters": selection["characters"] if selection else
                                  observed.get("working_context_estimated_tokens"),
            "summary_triggered": selection.get("summary_triggered") if selection else None,
            "full_reads": session.full_reads, "field_reads": session.field_reads,
            "read_payload_bytes": session.read_payload_bytes,
            "llm_completions": client.request_count - before[0],
            "llm_tokens": client.total_usage.get("total_tokens", 0) - before[1],
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3)}


def run_workflow(script, policy, client, *, mode="closed", save=lambda row: None):
    """Use the same public natural-language and evidence actions for every arm."""
    session = _session(script)
    keys = {}
    turns_by_key = {turn["key"]: turn for turn in script["turns"] if "key" in turn}
    rows = []
    for index, turn in enumerate(script["turns"]):
        client.set_context(unit_id=f"{mode}:{script['id']}",
                           workflow=script["id"], policy=policy, turn=index)
        before = (client.request_count, client.total_usage.get("total_tokens", 0))
        started = time.perf_counter()
        try:
            if turn["kind"] == "analysis":
                observed = live_turn(session, policy, turn["text"], client,
                                     deliver_answer=False, selector=select_context41)
                score = score_analysis(session, turn, observed, keys)
                if observed["outcome"]["status"] == "completed":
                    keys[turn["key"]] = session.entries[-1]
            else:
                observed = history_turn(session, policy, turn["text"], client)
                score = score_history(session, turn, observed, keys, turns_by_key)
        except StageBudgetExhausted:
            raise
        except Exception as exc:
            observed = {"status": "runtime_error", "error_type": type(exc).__name__}
            score = {"science_valid_screen": False, "protocol_action_valid": False,
                     "category": "runtime_error"}
        row = _record_row(client, before, started, policy, script, mode, index,
                          observed, score, session)
        rows.append(row)
        save(row)
    return rows


def build_same_history(script, stop_index):
    session = _session(script)
    keys = {}
    for turn in script["turns"][:stop_index]:
        if turn["kind"] != "analysis":
            continue
        parent = keys.get(turn.get("revision_of"))
        outcome = session.analyze(turn["record"], turn["capability"],
                                  turn["parameters"], turn["text"],
                                  revision_of=parent.task_id if parent else None)
        if outcome["status"] != "completed":
            raise AssertionError("Same-history real tool snapshot failed")
        keys[turn["key"]] = session.entries[-1]
    return session, keys


def run_same_history(script, index, policy, client, *, save=lambda row: None):
    turn = script["turns"][index]
    if turn["kind"] != "history":
        raise ValueError("Same-history checkpoint must be a history turn")
    session, keys = build_same_history(script, index)
    turns_by_key = {item["key"]: item for item in script["turns"] if "key" in item}
    client.set_context(unit_id=f"confirmation:{script['id']}",
                       workflow=script["id"], policy=policy, turn=index)
    before = (client.request_count, client.total_usage.get("total_tokens", 0))
    started = time.perf_counter()
    try:
        observed = history_turn(session, policy, turn["text"], client)
        score = score_history(session, turn, observed, keys, turns_by_key)
    except StageBudgetExhausted:
        raise
    except Exception as exc:
        observed = {"status": "runtime_error", "error_type": type(exc).__name__}
        score = {"science_valid_screen": False, "protocol_action_valid": False,
                 "category": "runtime_error"}
    row = _record_row(client, before, started, policy, script, "same", index,
                      observed, score, session)
    row["snapshot_evidence_tokens"] = {key: entry.evidence["evidence_token"]
                                       for key, entry in keys.items()}
    save(row)
    return row


def run_phase(phase):
    spec = load_spec()
    if phase not in {"development", "confirmation"}:
        raise ValueError("Unknown phase")
    offline_preflight(spec)
    PRIVATE.mkdir(parents=True, exist_ok=True)
    path = PRIVATE / f"{phase}_{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}.json"
    if path.exists():
        raise FileExistsError(path)
    raw = OpenAICompatibleClient.from_env()
    raw.max_retries = 0
    raw.max_tokens = min(raw.max_tokens, spec["model_max_output_tokens"])
    journal = JournaledBudgetClient(raw, path.with_suffix(".responses.jsonl"),
                                    max_requests=spec["max_external_completions"],
                                    max_total_tokens=spec["max_external_tokens"])
    client = Issue39BudgetClient(journal, LEDGER,
                                 max_requests=spec["max_external_completions"],
                                 max_tokens=spec["max_external_tokens"],
                                 model_label=raw.model, phase=phase)
    rows = []
    def save(row):
        rows.append(row)
        _save(path, phase, spec, rows, client)
    workflows = {item["id"]: item for item in spec["workflows"]}
    for workflow_id in spec[phase]:
        script = workflows[workflow_id]
        # Rotate order before outputs exist. All three arms in each complete unit.
        arms = (["S", "HC", "F"] if workflow_id != "C-mixed" else ["HC", "F", "S"])
        if phase == "development":
            arms = ["S", "HC", "F"]
        estimated_calls = len(arms) * (2 * len(script["turns"]) + 2)
        _admit_unit(spec, f"{phase}:{workflow_id}",
                    reserve_calls=estimated_calls, reserve_tokens=75000)
        for policy in arms:
            run_workflow(script, policy, client, mode=phase, save=save)
        if phase == "confirmation":
            checkpoint = next(index for index, item in enumerate(script["turns"])
                              if item["kind"] == "history")
            for policy in arms:
                run_same_history(script, checkpoint, policy, client, save=save)
    _save(path, phase, spec, rows, client)
    return path, rows


def audit_saved(path):
    """Append-only evaluator correction; never edits original response/score."""
    path = Path(path).resolve()
    if not path.is_relative_to(PRIVATE.resolve()) or not path.name.endswith(".json"):
        raise ValueError("Audit input must be an Issue42 private result file")
    saved = json.loads(path.read_text(encoding="utf-8"))
    if saved.get("spec_sha256") != spec_sha():
        raise ValueError("Frozen protocol hash differs; preserve old scoring")
    scripts = {item["id"]: item for item in load_spec()["workflows"]}
    audited = []
    for row in saved["rows"]:
        turn = scripts[row["workflow"]]["turns"][row["turn_index"]]
        if turn["kind"] != "history":
            continue
        checks = row["score"].get("target_checks") or []
        answer = row["observed"].get("answer") or ""
        by_key = {item["key"]: item for item in scripts[row["workflow"]]["turns"]
                  if "key" in item}
        peers = [by_key[target["key"]] for target in turn["targets"]]
        revised = []
        for check in checks:
            step = by_key[check["key"]]
            attributed = all(_attributed_in_answer(answer, value, step, peers)
                             for value in check["oracle_values"])
            revised.append({"key": check["key"],
                            "old_attribution_screen": check["attribution_screen"],
                            "audited_attribution_screen": attributed,
                            "source_and_result_valid": check["source_and_result_valid"],
                            "evidence_available": check["evidence_available"],
                            "numeric_screen": check["numeric_screen"]})
        new_science = bool(row["observed"].get("status") == "answered"
                           and checks and all(all(item[name] for name in (
                               "source_and_result_valid", "evidence_available",
                               "numeric_screen", "audited_attribution_screen"))
                               for item in revised)
                           and row["score"].get("unit_screen")
                           and row["score"].get("record_screen"))
        audited.append({"workflow": row["workflow"], "mode": row["mode"],
                        "policy": row["policy"], "turn_index": row["turn_index"],
                        "old_science_valid_screen": row["score"]["science_valid_screen"],
                        "audited_science_valid_screen": new_science,
                        "target_checks": revised})
    return {"input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "scoring_change": "Clause binding: commas no longer split record from scalar",
            "audited_rows": audited}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--offline-cost", action="store_true")
    parser.add_argument("--ledger-status", action="store_true")
    parser.add_argument("--phase", choices=("development", "confirmation"))
    parser.add_argument("--enable-paid-issue42", action="store_true")
    parser.add_argument("--audit-file", type=Path)
    args = parser.parse_args(argv)
    if args.audit_file:
        print(json.dumps(audit_saved(args.audit_file), ensure_ascii=False))
        return
    if args.offline:
        print(json.dumps({"spec_sha256": spec_sha(), "preflight": offline_preflight()},
                         ensure_ascii=False))
        return
    if args.offline_cost:
        print(json.dumps(offline_local_cost(), ensure_ascii=False))
        return
    if args.ledger_status:
        print(json.dumps(ledger_totals(LEDGER), ensure_ascii=False))
        return
    if not args.enable_paid_issue42 or not args.phase:
        parser.error("Paid phase requires explicit --enable-paid-issue42 and --phase")
    path, rows = run_phase(args.phase)
    print(json.dumps({"output": str(path.relative_to(PROJECT_ROOT)), "rows": len(rows),
                      "ledger": ledger_totals(LEDGER)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
