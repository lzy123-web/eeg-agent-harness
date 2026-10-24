"""Bounded, same-payload evaluation for EEG Intent Compiler v1.

One provider response is decoded once, then passed to both the frozen v0
validator and the candidate compiler.  This separates model extraction errors
from validator decisions without exposing gold labels to either runtime.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path

from ...context import ExecutionContext
from ...executor import Executor
from ...pipeline import load_config
from ...profiles import EDF_NATIVE
from ...tools import build_default_registry
from ..evidence_phase import build_quality_selection_record
from .compiler import IntentCompilerV1Interpreter
from .protocol import load_protocol
from .scoring import score_decision, score_raw_fields


@dataclass
class SharedBudget:
    max_requests: int
    max_tokens: int
    request_count: int = 0
    total_tokens: int = 0

    def check(self):
        if self.request_count >= self.max_requests:
            raise RuntimeError("Intent evaluation provider request budget exhausted")
        if self.total_tokens >= self.max_tokens:
            raise RuntimeError("Intent evaluation provider token budget exhausted")

    def charge(self, requests, tokens):
        self.request_count += int(requests)
        self.total_tokens += int(tokens)
        if self.request_count > self.max_requests or self.total_tokens > self.max_tokens:
            raise RuntimeError("Intent evaluation provider budget exceeded")


class BudgetedClient:
    """Charge a shared budget using actual provider attempts and usage."""

    def __init__(self, client, budget):
        self.client = client
        self.budget = budget

    def __getattr__(self, name):
        return getattr(self.client, name)

    def complete(self, messages, tools, tool_choice="auto"):
        self.budget.check()
        before_requests = getattr(self.client, "request_count", 0)
        before_tokens = getattr(self.client, "total_usage", {}).get("total_tokens", 0)
        try:
            return self.client.complete(messages, tools, tool_choice=tool_choice)
        finally:
            requests = getattr(self.client, "request_count", 0) - before_requests
            tokens = getattr(self.client, "total_usage", {}).get("total_tokens", 0) - before_tokens
            self.budget.charge(requests, tokens)


def _context(case_id, config_path):
    record, _ = build_quality_selection_record((1,))
    return ExecutionContext(
        record,
        EDF_NATIVE,
        Executor(build_default_registry(), load_config(config_path)),
        task_id=f"intent-{case_id}",
    )


def evaluate_cases(client, cases, *, requested_model, config_path="config/baseline.json"):
    """Evaluate v0 and v1 from identical raw intent payloads."""
    rows = []
    for case in cases:
        context = _context(case["id"], config_path)
        interpreter = IntentCompilerV1Interpreter(client)
        candidate = interpreter.interpret(case["request"], context)
        raw = interpreter.last_raw_intent
        row = {
            "case_id": case["id"],
            "split": case["split"],
            "language": case["language"],
            "request": case["request"],
            "requested_model": requested_model,
            "response_model": getattr(client, "last_response_model", None),
            "usage": dict(getattr(client, "last_usage", {})),
            "raw_intent": None if raw is None else raw.to_dict(),
            "raw_score": None if raw is None else score_raw_fields(case, raw),
            "v0_decision": score_decision(case, interpreter.last_v0_interpretation),
            "v1_decision": score_decision(case, candidate),
            "v1_diagnostics": interpreter.last_diagnostics,
        }
        rows.append(row)
    return rows


def summarize(rows):
    def count(predicate):
        return sum(1 for row in rows if predicate(row))

    raw_correct = [
        row for row in rows
        if row["raw_score"] is not None and row["raw_score"]["all_fields_correct"]
    ]
    return {
        "cases": len(rows),
        "raw_all_fields_correct": len(raw_correct),
        "base_model_field_error": len(rows) - len(raw_correct),
        "v0_correct": count(lambda row: row["v0_decision"]["correct"]),
        "v1_correct": count(lambda row: row["v1_decision"]["correct"]),
        "v0_correct_given_raw_correct": sum(
            row["v0_decision"]["correct"] for row in raw_correct),
        "v1_correct_given_raw_correct": sum(
            row["v1_decision"]["correct"] for row in raw_correct),
        "raw_correct_denominator": len(raw_correct),
        "v0_false_reject": count(lambda row: row["v0_decision"]["false_reject"]),
        "v1_false_reject": count(lambda row: row["v1_decision"]["false_reject"]),
        "v0_dangerous_accept": count(lambda row: row["v0_decision"]["dangerous_accept"]),
        "v1_dangerous_accept": count(lambda row: row["v1_decision"]["dangerous_accept"]),
    }


def build_report(client, cases, *, requested_model, protocol_hash, budget, config_path):
    rows = evaluate_cases(
        client, cases, requested_model=requested_model, config_path=config_path)
    return {
        "protocol_id": "eeg-intent-compiler-v1",
        "protocol_sha256": protocol_hash,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_data": "deterministic synthetic EEG only",
        "raw_eeg_sent_to_llm": False,
        "gold_visible_to_runtime": False,
        "same_payload_v0_v1": True,
        "requested_model": requested_model,
        "budget": {
            "max_requests": budget.max_requests,
            "max_tokens": budget.max_tokens,
            "request_count": budget.request_count,
            "total_tokens": budget.total_tokens,
        },
        "summary": summarize(rows),
        "cases": rows,
    }


def select_cases(split, case_ids=()):
    protocol, digest = load_protocol()
    selected = [case for case in protocol["cases"] if case["split"] == split]
    if case_ids:
        wanted = set(case_ids)
        selected = [case for case in selected if case["id"] in wanted]
        missing = wanted - {case["id"] for case in selected}
        if missing:
            raise ValueError(f"Cases are absent from split {split}: {sorted(missing)}")
    return selected, digest


def write_report(report, output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
