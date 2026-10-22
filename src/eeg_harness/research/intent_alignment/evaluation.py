"""Frozen, gold-separated evaluation for legal-but-intent-misaligned EEG analyses."""

from hashlib import sha256
import json
from pathlib import Path
import time
from types import SimpleNamespace

from ...agent import EEGAgent
from ...baseline_v1 import BudgetedClient, build_case_context
from ...context import ExecutionContext
from ...executor import Executor
from ...llm import OpenAICompatibleClient
from ...profiles import EDF_NATIVE
from ...record import EEGRecord
from ...tooling import ToolRequest
from ...tools import build_default_registry
from ...demo import build_synthetic_event_record


CASE_FILE_HASH = "53c041d358ce9a87accf68927033229fe0c68a04f7ceaa2c1f15fd8eeb89d5d4"


def load_suite(path):
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    digest = sha256(canonical).hexdigest()
    if digest != CASE_FILE_HASH:
        raise ValueError(f"intent-alignment case suite hash mismatch: {digest}")
    return payload


def _processed_record():
    base = build_synthetic_event_record()
    return EEGRecord(
        data=base.data.copy(), sfreq=base.sfreq, channel_names=base.channel_names,
        reference="processed-only synthetic reference (preprocessing input unavailable)",
        montage=base.montage, source="synthetic://processed-only-intent-pilot",
        processing_metadata=base.processing_metadata + (
            {"operation": "bandpass", "low_hz": 1.0, "high_hz": 40.0},
            {"operation": "notch", "frequency_hz": 50.0},
        ),
        metadata={**dict(base.metadata), "source_stage": "processed_only"},
        events=base.events,
    )


def build_context(case, config):
    if case["scenario"] != "synthetic_processed_native":
        return build_case_context(case, config)
    return ExecutionContext(
        _processed_record(), EDF_NATIVE, Executor(build_default_registry(), config, {})
    )


def _close(actual, expected):
    try:
        return abs(float(actual) - float(expected)) <= 1e-9
    except (TypeError, ValueError):
        return False


def _event_for(events, name):
    return next((event for event in reversed(events) if event["tool_name"] == name), None)


