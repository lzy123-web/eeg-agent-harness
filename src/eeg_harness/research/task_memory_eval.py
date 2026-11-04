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
from .task_memory_v2 import (protocol_records, replay_protocol_v2,
                             score_observed_history_turn)
from .task_memory_v3 import (EpisodeMemorySession, live_turn_v3,
                             replay_protocol_v3)


PROTOCOL_V2 = PROJECT_ROOT / "config" / "point1_task_memory_protocol_v2.json"


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


def run_replay_v2(*, session_ids=None,
                  policies=("F", "S", "G", "E", "E-no-science")):
    """Append-only offline replay of the separately frozen v2 protocol."""
    protocol = json.loads(PROTOCOL_V2.read_text(encoding="utf-8"))
    path = _destination("replay_v2")
    records = []
    for script in protocol["sessions"]:
        if session_ids is not None and script["id"] not in session_ids:
            continue
        records.extend(replay_protocol_v2(script, policies))
        _save(path, {"mode": "same_history_replay_v2", "real_llm": False,
                     "synthetic_only": True, "protocol_version": protocol["version"],
                     "records": records})
    return path, records


def run_replay_v3(*, session_ids=None, policies=("F", "S", "H", "HE"),
                  memory_variant="optimized"):
    """Append-only evaluation of the task-episode adapter, without API calls."""
    protocol = json.loads(PROTOCOL_V2.read_text(encoding="utf-8"))
    path = _destination("replay_v3")
    records = []
    for script in protocol["sessions"]:
        if session_ids is not None and script["id"] not in session_ids:
            continue
        records.extend(replay_protocol_v3(script, policies, variant=memory_variant))
        _save(path, {"mode": "task_episode_same_history_replay",
                     "real_llm": False, "synthetic_only": True,
                     "protocol_version": protocol["version"],
                     "memory_variant": memory_variant, "records": records})
    return path, records


def run_paired_v3(protocol, client, *, session_ids=None,
                  policies=("F", "S", "H", "HE"), deliver_answer=False,
                  save=None, memory_variant="optimized"):
    """Shared action interface; each arm builds only its own observed history."""
    observations = []
    for script in protocol["sessions"]:
        if session_ids is not None and script["id"] not in session_ids:
            continue
        for policy in policies:
            session = EpisodeMemorySession(script["id"], protocol_records(script))
            completed_ids = {}
            turns = [("analysis", item) for item in script["steps"]]
            turns += [("history", item) for item in script["queries"]]
            for index, (kind, expected) in enumerate(turns, 1):
                if hasattr(client, "set_context"):
                    client.set_context(session_id=script["id"], policy=policy,
                                       turn_index=index, kind=kind)
                before_requests = getattr(client, "request_count", None)
                before_tokens = getattr(client, "total_usage", {}).get("total_tokens", 0)
                started = time.perf_counter()
                try:
                    item = live_turn_v3(session, policy, expected["text"], client,
                                        deliver_answer=deliver_answer and kind == "history",
                                        variant=memory_variant)
                    if kind == "history":
                        score = score_observed_history_turn(session, script, expected, item)
                    else:
                        operation = "revise" if "revision_of" in expected else "analyze"
                        action, outcome = item["action"], item["outcome"]
                        parent_valid = ("revision_of" not in expected or
                                        action.get("parent_task_id") ==
                                        completed_ids.get(expected["revision_of"], object()))
                        operation_valid = (action.get("operation") == operation or
                                           operation == "analyze" and
                                           action.get("operation") == "switch_analyze")
                        valid = (operation_valid
                                 and outcome.get("record", action.get("record")) == expected["record"]
                                 and action.get("capability") == expected["capability"]
                                 and action.get("parameters") == expected["parameters"]
                                 and parent_valid and outcome.get("status") == "completed")
                        if valid:
                            category = "correct"
                        elif not operation_valid:
                            category = "common_action_selection_error"
                        elif outcome.get("status") != "completed":
                            category = "execution_error"
                        else:
                            category = "semantic_action_error"
                        score = {"valid": bool(valid), "category": category}
                        if valid:
                            completed_ids[expected["key"]] = outcome["task_id"]
                    item["score"] = score
                except Exception as exc:
                    item = {"request": expected["text"], "memory_policy": policy,
                            "outcome": {"status": "llm_error",
                                        "error_type": type(exc).__name__},
                            "score": {"valid": False, "category": "llm_error"}}
                item.update({"session_id": script["id"], "turn_index": index,
                             "kind": kind, "task_count": len(session.entries),
                             "lifecycle": list(session.lifecycle),
                             "evidence_reads": session.evidence_reads,
                             "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                             "llm_requests": (getattr(client, "request_count", 0)
                                              - before_requests if before_requests is not None
                                              else None),
                             "llm_tokens": (getattr(client, "total_usage", {}).get("total_tokens", 0)
                                            - before_tokens if before_tokens is not None
                                            else None)})
                observations.append(item)
                if save is not None:
                    save(observations)
                if item["outcome"]["status"] == "llm_error":
                    return observations
    return observations


