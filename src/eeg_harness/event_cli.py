"""CLI for event-related analysis on native EDF or a labelled synthetic demo."""

import argparse
import json
from pathlib import Path

from .agent import EEGAgent
from .context import ExecutionContext
from .demo import build_synthetic_event_record
from .edf import load_edf
from .event_workflow import run_event_workflow
from .executor import Executor
from .llm import DemoFakeLLM
from .pipeline import load_config
from .profiles import EDF_NATIVE
from .tools import build_default_registry


def build_parser():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Run event-related EEG analysis")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--edf", help="EDF with readable MNE annotations")
    source.add_argument(
        "--demo-synthetic",
        action="store_true",
        help="Use generated MNE RawArray data; this is not an EDF integration test",
    )
    parser.add_argument("--native-channel", action="append", dest="native_channels")
    parser.add_argument("--label", action="append", dest="labels")
    parser.add_argument("--tmin", type=float, default=-0.2)
    parser.add_argument("--tmax", type=float, default=0.8)
    parser.add_argument("--baseline-start", type=float, default=-0.2)
    parser.add_argument("--baseline-end", type=float, default=0.0)
    parser.add_argument("--fake-agent", action="store_true")
    parser.add_argument("--config", default=str(root / "config" / "baseline.json"))
    parser.add_argument("--output")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    if args.demo_synthetic:
        record = build_synthetic_event_record()
        source_kind = "synthetic_mne_rawarray"
    else:
        record = load_edf(args.edf, EDF_NATIVE, selected_channels=args.native_channels)
        source_kind = "edf_with_mne_annotations"

    if args.fake_agent:
        context = ExecutionContext(
            record, EDF_NATIVE, Executor(build_default_registry(), config), task_id="event-fake-agent"
        )
        result = EEGAgent(DemoFakeLLM(), context).run("执行事件 Epoch 频带功率分析").to_dict()
    else:
        labels = args.labels or (["stimulus"] if args.demo_synthetic else None)
        if not labels:
            raise ValueError("At least one --label is required for EDF event workflow")
        result = run_event_workflow(
            record,
            EDF_NATIVE,
            config,
            labels,
            args.tmin,
            args.tmax,
            (args.baseline_start, args.baseline_end),
        )
    output = {"source_kind": source_kind, "result": result}
    rendered = json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        path = Path(args.output).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8")
        print(f"Event analysis written to {path}")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

