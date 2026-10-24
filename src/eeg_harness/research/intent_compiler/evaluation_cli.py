"""Run a bounded real-LLM EEG intent evaluation split."""

import argparse
import json
import os

from ...llm import OpenAICompatibleClient
from .evaluation import (
    BudgetedClient, SharedBudget, build_report, select_cases, write_report,
)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("development", "holdout"), required=True)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--config", default="config/baseline.json")
    parser.add_argument("--max-requests", type=int, required=True)
    parser.add_argument("--max-tokens", type=int, required=True)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    cases, digest = select_cases(args.split, args.case)
    client = OpenAICompatibleClient(
        os.environ["EEG_HARNESS_LLM_BASE_URL"],
        os.environ["EEG_HARNESS_LLM_API_KEY"],
        args.model,
        timeout=os.environ.get("EEG_HARNESS_LLM_TIMEOUT", "60"),
        max_tokens=os.environ.get("EEG_HARNESS_LLM_MAX_TOKENS", "1024"),
        max_retries=os.environ.get("EEG_HARNESS_LLM_MAX_RETRIES", "1"),
        thinking="disabled",
    )
    budget = SharedBudget(args.max_requests, args.max_tokens)
    bounded = BudgetedClient(client, budget)
    report = build_report(
        bounded, cases, requested_model=args.model, protocol_hash=digest,
        budget=budget, config_path=args.config,
    )
    write_report(report, args.output)
    print(json.dumps({
        "output": args.output,
        "summary": report["summary"],
        "budget": report["budget"],
        "response_models": sorted({
            case["response_model"] for case in report["cases"]
            if case["response_model"] is not None
        }),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
