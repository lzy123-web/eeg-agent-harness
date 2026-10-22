"""Run one explicitly selected R3 EDF through the shared event workflow."""

import argparse
import json
from pathlib import Path

from ...pipeline import load_config
from .workflow import public_workflow_summary, run_r3_event_workflow


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edf", required=True, help="Explicit local EDF path")
    parser.add_argument("--config", default="config/baseline.json")
    parser.add_argument("--output", required=True, help="Ignored local JSON output path")
    parser.add_argument(
        "--public-summary",
        action="store_true",
        help="Write only de-identified counts instead of record-level features",
    )
    parser.add_argument(
        "--include-quality", action="store_true",
        help="Also run record and Epoch quality evidence tools locally",
    )
    args = parser.parse_args(argv)
    bundle = run_r3_event_workflow(
        args.edf, load_config(args.config), include_quality=args.include_quality
    )
    payload = public_workflow_summary(bundle) if args.public_summary else bundle
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(f"R3 workflow result written ({'public' if args.public_summary else 'local'} mode)")


if __name__ == "__main__":
    main()
