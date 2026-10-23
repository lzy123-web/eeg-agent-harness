"""CLI for the frozen CIEDG parsed-task formal evaluation."""

import argparse
import json
from pathlib import Path

from .runner import ABLATIONS, run_suite


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("development", "holdout"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-ablations", action="store_true")
    args = parser.parse_args(argv)
    methods = ("CIEDG", "strong_dynamic_expert") + (ABLATIONS if args.include_ablations else ())
    report = run_suite(args.split, methods=methods)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output), "split": args.split, "rows": len(report["rows"]),
        "aggregate": report["aggregate"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
