"""Read-only Issue48 cost, scientific-output and memory-use audit.

No API call, Agent invocation or gold feedback. This produces a minimal public
synthetic excerpt from private preserved logs. Task coverage/final natural
language accuracy require separate explicit review; counts are not a score.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

import numpy as np

from .task_memory_v2 import independent_oracle
from .working_memory_issue48 import ROOT, SPEC, records_for
from ..working_memory import NUMERIC_TOOLS


def read_json(path):
    return json.loads(path.read_text(encoding="utf8"))


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf8").splitlines() if line.strip()] if path.exists() else []


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def payload_for(request):
    for message in request.get("messages", []):
        try:
            payload = json.loads(message.get("content", ""))
        except (ValueError, TypeError):
            continue
        if isinstance(payload, dict) and "current_request" in payload:
            return payload
    return {}


def artifact_ids(value):
    """Find explicit artifact references, not guessed content-equivalent IDs."""
    found = set()
    if isinstance(value, dict):
        if isinstance(value.get("artifact_id"), str):
            found.add(value["artifact_id"])
        for item in value.values():
            found.update(artifact_ids(item))
    elif isinstance(value, list):
        for item in value:
            found.update(artifact_ids(item))
    return found


def _number_checks(observation, records):
    name, data, params = observation["request"]["name"], observation["result"]["data"], observation["scope"]
    if name in {"amplitude", "psd"}:
        paths = [[channel, field] for channel in params["channels"]
                 for field in (["rms"] if name == "amplitude" else list(data[channel]))]
    elif name == "event_bandpower":
        paths = [["conditions", label, "epoch_count"] for label in data["conditions"]]
        paths += [["conditions", label, "channels", channel, band]
                  for label, condition in data["conditions"].items()
                  for channel, powers in condition["channels"].items() for band in powers]
        paths += [["frequency_resolution_hz"]]
    elif name in {"epoch_summary", "create_epochs"}:
        paths = [["valid_epoch_count"]]
    else:
        return []
    record = records[observation["record"]]
    rows = []
    for path in paths:
        actual = data
        for key in path:
            actual = actual[key]
        scope = dict(params)
        if name == "event_bandpower" and path[0] == "conditions":
            scope["labels"] = [path[1]]
        if name in {"create_epochs", "epoch_summary"} or path[-1] == "epoch_count":
            expected = independent_oracle(record, {"capability": "epoch_summary", "parameters": scope}, ["valid_epoch_count"])
        elif path == ["frequency_resolution_hz"]:
            length = round((params["tmax"]-params["tmin"])*record.sfreq)
            expected = record.sfreq / min(length, round(record.sfreq))
        else:
            expected = independent_oracle(record, {"capability": name, "parameters": scope}, path)
        actual = float(actual)
        tol = .005 if name in {"amplitude", "psd"} else 1e-6
        source_valid = observation["source"] == record.source
        rows.append({"result_id": observation["result_id"], "tool": name,
                     "record": observation["record"], "source": observation["source"], "scope": scope,
                     "field": path, "actual": actual, "oracle": expected,
                     "absolute_error": abs(actual-expected), "rtol": tol, "atol": 5e-13,
                     "numeric_valid": bool(np.isclose(actual, expected, rtol=tol, atol=5e-13)),
                     "source_valid": source_valid})
    return rows


def _goal_excerpt(goal):
    fields = ("subgoal_id", "title", "record", "created_turn", "status", "deliveries", "criteria",
              "dependencies", "result_ids", "reused_results", "admission_issues", "contract_revisions",
              "delivery_check", "unresolved")
    out = {key: goal[key] for key in fields if key in goal}
    out["result_versions"] = [{key: result.get(key) for key in (
        "task_id", "record", "capability", "parameters", "revision_of", "superseded_by", "binding_valid", "artifact_id")}
        for result in goal.get("results", [])]
    return out


def audit_run(directory):
    manifest = read_json(directory/"manifest.json")
    spec = read_json(directory/"protocol.json")
    current_spec = read_json(SPEC)
    if manifest["phase"] == "confirmation" and spec["data_definition"] != current_spec["data_definition"]:
        raise ValueError("Cannot silently reconstruct changed confirmation data")
    records = records_for("original" if manifest["phase"] == "development" else "confirmation")
    requests, responses = read_rows(directory/"requests.jsonl"), read_rows(directory/"responses.jsonl")
    call_map = {}
    for index, response in enumerate(responses, 1):
        assistant = response.get("raw_assistant_message") or {}
        for call in assistant.get("tool_calls") or []:
            function = call.get("function", {})
            args = function.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {"invalid_json": args}
            call_map[call["id"]] = {"request_index": index, "name": function.get("name"), "arguments": args}
    visibility, component_bytes = [], Counter()
    for index, request in enumerate(requests, 1):
        payload = payload_for(request)
        restored = payload.get("restored_trajectories", [])
        active = payload.get("active_subgoal") or {}
        component_bytes.update(request.get("components", {}).get("parts", {}))
        visibility.append({"request_index": index, "request_id": request.get("request_id"),
            "turn": request.get("context", {}).get("turn"), "active_subgoal": active.get("subgoal_id"),
            "active_progress": active.get("delivery_check"),
            "visible_exact_results": [{k: e.get(k) for k in ("task_id", "record", "parameters", "revision_of", "created_turn", "acquired_this_turn")}
                                      for e in payload.get("exact_evidence", [])],
            "archived_goal_ids": [c.get("subgoal_id") for c in payload.get("archived_summaries", [])],
            "restored_goal_ids": [(x.get("subgoal") or {}).get("subgoal_id") for x in restored],
            "restored_artifact_ids": sorted(artifact_ids(restored)),
            "component_bytes": request.get("components", {})})
    turns, action_rows, numeric, errors = [], [], [], []
    for path in sorted(directory.glob("turn-*.json"), key=lambda p: int(p.stem.split("-")[-1])):
        result = read_json(path)
        number = int(path.stem.split("-")[-1])
        actions = []
        for action_index, action in enumerate(result.get("tool_results", []), 1):
            link = call_map.get(action["request_id"], {})
            data = action.get("data") or {}
            row = {"turn": number, "action_index": action_index, "call_id": action["request_id"],
                   "request_index": link.get("request_index"), "tool": action["tool_name"],
                   "arguments": link.get("arguments"), "success": action["success"],
                   "status": data.get("status"), "error": action.get("error"),
                   "progress": data.get("progress", data.get("delivery_check")),
                   "subgoal_id": data.get("subgoal_id"), "result_id": data.get("task_id")}
            for key in ("contract", "summary"):
                if isinstance(data.get(key), dict):
                    row[key] = _goal_excerpt(data[key])
            observation = data.get("observation")
            if observation:
                row["observation"] = observation
                if observation["result"]["success"]:
                    try:
                        numeric.extend(dict(check, turn=number, action_index=action_index)
                                       for check in _number_checks(observation, records))
                    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
                        errors.append({"turn": number, "action_index": action_index,
                                       "type": type(exc).__name__, "message": str(exc)})
            if action["tool_name"] == "restore_subgoal" and action["success"]:
                row["restored_goal_id"] = (data.get("subgoal") or {}).get("subgoal_id")
                row["restored_observations"] = data.get("action_observations", [])
                row["restored_artifact_ids"] = sorted(artifact_ids(data.get("action_observations", [])))
            if action["tool_name"] == "read_evidence" and action["success"]:
                row["read_evidence"] = data.get("evidence")
            actions.append(row)
            action_rows.append(row)
        turns.append({"turn": number, "request": spec["development"]["requests"][number-1] if manifest["phase"] == "development"
                          else spec["confirmation"][manifest["case"]]["requests"][number-1],
                      "stop_reason": result["stop_reason"], "rounds": result["rounds"], "tool_calls": result["tool_calls"],
                      "final_answer": result["final_answer"], "actions": actions,
                      "goals": [_goal_excerpt(g) for g in (result.get("working_memory") or {}).get("subgoals", [])],
                      "lifecycle_events": (result.get("working_memory") or {}).get("events", [])})
    restore_chains = []
    for action in action_rows:
        if action["tool"] != "restore_subgoal" or not action["success"]:
            continue
        index = action["request_index"]
        visible = [v for v in visibility if index is not None and v["request_index"] > index
                   and action.get("restored_goal_id") in v["restored_goal_ids"]]
        uses = [a for a in action_rows if a["success"] and a.get("observation")
                and a["request_index"] is not None and any(v["request_index"] <= a["request_index"] for v in visible)
                and (a["arguments"] or {}).get("artifact_id") in action["restored_artifact_ids"]]
        restore_chains.append({"restore_turn": action["turn"], "restore_request_index": index,
            "goal_id": action.get("restored_goal_id"), "artifact_ids": action["restored_artifact_ids"],
            "visible_in_followup_requests": [v["request_index"] for v in visible],
            "subsequent_real_artifact_uses": [{k: a[k] for k in ("turn", "request_index", "tool", "arguments")} for a in uses],
            "mechanism_use_proven": bool(visible and uses),
            "process_statement_use": "Final prose needs manual comparison to restored observations; not automatically credited"})
    return {"run": directory.name, "manifest": manifest,
            "original_protocol_sha256": hashlib.sha256((directory/"protocol.json").read_bytes()).hexdigest(),
            "turns": turns, "request_visibility": visibility, "input_component_bytes": dict(component_bytes),
            "numeric_checks": numeric, "audit_errors": errors, "restore_chains": restore_chains,
            "action_counts": {"numerical_attempts": sum(a["tool"] in NUMERIC_TOOLS for a in action_rows),
                              "numerical_executed": sum(bool(a.get("observation")) for a in action_rows),
                              "numerical_success": sum(bool(a.get("observation")) and a["observation"]["result"]["success"] for a in action_rows),
                              "control_attempts": sum(a["tool"] not in NUMERIC_TOOLS for a in action_rows),
                              "rejected": sum(not a["success"] for a in action_rows),
                              "unchanged": sum(a["status"] == "unchanged" for a in action_rows),
                              "successful_exact_reads": sum(a["tool"] == "read_evidence" and a["success"] for a in action_rows),
                              "successful_result_reuse": sum(a["tool"] == "reuse_result" and a["status"] == "reused" for a in action_rows)},
            "driver_events": read_rows(directory/"driver_events.jsonl"),
            "log_hashes": {p.name: sha(p) for p in sorted(directory.glob("*.json*"))}}


def build_audit(root=ROOT):
    root = Path(root)
    ledger = read_rows(root/"budget.jsonl")
    starts = {r["request_id"]: r for r in ledger if r["event"] == "reserved"}
    ends = {r["request_id"]: r for r in ledger if r["event"] in {"received", "failed"}}
    costs = defaultdict(lambda: {"attempts": 0, "received": 0, "failed": 0, "unsettled": 0,
        "charged_tokens": 0, "api_input_tokens": 0, "api_output_tokens": 0,
        "cache_hit_tokens": 0, "cache_miss_tokens": 0, "duration_seconds": 0.0})
    for ident, start in starts.items():
        end = ends.get(ident, {})
        row = costs[start["context"]["run_id"]]
        row["attempts"] += 1
        row["received"] += end.get("event") == "received"
        row["failed"] += end.get("event") == "failed"
        row["unsettled"] += not bool(end)
        row["charged_tokens"] += end["total_tokens"] if end.get("total_tokens") is not None else start["reserved_tokens"]
        usage = end.get("usage") or {}
        for k, v in (("api_input_tokens", "prompt_tokens"), ("api_output_tokens", "completion_tokens"),
                     ("cache_hit_tokens", "prompt_cache_hit_tokens"), ("cache_miss_tokens", "prompt_cache_miss_tokens")):
            row[k] += usage.get(v, 0)
        row["duration_seconds"] += end.get("duration_seconds", 0)
    runs = [audit_run(p.parent) for p in sorted(root.glob("*/manifest.json"))]
    return {"stage": "issue48", "kind": "posthoc_synthetic_only_audit_not_automated_task_score",
            "protocol_sha256_current": sha(SPEC), "ledger_sha256": sha(root/"budget.jsonl"),
            "costs_by_run": dict(costs),
            "cost_total": {k: sum(v[k] for v in costs.values()) for k in next(iter(costs.values()), {})},
            "reported_models": dict(Counter(r.get("response_model_reported") for r in ends.values() if r.get("event") == "received")),
            "budget_blocks": [r for r in ledger if r["event"] == "blocked_before_network"],
            "runs": runs,
            "interpretation": "Numerical agreement and mechanism traces do not replace original request coverage, scientific authorization or final-answer review. Actual costs include failed and unfinished sessions; bytes are not API tokens."}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    audit = build_audit(args.root)
    with args.output.open("x", encoding="utf8") as f:
        json.dump(audit, f, ensure_ascii=False, allow_nan=False, indent=2)
    checks = [c for run in audit["runs"] for c in run["numeric_checks"]]
    errors = [e for run in audit["runs"] for e in run["audit_errors"]]
    print(json.dumps({"costs": audit["cost_total"], "runs": len(audit["runs"]), "numeric_fields": len(checks),
                      "numeric_valid": all(c["numeric_valid"] and c["source_valid"] for c in checks),
                      "audit_errors": len(errors)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
