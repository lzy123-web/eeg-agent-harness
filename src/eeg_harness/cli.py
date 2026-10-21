"""Command-line entry point for the deterministic baseline."""

import argparse
import json
import os
from pathlib import Path

from .pipeline import run_baseline


def build_parser():
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Run EDF preprocessing, amplitude/PSD analysis, and one seizure inference without an LLM."
    )
    parser.add_argument("--edf", default=os.environ.get("EEG_HARNESS_EDF_PATH"))
    parser.add_argument("--model", default=os.environ.get("EEG_HARNESS_MODEL_PATH"))
    parser.add_argument("--config", default=str(project_root / "config" / "baseline.json"))
    parser.add_argument("--channel", default="FP1-F7")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=1)
    parser.add_argument("--output", default=None)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.edf:
        parser.error("--edf or EEG_HARNESS_EDF_PATH is required")
    if not args.model:
        parser.error("--model or EEG_HARNESS_MODEL_PATH is required")

    result = run_baseline(
        edf_path=args.edf,
        model_path=args.model,
        config_path=args.config,
        channel=args.channel,
        start=args.start,
        end=args.end,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
        print(f"Result written to {output}")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
