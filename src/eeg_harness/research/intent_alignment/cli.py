"""Command line entry for the Issue #9 frozen experiment."""

import argparse
import json
from pathlib import Path

from ...pipeline import load_config
from .evaluation import load_suite, rescore_report, run_controlled_injections, run_real_evaluation


def main(argv=None):
    root = Path(__file__).resolve().parents[4]
    parser = argparse.ArgumentParser(description="Run frozen EEG intent-alignment evaluation")
    parser.add_argument("--cases", default=str(root / "config" / "point1_intent_alignment_cases.json"))
    parser.add_argument("--config", default=str(root / "config" / "baseline.json"))
    parser.add_argument("--mode", choices=("injections", "real", "rescore"), required=True)
    parser.add_argument("--input", help="Existing real report; required for rescore")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    payload = load_suite(args.cases)
    config = load_config(args.config)
    if args.mode == "injections":
        report = {"case_suite_hash": payload and __import__("eeg_harness.research.intent_alignment.evaluation", fromlist=["CASE_FILE_HASH"]).CASE_FILE_HASH,
                  "controlled_injections": run_controlled_injections(payload, config)}
    elif args.mode == "rescore":
        if not args.input:
            parser.error("--input is required for rescore")
        report = rescore_report(payload, json.loads(Path(args.input).read_text(encoding="utf-8")))
    else:
        report = run_real_evaluation(payload, config)
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    summary = report.get("summary") or {
        "injections": len(report["controlled_injections"]),
        "executor_accepted": sum(item["executor_accepted"] for item in report["controlled_injections"]),
        "offline_mismatch": sum(item["offline_intent_mismatch"] for item in report["controlled_injections"]),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
