"""CLI for Fake or OpenAI-compatible EEG agent execution."""

import argparse
import json
import os
from pathlib import Path

from .agent import EEGAgent
from .context import ExecutionContext
from .edf import load_edf
from .executor import Executor
from .llm import DemoFakeLLM, OpenAICompatibleClient
from .pipeline import load_config
from .profiles import get_profile
from .tools import build_default_registry


def build_parser():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Run the bounded EEG tool-calling agent")
    parser.add_argument("--edf", default=os.environ.get("EEG_HARNESS_EDF_PATH"))
    parser.add_argument("--profile", choices=("tuev_bipolar_22", "edf_native"), default="tuev_bipolar_22")
    parser.add_argument("--model", default=os.environ.get("EEG_HARNESS_MODEL_PATH"))
    parser.add_argument("--config", default=str(root / "config" / "baseline.json"))
    parser.add_argument("--native-channel", action="append", dest="native_channels")
    parser.add_argument("--request", required=True)
    parser.add_argument("--fake", action="store_true", help="Use deterministic Fake LLM")
    parser.add_argument("--output")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.edf:
        parser.error("--edf or EEG_HARNESS_EDF_PATH is required")
    profile = get_profile(args.profile)
    record = load_edf(args.edf, profile, selected_channels=args.native_channels)
    resources = {"seizure_model": args.model} if args.model else {}
    context = ExecutionContext(
        record,
        profile,
        Executor(build_default_registry(), load_config(args.config), resources),
    )
    client = DemoFakeLLM() if args.fake else OpenAICompatibleClient.from_env()
    result = EEGAgent(client, context).run(args.request).to_dict()
    rendered = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
        print(f"Agent result written to {output}")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

