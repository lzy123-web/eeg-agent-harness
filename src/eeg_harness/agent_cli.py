"""CLI for Fake or OpenAI-compatible EEG agent execution."""

import argparse
import json
import os
from pathlib import Path

from .agent import EEGAgent
from .context import ExecutionContext
from .demo import build_synthetic_event_record, build_synthetic_no_event_record
from .edf import load_edf
from .executor import Executor
from .llm import DemoFakeLLM, DeterministicGoalFakeLLM, OpenAICompatibleClient
from .planning_agent import NaturalLanguagePlanningAgent
from .pipeline import load_config
from .profiles import get_profile
from .tools import build_default_registry
from .research.integrated_method.agent import ConstraintCarryingEEGAgent
from .research.integrated_method.fake import Point1FakeLLM
from .research.integrated_method.v1 import ConstraintCarryingEEGAgentV1
from .research.integrated_method.v11 import ConstraintCarryingEEGAgentV11
from .research.integrated_method.v2 import ConstraintCarryingEEGAgentV2
from .research.integrated_method.v3_agent import InstanceGoalEEGAgent
from .research.integrated_method.transfer import ConstraintCarryingEEGAgentTransfer


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
    parser.add_argument(
        "--demo-synthetic-no-events", action="store_true",
        help="Use synthetic continuous EEG without events",
    )
    parser.add_argument("--fake", action="store_true", help="Use deterministic Fake LLM")
    parser.add_argument(
        "--planning", action="store_true",
        help="Interpret a structured goal and run the constrained Planner",
    )
    parser.add_argument(
        "--agent-mode", choices=(
            "native", "planning", "point1", "point1-v1", "point1-v11", "point1-v2",
            "point1-v3", "point1-transfer",
        ), default="native",
        help="Select the opt-in Agent runtime; point1 enables the integrated research method",
    )
    parser.add_argument("--max-rounds", type=int, default=6)
    parser.add_argument("--max-tool-calls", type=int, default=8)
    parser.add_argument("--output")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.agent_mode in {"point1-v2", "point1-v3"} and not args.fake and not (
        args.demo_synthetic or args.demo_synthetic_no_events
    ):
        parser.error("point1 research external LLM validation accepts only synthetic EEG")
    if args.agent_mode == "point1-v3" and args.fake:
        parser.error("point1-v3 scripted Fake cases use python -m eeg_harness.research.integrated_method.v3_validation")
    if not args.demo_synthetic and not args.demo_synthetic_no_events and not args.edf:
        parser.error("--edf or EEG_HARNESS_EDF_PATH is required")
    if args.demo_synthetic or args.demo_synthetic_no_events:
        if args.profile not in {None, "edf_native"}:
            parser.error("--demo-synthetic requires --profile edf_native")
        profile = get_profile("edf_native")
        record = build_synthetic_no_event_record() if args.demo_synthetic_no_events else build_synthetic_event_record()
    else:
        profile = get_profile(args.profile or "tuev_bipolar_22")
        record = load_edf(args.edf, profile, selected_channels=args.native_channels)
    resources = {"seizure_model": args.model} if args.model else {}
    context = ExecutionContext(
        record,
        profile,
        Executor(build_default_registry(), load_config(args.config), resources),
    )
    mode = "planning" if args.planning else args.agent_mode
    if args.fake:
        client = (
            Point1FakeLLM() if mode in {
                "point1", "point1-v1", "point1-v11", "point1-v2", "point1-transfer",
            } else
            DeterministicGoalFakeLLM() if mode == "planning" else DemoFakeLLM()
        )
    else:
        client = OpenAICompatibleClient.from_env()
    if mode == "point1-transfer":
        agent = ConstraintCarryingEEGAgentTransfer(client, context)
    elif mode == "point1-v2":
        agent = ConstraintCarryingEEGAgentV2(client, context)
    elif mode == "point1-v3":
        agent = InstanceGoalEEGAgent(client, context, max_tool_calls=args.max_tool_calls)
    elif mode == "point1-v11":
        agent = ConstraintCarryingEEGAgentV11(client, context)
    elif mode == "point1-v1":
        agent = ConstraintCarryingEEGAgentV1(client, context)
    elif mode == "point1":
        agent = ConstraintCarryingEEGAgent(client, context)
    elif mode == "planning":
        agent = NaturalLanguagePlanningAgent(client, context)
    else:
        agent = EEGAgent(
            client, context, max_rounds=args.max_rounds, max_tool_calls=args.max_tool_calls
        )
    raw_result = agent.run(args.request)
    result = raw_result if isinstance(raw_result, dict) else raw_result.to_dict()
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