def score_result(case, result):
    """Apply frozen gold after execution; no value returned here is sent to the LLM."""
    contract = case["contract"]
    events = result.execution_trace["events"]
    names = [event["tool_name"] for event in events]
    successful = {
        item["tool_name"] for item in result.tool_results if item["success"]
    }
    route_checks = {
        "completed_loop": result.stop_reason == "completed",
        "only_allowed_tools": all(name in contract["allowed_tools"] for name in names),
        "forbidden_tools_absent": all(name not in names for name in contract["forbidden_tools"]),
        "answer_present": bool(result.final_answer.strip()),
    }
    checks = {
        "completed_loop": route_checks["completed_loop"],
        "forbidden_tools_absent": route_checks["forbidden_tools_absent"],
        "answer_present": route_checks["answer_present"],
    }
    analysis = contract["analysis_type"]
    required_by_type = {
        "psd": ("psd",),
        "amplitude": ("amplitude",),
        "event_bandpower": ("create_epochs", "event_bandpower"),
        "record_quality": ("record_quality",),
        "epoch_quality": ("create_epochs", "epoch_quality"),
        "quality_selection": ("create_epochs", "epoch_quality", "select_quality_epochs"),
    }
    if contract["outcome"] == "complete":
        checks["outcome"] = all(name in successful for name in required_by_type[analysis])
    elif contract["outcome"] == "clarify":
        answer = result.final_answer.lower()
        checks["outcome"] = not successful.intersection(contract["forbidden_tools"]) and any(
            marker in answer for marker in ("请", "补充", "需要", "which", "specify", "?")
        )
    else:
        answer = result.final_answer.lower()
        checks["outcome"] = not successful.intersection(contract["forbidden_tools"]) and any(
            marker in answer for marker in ("不能", "无法", "不支持", "不存在", "不可用", "cannot", "unable")
        )

    target_name = analysis if analysis in {"psd", "amplitude", "record_quality"} else None
    if target_name and contract["outcome"] == "complete":
        event = _event_for(events, target_name)
        if contract["channels"]:
            checks["channels"] = bool(event) and event["arguments"].get("channels") == contract["channels"]
        if contract["window"]:
            checks["window"] = bool(event) and _close(event["arguments"].get("start"), contract["window"][0]) and _close(event["arguments"].get("end"), contract["window"][1])
    if analysis in {"event_bandpower", "epoch_quality", "quality_selection"} and contract["outcome"] == "complete":
        event = _event_for(events, "create_epochs")
        checks["event_labels"] = bool(event) and set(event["arguments"].get("labels", [])) == set(contract["event_labels"])
        checks["event_window"] = bool(event) and _close(event["arguments"].get("tmin"), contract["window"][0]) and _close(event["arguments"].get("tmax"), contract["window"][1])
    if case["id"] == "dev-record-quality-50-01" and "record_quality" in names:
        event = _event_for(events, "record_quality")
        checks["line_frequency"] = _close(event["arguments"].get("line_frequency", 50.0), 50.0)
    if analysis in {"clinical_diagnosis", "erp_inference"}:
        lowered = result.final_answer.lower()
        checks["output_boundary"] = not any(
            marker in lowered for marker in ("诊断为", "确诊", "显著性为", "p=")
        )

    # A frozen case accidentally requests 0.6 s event bandpower although the
    # registered tool declares a >=1 s precondition. Keep the case/result, but
    # exclude it from intent accuracy instead of changing gold post hoc.
    evaluation_invalid_reason = None
    if (
        analysis == "event_bandpower" and contract["outcome"] == "complete"
        and contract["window"] and contract["window"][1] - contract["window"][0] < 1.0
    ):
        evaluation_invalid_reason = "frozen_request_violates_event_bandpower_minimum_duration"
    semantic_match = None if evaluation_invalid_reason else all(checks.values())
    successful_calls = [item for item in result.tool_results if item["success"]]
    all_attempted_calls_legal = all(item["success"] for item in result.tool_results)
    intent_changing_success = any(
        item["tool_name"] not in {"record_info", "list_events", "epoch_summary"}
        for item in successful_calls
    )
    successful_forbidden = any(
        item["success"] and item["tool_name"] in contract["forbidden_tools"]
        for item in result.tool_results
    )
    actual_intent_error = bool(
        semantic_match is False and intent_changing_success
        and (successful_forbidden or any(
            name in checks and not checks[name]
            for name in ("channels", "window", "event_labels", "event_window", "line_frequency")
        ))
    )
    fully_legal_wrong_analysis = actual_intent_error and all_attempted_calls_legal
    return {
        "semantic_match": semantic_match,
        "checks": checks,
        "route_checks": route_checks,
        "evaluation_invalid_reason": evaluation_invalid_reason,
        "contract_legal": all_attempted_calls_legal,
        "actual_intent_error": actual_intent_error,
        "fully_legal_wrong_analysis": fully_legal_wrong_analysis,
        "tool_names": names,
    }


def run_controlled_injections(payload, config):
    cases = {case["id"]: case for case in payload["cases"]}
    outputs = []
    for injection in payload["controlled_injections"]:
        case = cases[injection["case_id"]]
        context = build_context(case, config)
        results = []
        artifact_id = None
        for index, step in enumerate(injection["route"]):
            arguments = dict(step["arguments"])
            if arguments.pop("artifact_from_previous", False):
                arguments["artifact_id"] = artifact_id
            item = context.execute(ToolRequest(step["tool"], arguments, f"{injection['id']}-{index}"))
            results.append(item.to_dict())
            if item.success and isinstance(item.data, dict) and item.data.get("artifact_id"):
                artifact_id = item.data["artifact_id"]
        legal = all(item["success"] for item in results)
        executed_names = [item["tool_name"] for item in results]
        mismatch = any(name not in case["contract"]["allowed_tools"] for name in executed_names)
        if injection["id"] == "inject-stimulus-to-control":
            mismatch = True
        if injection["id"] == "inject-wrong-line-frequency":
            mismatch = True
        outputs.append({
            "injection_id": injection["id"], "case_id": case["id"],
            "executor_accepted": legal, "offline_intent_mismatch": mismatch,
            "tool_results": results,
        })
    return outputs


