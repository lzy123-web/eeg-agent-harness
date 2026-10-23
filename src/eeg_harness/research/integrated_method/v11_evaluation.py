"""Bounded synthetic LRSP v1.1 integration traces for Fake or real LLMs."""

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
from .v11 import ConstraintCarryingEEGAgentV11
from .v1_evaluation import BoundedClient


CASES = (
    {
        "case_id": "v11-one-bad-authorized-two-consumers",
        "anomalous": (1,),
        "request": (
            "检查 target 事件后 0 秒到 1 秒的质量，允许筛除异常试次，"
            "汇总筛选后的试次数，并计算筛选后试次的绝对频带功率"
        ),
    },
    {
        "case_id": "v11-one-bad-selection-forbidden-two-consumers",
        "anomalous": (1,),
        "request": (
            "检查 target 事件后 0 秒到 1 秒的质量，不要筛选或剔除试次，"
            "汇总未筛选的试次数，并计算未筛选试次的绝对频带功率"
        ),
    },
    {
        "case_id": "v11-clean-authorized-summary",
        "anomalous": (),
        "request": (
            "检查 target 事件后 0 秒到 1 秒的质量，允许筛除异常试次，"
            "并汇总最终可用的试次数"
        ),
    },
)


def run_suite(client, config_path="config/baseline.json"):
    config = load_config(config_path)
    cases = []
    for case in CASES:
        record, truth = build_quality_selection_record(case["anomalous"])
        context = ExecutionContext(
            record, EDF_NATIVE, Executor(build_default_registry(), config),
            task_id=case["case_id"],
        )
        result = ConstraintCarryingEEGAgentV11(client, context).run(case["request"])
        cases.append({
            "case_id": case["case_id"],
            "request": case["request"],
            "oracle_boundary": {
                "synthetic_only": True,
                "anomalous_epoch_indices": list(truth.anomalous_epoch_indices),
                "selection_forbidden": "不要筛选" in case["request"],
            },
            "result": result.to_dict(),
        })
    return {
        "protocol_id": "ccep-lrsp-v11-bounded-integration-v1",
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
        "cases": cases,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", default="config/baseline.json")
    parser.add_argument("--max-requests", type=int, default=8)
    parser.add_argument("--max-tokens", type=int, default=20000)
    args = parser.parse_args(argv)
    client = (
        BoundedClient(
            OpenAICompatibleClient.from_env(), args.max_requests, args.max_tokens,
        ) if args.real else Point1FakeLLM()
    )
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
