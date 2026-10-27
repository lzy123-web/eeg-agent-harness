"""Read-only Issue51 scientific, exposure, architecture and cost audit.

This module never runs an Agent or contacts a service. It extracts synthetic
evidence from preserved actual logs. A completed stop status is not a scientific
success score; request completeness and final natural language require review.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

import numpy as np

from ..working_memory import NUMERIC_TOOLS
from .task_memory_evidence import scalar_paths
from .task_memory_v2 import independent_oracle
from .working_memory_issue49_audit import (_number_checks, read_json, read_rows,
    sha, payload_for, artifact_ids, _goal_excerpt)
from .working_memory_issue51 import ROOT, SPEC, records_for, requests_for, digest


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True).encode("utf8")


def _digest(value):
    return hashlib.sha256(_encoded(value)).hexdigest()


def _decoded_messages(request):
    """Read structured inputs actually sent, excluding assistant proposals."""
    for message in request.get("messages", []):
        if message.get("role") not in {"user", "tool"}:
            continue
        try:
            value = json.loads(message.get("content", ""))
        except (TypeError, ValueError):
            continue
        if isinstance(value, (dict, list)):
            yield value


def evidence_in_request(request):
    """Only actual scalar fields or successful results count as exact values.

    Locator IDs, readable_fields and failed tool results are never promoted to
    values. Full native transcripts and compact evidence use the same scanner.
    Returned facts stay local to audit computation; public visibility exposes
    paths and digests, with requested read fields checked individually.
    """
    facts, conflicts = {}, []
    def add(ident, path, value):
        key = json.dumps(path, ensure_ascii=False)
        prior = facts.setdefault(ident, {})
        if key in prior and _encoded(prior[key]["value"]) != _encoded(value):
            conflicts.append({"result_id": ident, "path": path})
        else:
            prior[key] = {"path": path, "value": value}
    def scan(value, inherited_failure=False):
        if isinstance(value, list):
            for item in value: scan(item, inherited_failure)
        elif isinstance(value, dict):
            failed = inherited_failure or value.get("success") is False
            ident = value.get("task_id") or value.get("result_id")
            if isinstance(ident, str) and not failed:
                for field in value.get("fields", []) if isinstance(value.get("fields", []), list) else []:
                    if isinstance(field, dict) and isinstance(field.get("path"), list) and "value" in field:
                        add(ident, field["path"], field["value"])
                result = value.get("result")
                if isinstance(result, dict) and result.get("success") is True and isinstance(result.get("data"), dict):
                    for path, scalar in scalar_paths(result["data"]): add(ident, path, scalar)
            for item in value.values(): scan(item, failed)
    for value in _decoded_messages(request): scan(value)
    return facts, conflicts


def _fields_present(facts, ident, fields):
    available = facts.get(ident, {})
    return bool(fields) and all(
        json.dumps(f.get("path"), ensure_ascii=False) in available and
        _encoded(available[json.dumps(f["path"], ensure_ascii=False)]["value"]) == _encoded(f.get("value"))
        for f in fields)


def _memory_summary(goal):
    out = _goal_excerpt(goal)
    for key in ("contract_version", "requirements", "records", "default_record", "current_execution_record", "pending_actions", "scientific_facts"):
        if key in goal:
            out[key] = goal[key]
    return out


def _read_numeric_checks(evidence, records):
    """Check supported read scalars independently, without claiming new work."""
    rows = []
    name = evidence.get("capability")
    for field in evidence.get("fields", []):
        path = field.get("path", [])
        supported = (name == "amplitude" and len(path) == 2 and path[1] == "rms") or (
            name == "psd" and len(path) == 2) or (name == "event_bandpower" and len(path) == 5 and path[0] == "conditions")
        if not supported:
            continue
        record = records[evidence["record"]]
        scope = dict(evidence["parameters"])
        if name == "event_bandpower": scope["labels"] = [path[1]]
        expected = independent_oracle(record, {"capability": name, "parameters": scope}, path)
        actual = float(field["value"])
        tolerance = .005 if name in {"amplitude", "psd"} else 1e-6
        rows.append({"result_id": evidence["task_id"], "record": evidence["record"], "tool": name,
            "scope": scope, "field": path, "actual": actual, "oracle": expected,
            "numeric_valid": bool(np.isclose(actual, expected, rtol=tolerance, atol=5e-13)),
            "source_valid": evidence.get("source") == record.source,
            "meaning": "Historical result read, not fresh numerical execution"})
    return rows


def _request_views(requests):
    visible, actual_facts = [], []
    for index, request in enumerate(requests, 1):
        payload = payload_for(request)
        facts, conflicts = evidence_in_request(request)
        actual_facts.append(facts)
        restored = payload.get("restored_trajectories", [])
        restored_ids = [(x.get("subgoal") or {}).get("subgoal_id") for x in restored]
        # A successful native tool response also enters the next actual prompt.
        for value in _decoded_messages(request):
            if isinstance(value, dict) and value.get("tool_name") in {"restore_task", "restore_subgoal"} and value.get("success"):
                data = value.get("data") or {}
                restored_ids.append((data.get("subgoal") or {}).get("subgoal_id"))
        summaries = payload.get("task_summaries", payload.get("archived_summaries", []))
        visible.append({"request_index": index, "request_id": request.get("request_id"),
            "turn": request.get("context", {}).get("turn"),
            "tool_choice": request.get("tool_choice", "auto"),
            "exact_results": [{"result_id": ident, "field_count": len(fields),
                "field_paths": [f["path"] for f in fields.values()], "field_values_sha256": _digest(list(fields.values()))}
                for ident, fields in facts.items()],
            "conflicting_exact_fields": conflicts,
            "summary_task_ids": [x.get("subgoal_id") for x in summaries],
            "active_task_id": (payload.get("active_task") or {}).get("subgoal_id"),
            "active_task_completion": (payload.get("active_task") or {}).get("delivery_check"),
            "restored_task_ids": sorted({x for x in restored_ids if x}),
            "artifact_locators": sorted(set().union(*(artifact_ids(v) for v in _decoded_messages(request)))),
            "delivery_reason": payload.get("delivery_reason", payload.get("delivery_phase")),
            "actual_wire_payload_bytes": request.get("actual_wire_payload_bytes"),
            "component_bytes": request.get("components", {})})
    return visible, actual_facts


def _response_actions(responses):
    calls = {}
    for index, response in enumerate(responses, 1):
        for call in (response.get("raw_assistant_message") or {}).get("tool_calls") or []:
            fn = call.get("function", {})
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try: args = json.loads(args)
                except ValueError: args = {"invalid_json": args}
            calls[call["id"]] = {"request_index": index, "arguments": args}
    return calls


def _comparison_checks(comparison, records):
    """Recompute each operand from synthetic samples, then arithmetic separately."""
    checks, values = [], []
    for operand in comparison.get("operands", []):
        field = operand["field"]
        capability = "event_bandpower" if len(field) == 5 else "amplitude" if field[-1] == "rms" else "psd"
        params = dict(operand["scope"])
        if capability == "event_bandpower":params["labels"] = [field[1]]
        record = records[operand["record"]]
        expected = independent_oracle(record, {"capability":capability,"parameters":params}, field)
        values.append(float(operand["value"]))
        checks.append({"result_id":operand["result_id"], "record":operand["record"], "scope":params,
            "field":field,"actual":operand["value"],"oracle":expected,
            "numeric_valid":bool(np.isclose(operand["value"],expected,rtol=.005 if capability != "event_bandpower" else 1e-6,atol=5e-13)),
            "source_valid":operand["source"] == record.source})
    if len(values) != 2:
        raise ValueError("Comparison must have two actual operand records")
    left,right=values
    ratio=right/left if left else None
    return {"comparison_id":comparison["comparison_id"],"operands":checks,
        "difference_valid":bool(np.isclose(comparison["right_minus_left"],right-left,rtol=1e-12,atol=1e-24)),
        "ratio_valid":comparison.get("right_divided_by_left") is None if ratio is None else
            bool(np.isclose(comparison["right_divided_by_left"],ratio,rtol=1e-12,atol=1e-12)),
        "canonical_display":comparison.get("canonical_display"),
        "meaning":"Actual-tool operand verification plus arithmetic; final prose and causal claims still require review"}


def audit_run(directory):
    directory = Path(directory)
    manifest, spec = read_json(directory/"manifest.json"), read_json(directory/"protocol.json")
    if manifest["protocol_content_sha256"] != digest(spec):
        raise ValueError("Frozen protocol hash differs from the saved run protocol")
    records = records_for("development" if manifest["phase"] == "development" else "confirmation")
    actual_hashes = {alias: hashlib.sha256(record.data.tobytes()).hexdigest() for alias, record in records.items()}
    if manifest.get("data_sha256") != actual_hashes:
        raise ValueError("Synthetic data bytes differ from the original run manifest")
    requests, responses = read_rows(directory/"requests.jsonl"), read_rows(directory/"responses.jsonl")
    call_map = _response_actions(responses)
    visibility, actual_facts = _request_views(requests)
    turns, actions, numeric, audit_errors, comparisons = [], [], [], [], []
    for path in sorted(directory.glob("turn-*.json"), key=lambda x: int(x.stem.split("-")[-1])):
        result = read_json(path)
        number = int(path.stem.split("-")[-1])
        current_actions = []
        for order, action in enumerate(result.get("tool_results", []), 1):
            linked = call_map.get(action["request_id"], {})
            data = action.get("data") or {}
            row = {"turn": number, "action_index": order, "call_id": action["request_id"],
                "request_index": linked.get("request_index"), "tool": action["tool_name"],
                "arguments": linked.get("arguments"), "success": action["success"],
                "status": data.get("status"), "error": action.get("error"),
                "result_id": data.get("task_id"), "subgoal_id": data.get("subgoal_id")}
            if not action["success"]:
                row["failure_data"] = data
            observation = data.get("observation")
            if observation:
                row["observation"] = observation
                if observation["result"]["success"]:
                    try:
                        numeric.extend(dict(check, turn=number, action_index=order)
                            for check in _number_checks(observation, records))
                    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
                        audit_errors.append({"turn": number, "action_index": order,
                            "error_type": type(exc).__name__, "message": str(exc)})
            if action["tool_name"] in {"read_result", "read_evidence"} and action["success"]:
                row["read_evidence"] = data.get("evidence")
            if action["tool_name"] in {"restore_task", "restore_subgoal"} and action["success"]:
                row["restored_task_id"] = (data.get("subgoal") or {}).get("subgoal_id")
                row["restored_artifact_ids"] = sorted(artifact_ids(data.get("action_observations", [])))
                row["restored_observation_count"] = len(data.get("action_observations", []))
                row["restored_observation_sha256"] = _digest(data.get("action_observations", []))
            if action["tool_name"] == "focus_task" and action["success"]:
                task = data.get("task") or {}
                row["declared_task"] = _memory_summary(task)
                row["declared_requirement_count"] = len(task.get("requirements", []))
            if action["tool_name"] == "compare_results" and action["success"]:
                row["verified_comparison"] = data
                try:
                    comparison = _comparison_checks(data, records)
                    comparison.update(turn=number, request_index=linked.get("request_index"))
                    comparisons.append(comparison)
                except (KeyError,TypeError,ValueError,IndexError) as exc:
                    audit_errors.append({"kind":"comparison_oracle","turn":number,"error_type":type(exc).__name__,"message":str(exc)})
            actions.append(row); current_actions.append(row)
        memory = result.get("working_memory") or {}
        turns.append({"turn": number, "request": (spec["development"]["requests"] if manifest["phase"] == "confirmation" else spec[manifest["phase"]]["requests"])[number-1],
            "stop_reason": result["stop_reason"], "rounds": result["rounds"], "tool_calls": result["tool_calls"],
            "final_answer_verbatim": result["final_answer"], "actions": current_actions,
            "tasks": [_memory_summary(g) for g in memory.get("subgoals", [])],
            "lifecycle_events": memory.get("events", []),
            "semantic_review": "REQUIRED: stop status and numerical agreement do not certify full request delivery"})
    reads, restores, read_numeric = [], [], []
    for action in actions:
        index = action["request_index"]
        if index is None or not action["success"]:
            continue
        later = [(i+1, facts) for i, facts in enumerate(actual_facts) if i+1 > index]
        if action.get("read_evidence"):
            evidence = action["read_evidence"]
            ident, fields = evidence.get("task_id"), evidence.get("fields", [])
            where = [i for i, facts in later if _fields_present(facts, ident, fields)]
            finals = [a["request_index"] for a in actions if a["turn"] == action["turn"] and a["tool"] == "finish_task" and a["success"]]
            reads.append({"turn": action["turn"], "read_request_index": index, "result_id": ident,
                "actual_fields": fields, "visible_in_later_inputs": where,
                "visible_in_same_turn_final_generation": any(i in where for i in finals),
                "meaning": "Exact-value input exposure; actual answer use/correctness requires manual review"})
            try:
                read_numeric.extend(_read_numeric_checks(evidence, records))
            except (KeyError, TypeError, ValueError, IndexError) as exc:
                audit_errors.append({"turn": action["turn"], "request_index": index,
                    "error_type": type(exc).__name__, "message": str(exc), "kind": "read_oracle"})
        if action.get("restored_task_id"):
            visible = [v["request_index"] for v in visibility if v["request_index"] > index
                       and action["restored_task_id"] in v["restored_task_ids"]]
            uses = []
            for later_action in actions:
                obs = later_action.get("observation")
                if not obs or not obs["result"]["success"] or later_action["request_index"] is None:
                    continue
                resolved_artifact = obs["request"].get("arguments", {}).get("artifact_id")
                if resolved_artifact in action["restored_artifact_ids"] and any(v <= later_action["request_index"] for v in visible):
                    uses.append({"turn": later_action["turn"], "request_index": later_action["request_index"],
                        "tool": later_action["tool"], "actual_artifact_id": resolved_artifact})
            restores.append({"turn": action["turn"], "restore_request_index": index,
                "task_id": action["restored_task_id"], "artifact_ids": action["restored_artifact_ids"],
                "visible_in_later_inputs": visible, "subsequent_real_same_artifact_execution": uses,
                "temporal_exposure_then_execution": bool(visible and uses),
                "meaning": "Not a causal proof: the same locator may already have been visible elsewhere"})
    seed = read_json(directory/"controlled-history.json") if (directory/"controlled-history.json").exists() else None
    seed_numeric = []
    if seed:
        for action in seed.get("actions", []):
            observation = (action.get("result", {}).get("data") or {}).get("observation")
            if observation and observation["result"]["success"]:
                try: seed_numeric.extend(_number_checks(observation, records))
                except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
                    audit_errors.append({"kind": "controlled_seed_oracle", "error_type": type(exc).__name__, "message": str(exc)})
    return {"run": directory.name, "manifest": manifest, "turns": turns,
        "controlled_history": {k: seed[k] for k in ("kind", "entry_count", "scientific_content_sha256", "hash_exclusion")} if seed else None,
        "request_visibility": visibility, "numeric_checks": numeric, "audit_errors": audit_errors,
        "comparison_checks": comparisons,
        "read_chains": reads, "restore_chains": restores, "read_numeric_checks": read_numeric,
        "controlled_seed_numeric_checks": seed_numeric,
        "action_counts": {"numerical_attempts": sum(a["tool"] in NUMERIC_TOOLS for a in actions),
            "numerical_executed": sum(bool(a.get("observation")) for a in actions),
            "numerical_success": sum(bool(a.get("observation")) and a["observation"]["result"]["success"] for a in actions),
            "control_attempts": sum(a["tool"] not in NUMERIC_TOOLS for a in actions),
            "rejected": sum(not a["success"] for a in actions),
            "automatic_valid_reuse": sum(a["tool"] in NUMERIC_TOOLS and a["status"] == "reused" for a in actions),
            "successful_exact_reads": len(reads), "successful_process_restores": len(restores)},
        "autonomous_grouping_observations": [{"turn":a["turn"],"request_index":a["request_index"],
            "declared_task":a["declared_task"],"declared_requirement_count":a["declared_requirement_count"]}
            for a in actions if a.get("declared_requirement_count",0) > 1],
        "driver_events": read_rows(directory/"driver_events.jsonl"),
        "log_hashes": {p.name: sha(p) for p in sorted(directory.glob("*.json*"))}}


def _costs(ledger):
    starts = {r["request_id"]: r for r in ledger if r["event"] == "reserved"}
    ends = {r["request_id"]: r for r in ledger if r["event"] in {"received", "failed"}}
    costs = defaultdict(lambda: dict(attempts=0, received=0, failed=0, unsettled=0, charged_tokens=0,
        api_input_tokens=0, api_output_tokens=0, cache_hit_tokens=0, cache_miss_tokens=0, duration_seconds=0.0))
    for ident, start in starts.items():
        end = ends.get(ident, {})
        row = costs[start.get("context", {}).get("run_id", "unassigned")]
        row["attempts"] += 1
        row["received"] += end.get("event") == "received"
        row["failed"] += end.get("event") == "failed"
        row["unsettled"] += not bool(end)
        row["charged_tokens"] += end["total_tokens"] if end.get("total_tokens") is not None else start["reserved_tokens"]
        for target, origin in (("api_input_tokens", "prompt_tokens"), ("api_output_tokens", "completion_tokens"),
                ("cache_hit_tokens", "prompt_cache_hit_tokens"), ("cache_miss_tokens", "prompt_cache_miss_tokens")):
            row[target] += (end.get("usage") or {}).get(origin, 0)
        row["duration_seconds"] += end.get("duration_seconds", 0.0)
    return dict(costs)


def build_audit(root=ROOT):
    root = Path(root)
    ledger = read_rows(root/"budget.jsonl")
    if not ledger or ledger[0].get("stage") != "issue51":
        raise ValueError("An actual Issue51 ledger is required; no empty successful evidence artifact")
    run_paths = sorted(root.glob("*/manifest.json"))
    if not run_paths:
        raise ValueError("No actual run manifests; do not manufacture completed evidence")
    runs = [audit_run(p.parent) for p in run_paths]
    for layer in ("confirmation", "comparison"):
        selected = [r for r in runs if r["manifest"]["phase"] == layer]
        frozen = {(r["manifest"]["candidate_commit"], r["manifest"]["protocol_sha256"],
                   r["manifest"]["model_requested"], _digest(r["manifest"]["model_settings"])) for r in selected}
        if len(frozen) > 1:
            raise ValueError("Paired layer changed candidate/protocol/model; do not combine it as matched confirmation")
    costs = _costs(ledger)
    return {"stage": "issue51", "kind": "posthoc_synthetic_only_audit_NOT_automated_success_score",
        "public_coverage": {
            "included": "Natural requests and final answers; actual tool actions/failures; source/scope/version/artifact facts; independent numeric checks; exact-field input visibility; read/restore temporal chains; complete stage costs and file hashes",
            "excluded": "Full system prompts, full native request/response transcripts, credentials, private paths and real EEG; original synthetic logs remain locally preserved",
            "caution": "Completed status, observed values, or a restoration count alone never establish complete scientific delivery or memory efficacy"},
        "runs": runs, "costs_by_run": costs,
        "cost_total": {k: sum(v[k] for v in costs.values()) for k in next(iter(costs.values()), {})},
        "currency_cost": "Not inferred from tokens; reconcile actual provider billing separately",
        "reported_models": dict(Counter(r.get("response_model_reported") for r in ledger if r["event"] == "received")),
        "budget_events": [r for r in ledger if r["event"] in {
            "reservation_rejected", "decision_reservation_rejected", "final_lease_decision"}],
        "layer_freezes": [r for r in ledger if r["event"] == "phase_frozen"],
        "arm_lifecycle": [r for r in ledger if r["event"] in {"arm_started", "arm_ended"}],
        "ledger_sha256": sha(root/"budget.jsonl"), "current_protocol_sha256": sha(SPEC),
        "manual_review_required": ["Original request completeness", "Scientific authorization and parameter meaning",
            "Final values, units and comparison", "Whether historical process actually informed interpretation",
            "Whether costs and successes support an advantage over the simpler common interface"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    value = build_audit(args.root)
    with args.output.open("x", encoding="utf8") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
    checks = [c for run in value["runs"] for c in run["numeric_checks"]]
    print(json.dumps({"runs": len(value["runs"]), "cost_total": value["cost_total"],
        "numeric_checks": len(checks), "all_present_numeric_checks_valid": bool(checks) and all(c["numeric_valid"] and c["source_valid"] for c in checks),
        "semantic_review": "required; no automated success grade"}, ensure_ascii=False))


if __name__ == "__main__": main()
