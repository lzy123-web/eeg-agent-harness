"""CLI for Fake or OpenAI-compatible EEG agent execution."""

import argparse
import json
import os
from pathlib import Path

from .agent import EEGAgent
from .context import ExecutionContext
from .demo import build_synthetic_event_record
from .edf import load_edf
from .executor import Executor
from .llm import DemoFakeLLM, DeterministicGoalFakeLLM, OpenAICompatibleClient
from .planning_agent import NaturalLanguagePlanningAgent
from .pipeline import load_config
from .profiles import get_profile
from .tools import build_default_registry


def build_parser():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Run the bounded EEG tool-calling agent")
    parser.add_argument("--edf", default=os.environ.get("EEG_HARNESS_EDF_PATH"))
    parser.add_argument("--profile", choices=("tuev_bipolar_22", "edf_native"))
    parser.add_argument("--model", default=os.environ.get("EEG_HARNESS_MODEL_PATH"))
    parser.add_argument("--config", default=str(root / "config" / "baseline.json"))
    parser.add_argument("--native-channel", action="append", dest="native_channels")
    parser.add_argument("--request", required=True)
    parser.add_argument(
        "--demo-synthetic", action="store_true",
        help="Use the explicit non-clinical synthetic event record; no EDF is read",
    )
    parser.add_argument("--fake", action="store_true", help="Use deterministic Fake LLM")
    parser.add_argument(
        "--planning", action="store_true",
        help="Interpret a structured goal and run the constrained Planner",
    )
    parser.add_argument("--output")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.demo_synthetic and not args.edf:
        parser.error("--edf or EEG_HARNESS_EDF_PATH is required")
    if args.demo_synthetic:
        if args.profile not in {None, "edf_native"}:
            parser.error("--demo-synthetic requires --profile edf_native")
        profile = get_profile("edf_native")
        record = build_synthetic_event_record()
    else:
        profile = get_profile(args.profile or "tuev_bipolar_22")
        record = load_edf(args.edf, profile, selected_channels=args.native_channels)
    resources = {"seizure_model": args.model} if args.model else {}
    context = ExecutionContext(
        record,
        profile,
        Executor(build_default_registry(), load_config(args.config), resources),
    )
    if args.fake:
        client = DeterministicGoalFakeLLM() if args.planning else DemoFakeLLM()
    else:
        client = OpenAICompatibleClient.from_env()
    agent = (
        NaturalLanguagePlanningAgent(client, context)
        if args.planning else EEGAgent(client, context)
    )
    result = agent.run(args.request).to_dict()
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

