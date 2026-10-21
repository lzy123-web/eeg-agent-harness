"""CLI for a deterministic Registry + Executor EEG workflow."""

import argparse
import json
import os
from pathlib import Path

from .pipeline import load_config
from .profiles import get_profile
from .workflow import run_workflow


def build_parser():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Run a traced multi-tool EEG workflow")
    parser.add_argument("--edf", default=os.environ.get("EEG_HARNESS_EDF_PATH"), required=False)
    parser.add_argument("--profile", choices=("tuev_bipolar_22", "edf_native"), default="tuev_bipolar_22")
    parser.add_argument("--model", default=os.environ.get("EEG_HARNESS_MODEL_PATH"))
    parser.add_argument("--config", default=str(root / "config" / "baseline.json"))
    parser.add_argument("--channel", required=True)
    parser.add_argument("--native-channel", action="append", dest="native_channels")
    parser.add_argument("--start", type=float, default=0)
    parser.add_argument("--end", type=float, default=1)
    parser.add_argument("--output")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.edf:
        parser.error("--edf or EEG_HARNESS_EDF_PATH is required")
    profile = get_profile(args.profile)
    result = run_workflow(
        args.edf,
        profile,
        load_config(args.config),
        args.channel,
        start=args.start,
        end=args.end,
        model_path=args.model,
        native_channels=args.native_channels,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
        print(f"Workflow written to {output}")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