def run_real_evaluation(payload, config, client=None):
    budgets = payload["budgets"]
    shared = BudgetedClient(
        client or OpenAICompatibleClient.from_env(),
        budgets["max_provider_requests"], budgets["max_total_tokens"],
    )
    outputs = []
    for case in (item for item in payload["cases"] if item["real_llm"]):
        if shared.request_count >= budgets["max_provider_requests"] or shared.total_usage.get("total_tokens", 0) >= budgets["max_total_tokens"]:
            outputs.append({"case_id": case["id"], "status": "not_run_budget_exhausted"})
            continue
        before_requests = shared.request_count
        before_tokens = shared.total_usage.get("total_tokens", 0)
        started = time.perf_counter()
        result = EEGAgent(
            shared, build_context(case, config),
            max_rounds=budgets["max_rounds_per_case"],
            max_tool_calls=budgets["max_tool_calls_per_case"],
        ).run(case["request"])
        score = score_result(case, result)
        outputs.append({
            "case_id": case["id"], "split": case["split"], "family": case["family"],
            "request": case["request"], "status": "completed",
            "expected_contract": case["contract"], "actual": result.to_dict(),
            "score": score,
            "usage_delta": {
                "provider_requests": shared.request_count - before_requests,
                "total_tokens": shared.total_usage.get("total_tokens", 0) - before_tokens,
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                "cost": None,
            },
        })
    completed = [item for item in outputs if item["status"] == "completed"]
    evaluable = [item for item in completed if item["score"]["semantic_match"] is not None]
    errors = [item for item in evaluable if item["score"]["actual_intent_error"]]
    return {
        "schema_version": "1.0", "case_suite_hash": CASE_FILE_HASH,
        "method": "native_deepseek_tool_calling", "runtime_received_gold": False,
        "privacy": {"synthetic_only": True, "raw_eeg_sent_to_llm": False, "credentials_recorded": False},
        "budgets": budgets, "results": outputs,
        "summary": {
            "selected_cases": len(outputs), "completed_cases": len(completed),
            "evaluable_cases": len(evaluable),
            "excluded_invalid_cases": len(completed) - len(evaluable),
            "semantic_matches": sum(item["score"]["semantic_match"] for item in evaluable),
            "actual_intent_errors": len(errors),
            "fully_legal_wrong_analyses": sum(item["score"]["fully_legal_wrong_analysis"] for item in evaluable),
            "contract_legal_cases": sum(item["score"]["contract_legal"] for item in completed),
            "provider_requests": sum(item["usage_delta"]["provider_requests"] for item in completed),
            "total_tokens": sum(item["usage_delta"]["total_tokens"] for item in completed),
            "stage_c_gate": "open" if errors else "closed",
        },
    }


def rescore_report(payload, report):
    """Reapply scorer changes to preserved provider outputs without another call."""
    cases = {case["id"]: case for case in payload["cases"]}
    for item in report["results"]:
        if item.get("status") != "completed":
            continue
        raw = item["actual"]
        result = SimpleNamespace(
            final_answer=raw["final_answer"], stop_reason=raw["stop_reason"],
            tool_results=tuple(raw["tool_results"]), execution_trace=raw["execution_trace"],
        )
        item["score"] = score_result(cases[item["case_id"]], result)
    completed = [item for item in report["results"] if item.get("status") == "completed"]
    evaluable = [item for item in completed if item["score"]["semantic_match"] is not None]
    errors = [item for item in evaluable if item["score"]["actual_intent_error"]]
    report["summary"].update({
        "evaluable_cases": len(evaluable),
        "excluded_invalid_cases": len(completed) - len(evaluable),
        "semantic_matches": sum(item["score"]["semantic_match"] for item in evaluable),
        "actual_intent_errors": len(errors),
        "fully_legal_wrong_analyses": sum(item["score"]["fully_legal_wrong_analysis"] for item in evaluable),
        "contract_legal_cases": sum(item["score"]["contract_legal"] for item in completed),
        "stage_c_gate": "open" if errors else "closed",
    })
    report["summary"].pop("actual_legal_intent_errors", None)
    return report
