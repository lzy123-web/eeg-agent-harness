"""Bounded synthetic CCEP v1 integration traces for Fake or real LLMs."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from ...context import ExecutionContext
from ...executor import Executor
from ...llm import OpenAICompatibleClient
from ...pipeline import load_config
from ...profiles import EDF_NATIVE
from ...tools import build_default_registry
from ..evidence_phase import build_quality_selection_record
from .fake import Point1FakeLLM
from .v1 import ConstraintCarryingEEGAgentV1


CASES = (
    {
        "case_id": "v1-one-bad-authorized",
        "anomalous": (1,),
        "request": (
            "检查 target 事件后 0 秒到 1 秒的质量，允许筛除异常试次，"
            "随后计算筛选后试次的绝对频带功率"
        ),
    },
    {
        "case_id": "v1-clean-authorized",
        "anomalous": (),
        "request": (
            "检查 target 事件后 0 秒到 1 秒的质量，允许筛除异常试次，"
            "随后计算筛选后试次的绝对频带功率"
        ),
    },
    {
        "case_id": "v1-one-bad-selection-forbidden",
        "anomalous": (1,),
        "request": (
            "检查 target 事件后 0 秒到 1 秒的质量，不要筛选或剔除试次，"
            "随后计算未筛选试次的绝对频带功率"
        ),
    },
)


class BoundedClient:
    def __init__(self, client, max_requests=8, max_tokens=20000):
        self.client = client
        self.max_requests = int(max_requests)
        self.max_tokens = int(max_tokens)

    def __getattr__(self, name):
        return getattr(self.client, name)

    def complete(self, messages, tools, tool_choice="auto"):
        if self.client.request_count >= self.max_requests:
            raise RuntimeError("Declared CCEP v1 provider request budget exhausted")
        used = self.client.total_usage.get("total_tokens", 0)
        if used >= self.max_tokens:
            raise RuntimeError("Declared CCEP v1 provider token budget exhausted")
        return self.client.complete(messages, tools, tool_choice=tool_choice)


def run_suite(client, config_path="config/baseline.json"):
    config = load_config(config_path)
    results = []
    for case in CASES:
        record, truth = build_quality_selection_record(case["anomalous"])
        context = ExecutionContext(
            record,
            EDF_NATIVE,
            Executor(build_default_registry(), config),
            task_id=case["case_id"],
        )
        run = ConstraintCarryingEEGAgentV1(client, context).run(case["request"])
        results.append({
            "case_id": case["case_id"],
            "fixture": "clean" if not case["anomalous"] else "one_bad",
            "request": case["request"],
            "oracle_boundary": {
                "selection_authorized": "不要筛选" not in case["request"],
                "anomalous_epoch_indices": list(truth.anomalous_epoch_indices),
                "expected_created_epoch_count": 3,
            },
            "result": run.to_dict(),
        })
    return {
        "protocol_id": "ccep-v1-bounded-integration-v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_data": "deterministic synthetic EEG only",
        "raw_eeg_sent_to_llm": False,
        "gold_visible_to_runtime": False,
        "provider_budget": {
            "max_requests": getattr(client, "max_requests", None),
            "max_tokens": getattr(client, "max_tokens", None),
        },
        "provider_usage": {
            "request_count": getattr(client, "request_count", None),
            "tokens": dict(getattr(client, "total_usage", {})),
        },
        "cases": results,
    }


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real", action="store_true", help="Use env-configured OpenAI-compatible LLM")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", default="config/baseline.json")
    parser.add_argument("--max-requests", type=int, default=8)
    parser.add_argument("--max-tokens", type=int, default=20000)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.real:
        client = BoundedClient(
            OpenAICompatibleClient.from_env(), args.max_requests, args.max_tokens,
        )
    else:
        client = Point1FakeLLM()
    report = run_suite(client, args.config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "cases": len(report["cases"]),
        "provider_requests": report["provider_usage"]["request_count"],
        "stop_reasons": [item["result"]["stop_reason"] for item in report["cases"]],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
