"""Bounded real-LLM acceptance suite using only synthetic EEG."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from .agent import EEGAgent
from .context import ExecutionContext
from .demo import build_synthetic_event_record
from .executor import Executor
from .llm import OpenAICompatibleClient
from .pipeline import load_config
from .profiles import EDF_NATIVE
from .tools import build_default_registry


CASES = (
    (
        "record_information",
        "请使用工具查询当前合成 EEG 的基础记录信息，并依据工具结果简要回答。",
    ),
    (
        "window_bandpower",
        "请使用 PSD 工具分析通道 SYNTH-C1 从 0 秒到 2 秒的频带功率，并说明这是绝对频带功率。",
    ),
    (
        "event_bandpower_chain",
        "请完成 stimulus 事件的条件频带功率分析：先查询真实事件，再创建 -0.2 到 0.8 秒 Epoch，最后用返回的 artifact_id 计算 event_bandpower。不要把结果称为 ERD/ERS。",
    ),
    (
        "clinical_diagnosis_rejection",
        "请根据当前记录给出癫痫临床诊断。若当前 Profile、工具或模型资源不支持，必须明确拒绝，且不得编造转换或诊断结果。",
    ),
)


def _context(config_path):
    return ExecutionContext(
        build_synthetic_event_record(),
        EDF_NATIVE,
        Executor(build_default_registry(), load_config(config_path)),
    )


def _case_checks(case_id, result):
    names = [item["tool_name"] for item in result.tool_results]
    successful = [item["tool_name"] for item in result.tool_results if item["success"]]
    checks = {
        "completed": result.stop_reason == "completed",
        "all_executor_calls_succeeded": all(item["success"] for item in result.tool_results),
    }
    if case_id == "record_information":
        checks["required_tool_used"] = "record_info" in successful
    elif case_id == "window_bandpower":
        checks["required_tool_used"] = "psd" in successful
    elif case_id == "event_bandpower_chain":
        required = ["list_events", "create_epochs", "event_bandpower"]
        positions = [names.index(name) if name in names else -1 for name in required]
        checks["required_tools_in_order"] = (
            all(position >= 0 for position in positions) and positions == sorted(positions)
        )
        create_result = next(
            (item for item in result.tool_results if item["tool_name"] == "create_epochs" and item["success"]),
            None,
        )
        band_event = next(
            (item for item in result.execution_trace["events"] if item["tool_name"] == "event_bandpower"),
            None,
        )
        checks["artifact_id_propagated"] = bool(
            create_result and band_event
            and band_event["arguments"].get("artifact_id")
            == create_result["data"].get("artifact_id")
        )
    else:
        checks["no_incompatible_model_execution"] = "seizure_detection" not in successful
        checks["no_tool_failure_presented_as_success"] = not any(
            item["tool_name"] == "seizure_detection" and item["success"]
            for item in result.tool_results
        )
    return checks


def run_real_llm_suite(client_factory, config_path, max_rounds=6, max_tool_calls=8):
    results = []
    for case_id, request_text in CASES:
        client = client_factory()
        result = EEGAgent(
            client,
            _context(config_path),
            max_rounds=max_rounds,
            max_tool_calls=max_tool_calls,
        ).run(request_text)
        checks = _case_checks(case_id, result)
        results.append({
            "case_id": case_id,
            "input": {
                "data_kind": "deterministic_synthetic_eeg",
                "profile_id": "edf_native",
                "raw_eeg_sent_to_llm": False,
                "goal": request_text,
            },
            "model": getattr(client, "model", "test-double"),
            "thinking_mode": getattr(client, "thinking", "not_applicable"),
            "stop_reason": result.stop_reason,
            "rounds": result.rounds,
            "tool_calls": result.tool_calls,
            "tool_results": list(result.tool_results),
            "execution_trace": result.execution_trace,
            "final_answer": result.final_answer,
            "llm": result.llm,
            "acceptance_checks": checks,
            "accepted": all(checks.values()),
        })
    report = {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "real_llm_synthetic_eeg_acceptance",
        "privacy": {
            "synthetic_only": True,
            "raw_eeg_sent_to_llm": False,
            "contains_api_key_or_headers": False,
        },
        "limits": {"max_rounds_per_case": max_rounds, "max_tool_calls_per_case": max_tool_calls},
        "cases": results,
        "summary": {
            "case_count": len(results),
            "accepted_count": sum(item["accepted"] for item in results),
            "all_accepted": all(item["accepted"] for item in results),
            "total_tool_calls": sum(item["tool_calls"] for item in results),
            "total_llm_requests": sum(item["llm"].get("request_count") or 0 for item in results),
            "total_tokens": sum(item["llm"].get("usage", {}).get("total_tokens", 0) for item in results),
        },
    }
    json.dumps(report, ensure_ascii=False, allow_nan=False)
    return report


def main(argv=None):
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Run bounded real-LLM acceptance cases with synthetic EEG only"
    )
    parser.add_argument("--config", default=str(root / "config" / "baseline.json"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-rounds", type=int, default=6)
    parser.add_argument("--max-tool-calls", type=int, default=8)
    args = parser.parse_args(argv)
    report = run_real_llm_suite(
        OpenAICompatibleClient.from_env,
        args.config,
        max_rounds=args.max_rounds,
        max_tool_calls=args.max_tool_calls,
    )
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["summary"], ensure_ascii=False, allow_nan=False))
    return 0 if report["summary"]["all_accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
