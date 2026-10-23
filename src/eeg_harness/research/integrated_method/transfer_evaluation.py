"""Small calibration for Issue #15; this is not the frozen formal experiment."""

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
from .transfer import ConstraintCarryingEEGAgentTransfer
from .transfer_diagnostics import (
    ExpireRereferencedArtifactBeforeBandpower,
    run_guarded_transfer_expert,
)
from .v1_evaluation import BoundedClient


REQUEST = (
    "对 target 事件后 0 秒到 1 秒的 Epoch，允许以 SYNTH-C2 作为参考通道重参考，"
    "检查转换后质量，汇总试次数并计算绝对频带功率"
)


def _context(config, task_id, fault):
    record, _ = build_quality_selection_record((1,))
    context = ExecutionContext(
        record, EDF_NATIVE, Executor(build_default_registry(), config), task_id,
    )
    if fault:
        context.executor = ExpireRereferencedArtifactBeforeBandpower(context.executor)
    return context


def _science_signature(release_results):
    summary = next(row["data"] for row in release_results if row["tool_name"] == "epoch_summary")
    power = next(row["data"] for row in release_results if row["tool_name"] == "event_bandpower")
    quality = next(row["data"] for row in release_results if row["tool_name"] == "epoch_quality")
    return {
        "reference": summary["reference"],
        "shape": summary["shape"],
        "epoch_counts": quality["epoch_counts"],
        "conditions": power["conditions"],
    }


def run_calibration(client, config_path="config/baseline.json"):
    config = load_config(config_path)
    cases = []
    for fault in (False, True):
        case_id = "reference-artifact-expiry" if fault else "reference-normal"
        candidate = ConstraintCarryingEEGAgentTransfer(
            client, _context(config, f"candidate-{case_id}", fault),
        ).run(REQUEST)
        expert = run_guarded_transfer_expert(
            _context(config, f"expert-{case_id}", fault),
            labels=("target",), tmin=0.0, tmax=1.0,
            reference_channels=("SYNTH-C2",), rereference_authorized=True,
        )
        candidate_signature = (
            _science_signature(candidate.execution["release_results"])
            if candidate.execution and candidate.stop_reason == "completed" else None
        )
        expert_signature = (
            _science_signature(expert["release_results"])
            if expert["status"] == "completed" else None
        )
        cases.append({
            "case_id": case_id,
            "fault": "expire_effective_artifact_before_bandpower" if fault else None,
            "candidate_stop": candidate.stop_reason,
            "expert_stop": expert["status"],
            "candidate_tool_calls": len(candidate.execution["tool_results"]) if candidate.execution else 0,
            "expert_tool_calls": len(expert["tool_results"]),
            "science_equal": candidate_signature == expert_signature,
            "candidate": candidate.to_dict(),
            "expert": expert,
        })
    return {
        "protocol_id": "point1-transfer-calibration-v1",
        "formal_experiment": False,
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
    parser.add_argument("--max-requests", type=int, default=6)
    parser.add_argument("--max-tokens", type=int, default=12000)
    args = parser.parse_args(argv)
    client = (
        BoundedClient(OpenAICompatibleClient.from_env(), args.max_requests, args.max_tokens)
        if args.real else Point1FakeLLM()
    )
    report = run_calibration(client, args.config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "cases": len(report["cases"]),
        "provider_requests": report["provider_usage"]["request_count"],
        "candidate_stops": [row["candidate_stop"] for row in report["cases"]],
        "science_equal": [row["science_equal"] for row in report["cases"]],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
