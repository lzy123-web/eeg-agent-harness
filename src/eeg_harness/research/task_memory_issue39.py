"""Bounded synthetic-only real-model phases for Issue #39.

The entire stage shares one append-only private ledger. This executable entry
does not load EDF, weights or private participant data.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from ..llm import OpenAICompatibleClient
from .integrated_method.v2_validation import JournaledBudgetClient, PRIVATE_ROOT
from .task_memory_eval import PROTOCOL_V2, run_paired_v3
from .task_memory_issue39_budget import Issue39BudgetClient, ledger_totals
from .task_memory_v2 import protocol_records
from .task_memory_v3 import EpisodeMemorySession, live_turn_v3
from .task_memory import PROJECT_ROOT


STAGE_PROTOCOL = PROJECT_ROOT / "config" / "point1_task_memory_issue39.json"
PRIVATE = PRIVATE_ROOT / "point1_task_memory" / "issue39"
LEDGER = PRIVATE / "budget.jsonl"
PHASE_LIMITS = {"smoke": 8, "initial": 48, "revision": 32,
                "confirmation": 56, "reserve": 16}


def protocol_hash():
    return hashlib.sha256(STAGE_PROTOCOL.read_bytes()).hexdigest()


def load_stage_protocol():
    return json.loads(STAGE_PROTOCOL.read_text(encoding="utf-8"))


def _private_output(phase):
    PRIVATE.mkdir(parents=True, exist_ok=True)
    path = PRIVATE / f"{phase}_{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}.json"
    if path.exists():
        raise FileExistsError("Issue39 results must be append-only by run")
    return path


def _save(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                               allow_nan=False) + "\n", encoding="utf-8")


def _smoke(client, save):
    """Small public-action check; requests only, never pass expected actions."""
    script = load_stage_protocol()["confirmation_sessions"][0]
    session = EpisodeMemorySession("I39-smoke", protocol_records(script))
    turns = (
        script["steps"][0]["text"],
        "请仅切换到 B 记录，暂时不要计算。",
        "请统计 B 的 rare 事件后 0 到 1 秒有效试次数。",
        "请把刚才 B 的 rare 试次窗口改为事件后 0 到 0.5 秒，保留旧结果。",
        "修改前 B 的 rare 事件后 0 到 1 秒，有效试次数是多少？",
    )
    rows = []
    for index, request in enumerate(turns, 1):
        client.set_context(session_id=session.session_id, policy="H",
                           turn_index=index, kind="smoke")
        try:
            item = live_turn_v3(session, "H", request, client,
                                deliver_answer=index == len(turns))
        except Exception as exc:
            item = {"request": request, "outcome": {"status": "llm_error",
                    "error_type": type(exc).__name__}}
        item["turn_index"] = index
        item["task_count"] = len(session.entries)
        item["lifecycle"] = list(session.lifecycle)
        rows.append(item)
        save(rows)
        if item["outcome"]["status"] == "llm_error":
            break
    return rows


def run_phase(phase, *, policies=None):
    spec = load_stage_protocol()
    path = _private_output(phase)
    raw = OpenAICompatibleClient.from_env()
    raw.max_retries = 0
    raw.max_tokens = min(raw.max_tokens, 1000)
    journal = JournaledBudgetClient(raw, path.with_suffix(".responses.jsonl"),
                                    max_requests=PHASE_LIMITS[phase],
                                    max_total_tokens=spec["max_external_tokens"])
    client = Issue39BudgetClient(journal, LEDGER,
                                 max_requests=spec["max_external_completions"],
                                 max_tokens=spec["max_external_tokens"],
                                 model_label=raw.model, phase=phase,
                                 phase_request_cap=PHASE_LIMITS[phase])

    def save(rows):
        _save(path, {"phase": phase, "synthetic_only": True,
                     "protocol_sha256": protocol_hash(),
                     "requested_model": raw.model,
                     "reported_models": list(raw.response_models),
                     "run_request_count": raw.request_count,
                     "run_usage": dict(raw.total_usage),
                     "stage_ledger": ledger_totals(LEDGER),
                     "records": rows})

    if phase == "smoke":
        rows = _smoke(client, save)
    else:
        if phase == "confirmation":
            scripts = spec["confirmation_sessions"]
            arms = policies or tuple(spec["policies"])
        else:
            original = json.loads(PROTOCOL_V2.read_text(encoding="utf-8"))
            scripts = [script for script in original["sessions"]
                       if script["id"] in spec["development_session_ids"]]
            arms = policies or (("H", "HE") if phase == "revision"
                                else tuple(spec["policies"]))
        rows = run_paired_v3({"sessions": scripts}, client, policies=arms,
                             deliver_answer=True, save=save)
    save(rows)
    return path, rows, ledger_totals(LEDGER)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=tuple(PHASE_LIMITS))
    parser.add_argument("--policies", nargs="+")
    parser.add_argument("--enable-paid-issue39", action="store_true")
    parser.add_argument("--ledger-status", action="store_true")
    args = parser.parse_args(argv)
    if args.ledger_status:
        print(json.dumps({"ledger": str(LEDGER.relative_to(PROJECT_ROOT)),
                          **ledger_totals(LEDGER)}, ensure_ascii=False))
        return
    if not args.enable_paid_issue39 or args.phase is None:
        parser.error("Paid phase needs --enable-paid-issue39 and --phase")
    path, rows, totals = run_phase(args.phase, policies=args.policies)
    print(json.dumps({"output": str(path.relative_to(PROJECT_ROOT)),
                      "turns": len(rows), "stage_ledger": totals}, ensure_ascii=False))


if __name__ == "__main__":
    main()
