"""Frozen synthetic multi-turn EEG memory replay and bounded real-model CLI."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from ..llm import OpenAICompatibleClient
from .integrated_method.v2_validation import JournaledBudgetClient, PRIVATE_ROOT
from .task_memory import (MultiTurnEEGSession, PROJECT_ROOT, live_turn,
                          load_protocol, replay_policies)


def _destination(label):
    root = PRIVATE_ROOT / "point1_task_memory"
    root.mkdir(parents=True, exist_ok=True)
    name = f"{label}_{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}.json"
    result = root / name
    if result.exists():
        raise FileExistsError("Append-only experiment output required")
    return result


def _save(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                               allow_nan=False) + "\n", encoding="utf-8")


def run_replay(*, session_ids=None, policies=("F", "S", "G", "E", "E-no-scope")):
    protocol = load_protocol()
    path = _destination("replay")
    records = []
    for script in protocol["sessions"]:
        if session_ids is not None and script["id"] not in session_ids:
            continue
        start = time.perf_counter()
        for entry in replay_policies(script, policies):
            entry["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 3)
            records.append(entry)
            _save(path, {"mode": "same_history_replay", "real_llm": False,
                         "synthetic_only": True, "records": records})
    return path, records


def score_live_turn(script, index, observed):
    """Gold is consulted only after the model and shared execution have finished."""
    gold = script["turns"][index]
    action, outcome = observed["action"], observed["outcome"]
    actual_op = action.get("operation")
    correct = actual_op == gold["op"]
    if gold["op"] in {"analyze", "revise"}:
        correct = (correct and action.get("record") == gold["record"]
                   and action.get("capability") == gold["capability"]
                   and action.get("parameters") == gold["parameters"]
                   and outcome["status"] == "completed")
        if gold["op"] == "revise":
            correct = correct and action.get("parent_task_id") == f"{script['id']}-t{gold['parent']}"
    elif gold["op"] == "switch":
        correct = correct and outcome.get("record") == gold["record"]
    elif gold["op"] == "history":
        correct = correct and outcome.get("task_id") == f"{script['id']}-t{gold['target']}"
    else:
        correct = correct and outcome["status"] == "clarification_required"
    return {"correct": bool(correct), "expected_operation": gold["op"],
            "actual_operation": actual_op,
            "target_match": (outcome.get("task_id") == f"{script['id']}-t{gold['target']}")
            if gold["op"] == "history" else None}


def run_live(*, session_ids=("M1", "M6"), policies=("G", "E"),
             max_requests=96, max_total_tokens=300000,
             deliver_answer=False):
    protocol = load_protocol()
    path = _destination("real")
    raw = OpenAICompatibleClient.from_env()
    raw.max_retries = 0
    raw.max_tokens = min(raw.max_tokens, 1200)
    client = JournaledBudgetClient(raw, path.with_suffix(".responses.jsonl"),
                                   max_requests=max_requests,
                                   max_total_tokens=max_total_tokens)
    observations = []
    for script in protocol["sessions"]:
        if script["id"] not in session_ids:
            continue
        for policy in policies:
            session = MultiTurnEEGSession(script["id"])
            for index, turn in enumerate(script["turns"]):
                before = client.request_count
                started = time.perf_counter()
                try:
                    item = live_turn(session, policy, turn["text"], client,
                                     deliver_answer=deliver_answer)
                    item["score"] = score_live_turn(script, index, item)
                except Exception as exc:
                    item = {"request": turn["text"], "memory_policy": policy,
                            "outcome": {"status": "llm_error", "error_type": type(exc).__name__},
                            "score": {"correct": False}}
                item.update({"session_id": script["id"], "turn_index": index + 1,
                             "request_indices": [before + 1, client.request_count],
                             "elapsed_ms": round((time.perf_counter() - started) * 1000, 3)})
                observations.append(item)
                _save(path, {"mode": "real_closed_loop", "synthetic_only": True,
                             "final_answer_enabled": deliver_answer,
                             "requested_model": client.model,
                             "response_models": list(raw.response_models),
                             "request_count": client.request_count,
                             "usage": dict(client.total_usage),
                             "records": observations})
                if item["outcome"]["status"] == "llm_error":
                    return path, observations, client
    return path, observations, client


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("replay", "real"), required=True)
    parser.add_argument("--sessions", nargs="+")
    parser.add_argument("--policies", nargs="+")
    parser.add_argument("--max-requests", type=int, default=96)
    parser.add_argument("--max-total-tokens", type=int, default=300000)
    parser.add_argument("--final-answer", action="store_true",
                        help="Request a second, grounded natural-language delivery per turn")
    args = parser.parse_args(argv)
    if args.mode == "replay":
        path, records = run_replay(session_ids=args.sessions,
                                   policies=args.policies or ("F", "S", "G", "E", "E-no-scope"))
        print(json.dumps({"output": str(path.relative_to(PROJECT_ROOT)),
                          "sessions": len(records),
                          "history_hits": sum(item.get("hit") is True
                                              for row in records for item in row["observations"]),
                          "real_llm": False}, ensure_ascii=False))
    else:
        path, records, client = run_live(
            session_ids=args.sessions or ("M1", "M6"),
            policies=args.policies or ("G", "E"),
            max_requests=args.max_requests, max_total_tokens=args.max_total_tokens,
            deliver_answer=args.final_answer)
        print(json.dumps({"output": str(path.relative_to(PROJECT_ROOT)),
                          "turns": len(records),
                          "correct": sum(item["score"]["correct"] for item in records),
                          "request_count": client.request_count,
                          "total_tokens": client.total_usage.get("total_tokens")},
                         ensure_ascii=False))


if __name__ == "__main__":
    main()
