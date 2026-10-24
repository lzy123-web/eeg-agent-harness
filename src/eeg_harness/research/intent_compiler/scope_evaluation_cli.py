"""Run a bounded real-LLM EEG goal/state scope evaluation."""

import argparse
import json
import os

from ...llm import OpenAICompatibleClient
from .evaluation import BudgetedClient, SharedBudget
from .scope_evaluation import (
    build_scope_report, select_scope_cases, write_scope_report,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("development", "holdout"), required=True)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--config", default="config/baseline.json")
    parser.add_argument("--max-requests", type=int, required=True)
    parser.add_argument("--max-tokens", type=int, required=True)
    args = parser.parse_args(argv)

    cases, digest = select_scope_cases(args.split, args.case)
    base = OpenAICompatibleClient(
        os.environ["EEG_HARNESS_LLM_BASE_URL"],
        os.environ["EEG_HARNESS_LLM_API_KEY"],
        args.model,
        timeout=os.environ.get("EEG_HARNESS_LLM_TIMEOUT", "60"),
        max_tokens=os.environ.get("EEG_HARNESS_LLM_MAX_TOKENS", "1024"),
        max_retries=os.environ.get("EEG_HARNESS_LLM_MAX_RETRIES", "1"),
        thinking="disabled",
    )
    budget = SharedBudget(args.max_requests, args.max_tokens)
    report = build_scope_report(
        BudgetedClient(base, budget), cases, requested_model=args.model,
        protocol_hash=digest, budget=budget, config_path=args.config,
    )
    write_scope_report(report, args.output)
    print(json.dumps({
        "output": args.output,
        "summary": report["summary"],
        "budget": report["budget"],
        "response_models": sorted({model for model in base.response_models if model}),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
