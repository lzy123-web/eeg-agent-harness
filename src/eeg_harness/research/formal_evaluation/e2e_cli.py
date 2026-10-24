"""Run bounded real-LLM CIEDG/native evaluation on frozen synthetic cases."""

import argparse
import json
from pathlib import Path

from ...llm import OpenAICompatibleClient
from .e2e import BoundedClient, run_e2e_suite


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-ids", nargs="+", default=["S02", "S06", "R05", "R11"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-requests", type=int, default=40)
    parser.add_argument("--max-total-tokens", type=int, default=140_000)
    args = parser.parse_args(argv)
    client = BoundedClient(OpenAICompatibleClient.from_env(), args.max_requests,
                           args.max_total_tokens)
    report = run_e2e_suite(client, args.case_ids)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False),
                           encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if report["summary"]["accepted"] == report["summary"]["rows"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