def run_live_v3(*, session_ids=("N-medium",), policies=("F", "S", "H", "HE"),
                max_requests, max_total_tokens, deliver_answer=False,
                memory_variant="optimized"):
    """Future opt-in paid run; this stage executes no external model calls."""
    protocol = json.loads(PROTOCOL_V2.read_text(encoding="utf-8"))
    path = _destination("real_v3")
    raw = OpenAICompatibleClient.from_env()
    raw.max_retries = 0
    raw.max_tokens = min(raw.max_tokens, 1200)
    client = JournaledBudgetClient(raw, path.with_suffix(".responses.jsonl"),
                                   max_requests=max_requests,
                                   max_total_tokens=max_total_tokens)

    def save(observations):
        _save(path, {"mode": "task_episode_real_closed_loop",
                     "synthetic_only": True, "protocol_version": protocol["version"],
                     "requested_model": client.model,
                     "response_models": list(raw.response_models),
                     "memory_variant": memory_variant,
                     "request_count": client.request_count,
                     "usage": dict(client.total_usage), "records": observations})

    return path, run_paired_v3(protocol, client, session_ids=session_ids,
                               policies=policies, deliver_answer=deliver_answer,
                               save=save, memory_variant=memory_variant), client


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
    parser.add_argument("--mode", choices=("replay", "replay-v2", "replay-v3",
                                           "real", "real-v3"), required=True)
    parser.add_argument("--sessions", nargs="+")
    parser.add_argument("--policies", nargs="+")
    parser.add_argument("--memory-variant", choices=("original", "optimized"),
                        default="optimized")
    parser.add_argument("--max-requests", type=int, default=96)
    parser.add_argument("--max-total-tokens", type=int, default=300000)
    parser.add_argument("--final-answer", action="store_true",
                        help="Request a second, grounded natural-language delivery per turn")
    parser.add_argument("--enable-paid-v3", action="store_true",
                        help="Explicit future authorization gate for real-v3 only")
    parser.add_argument("--v3-max-requests", type=int,
                        help="Required explicit request cap for future real-v3 run")
    parser.add_argument("--v3-max-total-tokens", type=int,
                        help="Required explicit token cap for future real-v3 run")
    args = parser.parse_args(argv)
    if args.mode == "replay-v3":
        path, records = run_replay_v3(session_ids=args.sessions,
                                      policies=args.policies or ("F", "S", "H", "HE"),
                                      memory_variant=args.memory_variant)
        print(json.dumps({"output": str(path.relative_to(PROJECT_ROOT)),
                          "session_policy_pairs": len(records),
                          "queries": sum(len(row["queries"]) for row in records),
                          "real_llm": False}, ensure_ascii=False))
    elif args.mode == "replay-v2":
        path, records = run_replay_v2(session_ids=args.sessions,
                                      policies=args.policies or
                                      ("F", "S", "G", "E", "E-no-science"))
        print(json.dumps({"output": str(path.relative_to(PROJECT_ROOT)),
                          "session_policy_pairs": len(records),
                          "queries": sum(len(row["queries"]) for row in records),
                          "real_llm": False}, ensure_ascii=False))
    elif args.mode == "replay":
        path, records = run_replay(session_ids=args.sessions,
                                   policies=args.policies or ("F", "S", "G", "E", "E-no-scope"))
        print(json.dumps({"output": str(path.relative_to(PROJECT_ROOT)),
                          "sessions": len(records),
                          "history_hits": sum(item.get("hit") is True
                                              for row in records for item in row["observations"]),
                          "real_llm": False}, ensure_ascii=False))
    elif args.mode == "real-v3":
        if (not args.enable_paid_v3 or args.v3_max_requests is None
                or args.v3_max_total_tokens is None
                or args.v3_max_requests < 1 or args.v3_max_total_tokens < 1):
            parser.error("real-v3 requires --enable-paid-v3 and positive explicit budgets")
        path, records, client = run_live_v3(
            session_ids=args.sessions or ("N-medium",),
            policies=args.policies or ("F", "S", "H", "HE"),
            max_requests=args.v3_max_requests,
            max_total_tokens=args.v3_max_total_tokens,
            deliver_answer=args.final_answer,
            memory_variant=args.memory_variant)
        print(json.dumps({"output": str(path.relative_to(PROJECT_ROOT)),
                          "turns": len(records),
                          "correct": sum(item["score"]["valid"] for item in records),
                          "request_count": client.request_count,
                          "total_tokens": client.total_usage.get("total_tokens")},
                         ensure_ascii=False))
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
