"""Run bounded real-Agent checks for the opt-in scope compiler."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from ...context import ExecutionContext
from ...executor import Executor
from ...llm import OpenAICompatibleClient
from ...pipeline import load_config
from ...profiles import EDF_NATIVE
from ...tools import build_default_registry
from ..evidence_phase import build_quality_selection_record
from .agent import IntentScopeTransferAgentV2
from .evaluation import BudgetedClient, SharedBudget
from .scope_protocol import load_scope_protocol


LEGACY_H14_PATH = "docs/research/results/eeg_intent_compiler_v1_holdout_flash.json"


def _selected_cases(ids):
    protocol, digest = load_scope_protocol()
    available = {case["id"]: case for case in protocol["cases"]}
    if "H14" in ids:
        old = json.loads(Path(LEGACY_H14_PATH).read_text(encoding="utf-8"))
        available["H14"] = next(case for case in old["cases"] if case["case_id"] == "H14")
        available["H14"] = {
            "id": "H14", "request": available["H14"]["request"],
            "origin": "Issue #17 development regression; excluded from v2 score",
        }
    missing = set(ids) - set(available)
    if missing:
        raise ValueError(f"Unknown cases: {sorted(missing)}")
    return [available[item] for item in ids], digest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--case", action="append", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--config", default="config/baseline.json")
    parser.add_argument("--max-requests", type=int, required=True)
    parser.add_argument("--max-tokens", type=int, required=True)
    args = parser.parse_args(argv)

    selected, digest = _selected_cases(args.case)
    base = OpenAICompatibleClient(
        os.environ["EEG_HARNESS_LLM_BASE_URL"], os.environ["EEG_HARNESS_LLM_API_KEY"],
        args.model, timeout=os.environ.get("EEG_HARNESS_LLM_TIMEOUT", "60"),
        max_tokens=os.environ.get("EEG_HARNESS_LLM_MAX_TOKENS", "1024"),
        max_retries=os.environ.get("EEG_HARNESS_LLM_MAX_RETRIES", "1"), thinking="disabled",
    )
    budget = SharedBudget(args.max_requests, args.max_tokens)
    client = BudgetedClient(base, budget)
    config = load_config(args.config)
    rows = []
    for case in selected:
        record, _ = build_quality_selection_record((1,))
        ctx = ExecutionContext(
            record, EDF_NATIVE, Executor(build_default_registry(), config),
            task_id=f"intent-scope-agent-{case['id']}",
        )
        before_requests, before_tokens = budget.request_count, budget.total_tokens
        result = IntentScopeTransferAgentV2(client, ctx).run(case["request"])
        rows.append({
            "case_id": case["id"], "request": case["request"],
            "origin": case.get("origin", "frozen v2 protocol"),
            "provider_requests": budget.request_count - before_requests,
            "provider_tokens": budget.total_tokens - before_tokens,
            "result": result.to_dict(),
        })
    report = {
        "protocol_id": "eeg-intent-scope-v2-real-agent-check",
        "protocol_sha256": digest,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_data": "deterministic synthetic EEG only",
        "raw_eeg_sent_to_llm": False,
        "gold_visible_to_runtime": False,
        "requested_model": args.model,
        "response_models": list(base.response_models),
        "budget": {"max_requests": budget.max_requests, "max_tokens": budget.max_tokens,
                   "request_count": budget.request_count, "total_tokens": budget.total_tokens},
        "cases": rows,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({
        "output": str(output), "budget": report["budget"],
        "cases": [{"case_id": row["case_id"],
                   "stop_reason": row["result"]["stop_reason"]} for row in rows],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
