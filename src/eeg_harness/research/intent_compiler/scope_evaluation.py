"""Bounded evaluation for the opt-in EEG goal/state scope compiler."""

from datetime import datetime, timezone
import json
from pathlib import Path

from .evaluation import _context
from .scope import IntentScopeCompilerV2Interpreter
from .scope_protocol import load_scope_protocol
from .scoring import score_decision


def select_scope_cases(split, case_ids=()):
    protocol, digest = load_scope_protocol()
    selected = [case for case in protocol["cases"] if case["split"] == split]
    if case_ids:
        wanted = set(case_ids)
        selected = [case for case in selected if case["id"] in wanted]
        missing = wanted - {case["id"] for case in selected}
        if missing:
            raise ValueError(f"Cases are absent from split {split}: {sorted(missing)}")
    return selected, digest


def score_raw_core(case, intent):
    if intent is None:
        return {"analysis_type": False, "objectives": False, "core_correct": False}
    analysis_ok = intent.analysis_type == case["gold"]["analysis_type"]
    objectives_ok = set(intent.objectives) == set(case["gold"]["objectives"])
    return {
        "analysis_type": analysis_ok,
        "objectives": objectives_ok,
        "core_correct": analysis_ok and objectives_ok,
    }


def evaluate_scope_cases(client, cases, *, requested_model, config_path="config/baseline.json"):
    rows = []
    for case in cases:
        before_models = len(getattr(client, "response_models", ()))
        before_usage = dict(getattr(client, "total_usage", {}))
        interpreter = IntentScopeCompilerV2Interpreter(client)
        candidate = interpreter.interpret(case["request"], _context(case["id"], config_path))
        after_usage = dict(getattr(client, "total_usage", {}))
        rows.append({
            "case_id": case["id"],
            "split": case["split"],
            "language": case["language"],
            "request": case["request"],
            "scope_class": case["gold"]["scope_class"],
            "requested_model": requested_model,
            "response_models": list(getattr(client, "response_models", ()))[before_models:],
            "usage": {
                key: after_usage.get(key, 0) - before_usage.get(key, 0)
                for key in set(before_usage) | set(after_usage)
            },
            "raw_intent": None if interpreter.last_raw_intent is None else interpreter.last_raw_intent.to_dict(),
            "raw_core_score": score_raw_core(case, interpreter.last_raw_intent),
            "raw_scope": None if interpreter.last_raw_scope is None else interpreter.last_raw_scope.to_dict(),
            "v0_decision": score_decision(case, interpreter.v1.last_v0_interpretation),
            "v1_decision": score_decision(case, interpreter.last_v1_interpretation),
            "v2_decision": score_decision(case, candidate),
            "v1_diagnostics": interpreter.v1.last_diagnostics,
            "v2_diagnostics": interpreter.last_scope_diagnostics,
        })
    return rows


def summarize_scope(rows):
    summary = {"cases": len(rows)}
    for version in ("v0", "v1", "v2"):
        decisions = [row[f"{version}_decision"] for row in rows]
        summary.update({
            f"{version}_correct": sum(item["correct"] for item in decisions),
            f"{version}_dangerous_accept": sum(item["dangerous_accept"] for item in decisions),
            f"{version}_false_reject": sum(item["false_reject"] for item in decisions),
        })
    summary["raw_core_correct"] = sum(row["raw_core_score"]["core_correct"] for row in rows)
    return summary


def build_scope_report(client, cases, *, requested_model, protocol_hash, budget, config_path):
    start_requests = budget.request_count
    start_tokens = budget.total_tokens
    rows = evaluate_scope_cases(
        client, cases, requested_model=requested_model, config_path=config_path)
    # Per-row clients expose cumulative provider metadata, so retain the exact
    # bounded totals at report level as the authoritative usage record.
    return {
        "protocol_id": "eeg-intent-scope-compiler-v2",
        "protocol_sha256": protocol_hash,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_data": "deterministic synthetic EEG metadata only",
        "raw_eeg_sent_to_llm": False,
        "gold_visible_to_runtime": False,
        "requested_model": requested_model,
        "budget": {
            "max_requests": budget.max_requests,
            "max_tokens": budget.max_tokens,
            "request_count": budget.request_count - start_requests,
            "total_tokens": budget.total_tokens - start_tokens,
        },
        "summary": summarize_scope(rows),
        "cases": rows,
    }


def write_scope_report(report, output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
