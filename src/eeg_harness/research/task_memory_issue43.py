"""Issue #43: common evidence handoff and bounded complete-task evaluation.

Historical Issue #42 entry remains runnable; all arms share this repaired path.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import time

from ..llm import OpenAICompatibleClient
from .integrated_method.v2_validation import JournaledBudgetClient, PRIVATE_ROOT
from .task_memory import PROJECT_ROOT
from .task_memory_evidence import (add_readable_paths, bind_read_scope,
                                   exact_visible, merge_evidence, normalized_read,
                                   visible_cards)
from .task_memory_issue39_budget import (Issue39BudgetClient, StageBudgetExhausted,
                                         _rows, ledger_totals)
from .task_memory_issue41 import (_encoded, _number_in_answer, select_context41)
from .task_memory_issue42 import (_actual_matches_oracle,
                                  history_turn as old_history_turn,
                                  score_history as old_score_history,
                                  build_same_history, load_spec as old_spec,
                                  offline_preflight as old_preflight, run_same_history,
                                  run_workflow)
from .task_memory_v2 import independent_oracle


SPEC_PATH = PROJECT_ROOT / "config" / "point1_task_memory_issue43.json"
PRIVATE = PRIVATE_ROOT / "point1_task_memory" / "issue43"
LEDGER = PRIVATE / "budget.jsonl"
ACTION_TOOL = [{"type": "function", "function": {
    "name": "submit_evidence_action",
    "description": "Answer from exact visible EEG evidence, read one task, or clarify.",
    "parameters": {"type": "object", "properties": {
        "operation": {"type": "string", "enum": ["answer", "read_full", "read_fields", "clarify"]},
        "task_id": {"type": "string"}, "answer": {"type": "string"},
        "question": {"type": "string"},
        "field_paths": {"type": "array", "items": {"type": "array", "items": {
            "anyOf": [{"type": "string"}, {"type": "integer"}]}}},
        "scope": {"type": "object", "properties": {
            "record": {"type": "string"},
            "kind": {"type": "string", "enum": ["event", "continuous"]},
            "condition": {"type": "string"}, "channel": {"type": "string"},
            "window": {"type": "array", "items": {"type": "number"}},
            "version": {"type": "string", "enum": ["old", "new"]}},
            "additionalProperties": False},
    }, "required": ["operation"]},
}}]


def load_spec():
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def spec_sha():
    return hashlib.sha256(SPEC_PATH.read_bytes()).hexdigest()


def select_context43(session, query, policy, *, inline_max=256):
    return add_readable_paths(session, select_context41(
        session, query, policy, inline_max=inline_max))


def _field_refs(items):
    return [{"task_id": item["task_id"], "path": field["path"]}
            for item in items for field in item["fields"]]


def _canonical_paths(selected, task_id, paths):
    card = next((card for card in visible_cards(selected["payload"])
                 if card.get("task_id") == task_id), None)
    if card is None or not isinstance(paths, list):
        return None
    advertised = card.get("readable_fields", ())
    output = []
    for path in paths:
        if not isinstance(path, list):
            return None
        # Backward-compatible display wrapper, accepted only if it appeared
        # on this exact card and the canonical path is actually advertised.
        if path and path[0] in {"result_preview", "exact_result"}:
            if path[0] not in card:
                return None
            path = path[1:]
        if path not in advertised:
            return None
        output.append(path)
    return output


def history_turn(session, policy, query, client, *, inline_max=256):
    """Two-call maximum, with a bounded exact-evidence union for final answer."""
    selected = select_context43(session, query, policy, inline_max=inline_max)
    visible = exact_visible(session, selected)
    first_messages = [
        {"role": "system", "content": (
            "你是研究用途 EEG 历史分析助手，只能依据可见真实结果回答。可直接 answer，"
            "也可一次提交最多四项 read_full/read_fields 或 clarify。任务卡 readable_fields "
            "是相对 TaskEntry.result 的真实字段路径，字段索引不是数值。多对象读取时，"
            "每项 scope 用 record、kind、condition、channel、window、version 明确绑定"
            "该对象；所声明范围必须来自用户请求且与任务一致。不能猜数值、诊断或混同"
            "连续时间与事件相对时间；绝对功率单位 V²，幅值 V。")},
        {"role": "user", "content": json.dumps({"request": query,
                                                 "memory": selected["payload"]},
                                                ensure_ascii=False, allow_nan=False)},
    ]
    first = client.complete(first_messages, ACTION_TOOL,
                            tool_choice={"type": "function", "function": {
                                "name": "submit_evidence_action"}})
    base = {"selection": selected, "stored_task_ids": [entry.task_id for entry in session.entries],
            "first_visible": _field_refs(visible), "reads": [],
            "read_success": [], "final_visible": _field_refs(visible),
            "handoff_ms": 0.0, "handoff_bytes": 0}
    try:
        calls = first.get("tool_calls") or []
        if not 1 <= len(calls) <= 4 or any(
                call.get("function", {}).get("name") != "submit_evidence_action"
                for call in calls):
            raise ValueError("Invalid evidence call")
        actions = [json.loads(call["function"]["arguments"]) for call in calls]
        if len(actions) > 1 and any(action.get("operation") not in
                                    {"read_full", "read_fields"} for action in actions):
            raise ValueError("Mixed evidence actions")
    except (ValueError, KeyError, TypeError):
        return {**base, "status": "invalid_action", "actions": [], "answer": None}
    first_action = actions[0]
    if first_action.get("operation") == "answer":
        answer = first_action.get("answer")
        return {**base, "status": "answered" if isinstance(answer, str) and answer.strip()
                else "invalid_answer", "actions": actions, "answer": answer}
    if first_action.get("operation") == "clarify":
        return {**base, "status": "clarification_required", "actions": actions,
                "answer": first_action.get("question")}

    raw_reads = []
    valid_reads = []
    for action in actions:
        task_id = action.get("task_id")
        entry = next((entry for entry in session.entries if entry.task_id == task_id), None)
        if entry is None:
            raw_reads.append({"status": "clarification_required", "code": "TASK_NOT_FOUND",
                              "task_id": task_id})
            continue
        bound, reason = bind_read_scope(session, entry, query, action.get("scope"))
        if reason:
            raw_reads.append({"status": "clarification_required", "code": reason,
                              "task_id": task_id})
            continue
        if action.get("operation") == "read_full":
            result = session.read_task(task_id, bound)
        elif action.get("operation") == "read_fields":
            paths = _canonical_paths(selected, task_id, action.get("field_paths"))
            result = (session.read_task_fields(task_id, paths, bound) if paths else
                      {"status": "invalid_field", "code": "FIELD_NOT_ADVERTISED",
                       "task_id": task_id})
        else:
            result = {"status": "invalid_action", "code": "UNKNOWN_READ",
                      "task_id": task_id}
        raw_reads.append(result)
        if result.get("status") in {"read", "read_fields"}:
            try:
                valid_reads.append(normalized_read(session, result))
            except (KeyError, IndexError, TypeError, ValueError):
                raw_reads[-1] = {"status": "invalid_evidence", "code": "READ_PROVENANCE_ERROR",
                                 "task_id": task_id}
    try:
        handoff, assembly_ms = merge_evidence(visible, valid_reads)
    except ValueError:
        return {**base, "status": "invalid_evidence", "actions": actions,
                "reads": raw_reads, "answer": None, "code": "EVIDENCE_CONFLICT"}
    if handoff["status"] != "ok":
        return {**base, "status": "clarification_required", "actions": actions,
                "reads": raw_reads, "answer": "证据范围超过本轮安全交接上限，请缩小查询。",
                "code": handoff["code"]}
    if not handoff["items"]:
        return {**base, "status": "clarification_required", "actions": actions,
                "reads": raw_reads, "answer": "未能读到有效证据，请澄清目标或范围。"}
    failures = [{"task_id": item.get("task_id"), "code": item.get("code"),
                 "status": item.get("status")}
                for item in raw_reads if item.get("status") not in {"read", "read_fields"}]
    final_payload = {"request": query, "evidence": handoff["items"],
                     "failed_reads": failures}
    second_messages = [
        {"role": "system", "content": (
            "只根据 evidence 中明确的真实字段值回答当前请求。每项标明记录、来源、"
            "科学范围、参数版本与单位；first_visible 表示首次可见，不得说成刚读回。"
            "failed_reads 和字段索引不提供数值；缺项只能部分回答并注明缺口，"
            "不得把部分完成说成完整完成，不能编造或诊断。")},
        {"role": "user", "content": json.dumps(final_payload, ensure_ascii=False,
                                                allow_nan=False)},
    ]
    second = client.complete(second_messages, [])
    answer = second.get("content") if isinstance(second, dict) else None
    return {**base, "status": "answered" if isinstance(answer, str) and answer.strip()
            else "invalid_answer", "actions": actions, "answer": answer,
            "reads": raw_reads, "read_success": _field_refs(valid_reads),
            "final_visible": _field_refs(handoff["items"]),
            "handoff_ms": round(assembly_ms, 6),
            "handoff_bytes": len(_encoded(final_payload)),
            "failed_reads": failures}


def _field_present(refs, task_id, field):
    return any(item["task_id"] == task_id and item["path"] == field for item in refs)


def _attributed_value(answer, value, step, peers):
    """Conservative scope binding for a mixed-task numeric answer screen."""
    records = {item["record"] for item in peers}
    anchors = "|".join(re.escape(record) for record in sorted(records, key=len,
                                                                reverse=True))
    clauses = []
    # A numbered heading and its following bullet fields form one attribution
    # block; a Markdown table row remains its own block. Do not concatenate
    # distinct records across blank paragraphs or semicolon-separated clauses.
    blocks = []
    for paragraph in re.split(r"\n\s*\n", answer):
        if "|" in paragraph and any(line.lstrip().startswith("|")
                                   for line in paragraph.splitlines()):
            blocks.extend(paragraph.splitlines())
        else:
            blocks.append(paragraph)
    split_before_record = rf"[；;。]\s*(?=(?:记录\s*)?(?:{anchors})(?![A-Za-z0-9]))"
    for sentence in (part for block in blocks for part in re.split(split_before_record, block)):
        boundary = rf"[,，、]\s*(?=(?:记录\s*)?(?:{anchors})(?![A-Za-z0-9]))"
        clauses.extend(part.strip() for part in re.split(boundary, sentence)
                       if part.strip())
    same_record = [item for item in peers if item["record"] == step["record"]]
    params = step["parameters"]
    start = params.get("start", params.get("tmin"))
    end = params.get("end", params.get("tmax"))
    need_window = len({(item["parameters"].get("start"),
                        item["parameters"].get("end"),
                        item["parameters"].get("tmin"),
                        item["parameters"].get("tmax")) for item in same_record}) > 1
    need_scope = len({item["capability"] in {"epoch_summary", "event_bandpower"}
                      for item in same_record}) > 1
    event = step["capability"] in {"epoch_summary", "event_bandpower"}
    labels = {tuple(item["parameters"].get("labels", ()))
              for item in peers if item["parameters"].get("labels")}
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
            heading = clause.splitlines()[0]
            if re.search(r"连续|continuous", heading, re.I):
                clause_event = False
            elif re.search(r"事件|试次|epoch|event", heading, re.I):
                clause_event = True
            else:
                clause_event = bool(re.search(r"事件|试次|epoch|event", clause, re.I))
            if event != clause_event:
                continue
        if event and len(labels) > 1 and not any(
                label in clause for label in params.get("labels", ())):
            continue
        capability = step["capability"]
        if capability == "amplitude" and not re.search(r"幅值|RMS|振幅", clause, re.I):
            continue
        if capability == "epoch_summary" and not re.search(r"试次|epoch|计数", clause, re.I):
            continue
        if capability in {"psd", "event_bandpower"} and not re.search(
                r"alpha|功率|频带", clause, re.I):
            continue
        return True
    return False


def score_history(session, turn, observed, keys, turns_by_key):
    """Support is judged from actual last-call inputs, not hidden store union."""
    answer = observed.get("answer") or ""
    peers = [turns_by_key[target["key"]] for target in turn["targets"]]
    checks = []
    for target in turn["targets"]:
        step = turns_by_key[target["key"]]
        entry = keys.get(target["key"])
        oracle = [independent_oracle(session.records[step["record"]], step, field)
                  for field in target["fields"]]
        stored = bool(entry and _actual_matches_oracle(entry, step, session))
        first = bool(entry and all(_field_present(observed.get("first_visible", ()),
                                              entry.task_id, field)
                                   for field in target["fields"]))
        read = bool(entry and all(_field_present(observed.get("read_success", ()),
                                             entry.task_id, field)
                                  for field in target["fields"]))
        final = bool(entry and all(_field_present(observed.get("final_visible", ()),
                                              entry.task_id, field)
                                   for field in target["fields"]))
        numeric = all(_number_in_answer(answer, value) for value in oracle)
        attributed = all(_attributed_value(answer, value, step, peers)
                         for value in oracle)
        checks.append({"key": target["key"],
                       "task_id": entry.task_id if entry else None,
                       "oracle_values": oracle, "stored_valid": stored,
                       "first_visible": first, "read_success": read,
                       "final_visible": final, "numeric_screen": numeric,
                       "attribution_screen": attributed})
    capabilities = {turns_by_key[target["key"]]["capability"] for target in turn["targets"]}
    positive = re.sub(r"(?:非|不是|并非|不等于|not)\s*V²(?:/Hz)?", "", answer,
                      flags=re.IGNORECASE)
    units_ok = ("V²" in positive and "V²/Hz" not in positive if
                capabilities & {"psd", "event_bandpower"} else True)
    units_ok &= (bool(re.search(r"V(?!²|/Hz)", positive)) if "amplitude" in capabilities
                 else True)
    units_ok &= ("次" in positive or "个" in positive if "epoch_summary" in capabilities
                 else True)
    complete = bool(observed.get("status") == "answered" and units_ok and checks and
                    all(all(check[key] for key in (
                        "stored_valid", "final_visible", "numeric_screen",
                        "attribution_screen")) for check in checks))
    covered = [check for check in checks if check["stored_valid"] and
               check["final_visible"] and check["numeric_screen"] and
               check["attribution_screen"]]
    category = ("complete_screen" if complete else
                "partial_answer" if observed.get("status") == "answered" and covered else
                "clarification" if observed.get("status") == "clarification_required" else
                "unsupported_or_wrong_answer")
    actions = observed.get("actions") or []
    protocol = bool(observed.get("status") == "answered" and actions and
                    (actions[0].get("operation") == "answer" or
                     any(item.get("operation") in {"read_full", "read_fields"}
                         for item in actions)))
    return {"science_valid_screen": complete, "protocol_action_valid": protocol,
            "category": category, "target_checks": checks, "unit_screen": units_ok,
            "requires_manual_science_review": True}


def _session(script):
    from .task_memory_issue42 import _session as make_session
    return make_session(script)


def offline_preflight():
    return old_preflight({"workflows": load_spec()["workflows"]})


def _save(path, phase, rows, client):
    path.write_text(json.dumps({"phase": phase, "synthetic_only": True,
                                "spec_sha256": spec_sha(),
                                "requested_model": getattr(client, "model", None),
                                "ledger": ledger_totals(LEDGER), "rows": rows},
                               ensure_ascii=False, allow_nan=False, indent=2) + "\n",
                    encoding="utf-8")


def _admit_unit(unit_id, spec, *, reserve_calls, reserve_tokens):
    if any(row.get("event") == "reserved" and
           row.get("context", {}).get("unit_id", "").startswith(unit_id)
           for row in _rows(LEDGER)):
        raise StageBudgetExhausted("Unit already attempted; preserve first responses")
    totals = ledger_totals(LEDGER)
    if (totals["attempts"] + reserve_calls > spec["max_external_completions"] or
            totals["charged_tokens"] + reserve_tokens > spec["max_external_tokens"]):
        raise StageBudgetExhausted("Insufficient stage budget for a complete paired unit")


def run_phase(phase):
    if phase not in {"development", "confirmation"}:
        raise ValueError("Unknown phase")
    spec = load_spec()
    offline_preflight()
    PRIVATE.mkdir(parents=True, exist_ok=True)
    path = PRIVATE / f"{phase}_{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}.json"
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
        _save(path, phase, rows, client)
    if phase == "development":
        script = next(item for item in old_spec()["workflows"] if item["id"] == "C-mixed")
        # One already-seen same-history question; old/new paths remain explicit.
        _admit_unit("development:C-mixed", spec, reserve_calls=8, reserve_tokens=36000)
        for handler, scorer, name in ((old_history_turn, old_score_history, "old"),
                                      (history_turn, score_history, "repaired")):
            index = 3
            for policy in ("S", "HC"):
                client.set_context(phase=phase, unit_id=f"{name}:{script['id']}:{policy}")
                row = run_same_history(script, index, policy, client,
                                       history_handler=handler,
                                       history_scorer=scorer,
                                       mode=f"development:C-mixed:{name}")
                row["implementation"] = name
                save(row)
    else:
        for script in spec["workflows"]:
            _admit_unit(f"confirmation:{script['id']}", spec,
                        reserve_calls=3 * (sum(item["kind"] == "analysis"
                                               for item in script["turns"]) + 2),
                        reserve_tokens=60000 if script["id"] == "N-continuous" else 75000)
            arms = (["S", "HC", "F"] if script["id"] == "N-continuous"
                    else ["HC", "F", "S"])
            for policy in arms:
                client.set_context(phase=phase,
                                   unit_id=f"{script['id']}:{policy}")
                run_workflow(script, policy, client, mode=phase, save=save,
                             history_handler=history_turn,
                             history_scorer=score_history)
    _save(path, phase, rows, client)
    return path, rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--ledger-status", action="store_true")
    parser.add_argument("--phase", choices=("development", "confirmation"))
    parser.add_argument("--enable-paid-issue43", action="store_true")
    args = parser.parse_args(argv)
    if args.offline:
        print(json.dumps({"spec_sha256": spec_sha(), "preflight": offline_preflight()},
                         ensure_ascii=False))
        return
    if args.ledger_status:
        print(json.dumps(ledger_totals(LEDGER), ensure_ascii=False))
        return
    if not args.enable_paid_issue43 or not args.phase:
        parser.error("Paid phase requires --enable-paid-issue43 and --phase")
    path, rows = run_phase(args.phase)
    print(json.dumps({"output": str(path.relative_to(PROJECT_ROOT)),
                      "rows": len(rows), "ledger": ledger_totals(LEDGER)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
