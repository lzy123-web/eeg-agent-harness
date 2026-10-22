"""Budget-bounded Stage C routing comparison on frozen holdout requests."""

import json
import time


METHOD_PROMPTS = {
    "native_routing": (
        "你是 EEG 分析执行助手。根据用户请求和 RECORD_METADATA 选择下一步。"
        "不得编造工具能力、数据或临床诊断；缺少必要信息时可以澄清。"
    ),
    "strong_preflight": (
        "你是严格的 EEG 路由器。决策前逐项检查分析类型、通道、时间窗、来源阶段、"
        "事件条件、筛选授权和输出边界。显式给定的值必须原样保留；有多个合理解释且"
        "缺少任何必要项时必须 clarify，不得用默认值替代。只提交一个决策。"
    ),
    "intent_contract": (
        "你是 EEG 科学意图契约编译器。先在内部区分 UserIntentContract（用户显式值与"
        "未知项）、ScientificPlanContract（唯一忠实且受支持的分析）和 EvidenceContract"
        "（回答所需证据）；再提交一个决策。不得把未知项补成猜测，不得改变通道、时间窗、"
        "条件、数据来源、筛选权限或输出边界。关键项未知则 clarify，不支持则 reject。"
    ),
}


DECISION_TOOL = [{
    "type": "function",
    "function": {
        "name": "submit_decision",
        "description": "Submit the single intent-preserving routing decision; this does not execute EEG analysis.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["execute", "clarify", "reject"]},
                "analysis_type": {"type": "string"},
                "channels": {"type": "array", "items": {"type": "string"}},
                "window": {"type": "array", "items": {"type": "number"}},
                "event_labels": {"type": "array", "items": {"type": "string"}},
                "source_stage": {"type": "string"},
                "reason": {"type": "string"}
            },
            "required": ["action", "analysis_type", "channels", "window", "event_labels", "source_stage", "reason"],
            "additionalProperties": False
        }
    }
}]


def _metadata(case):
    scenario = case["scenario"]
    return {
        "profile_id": "edf_native", "sfreq": 128.0, "duration_seconds": 8.0,
        "channel_names": ["SYNTH-C1", "SYNTH-C2"], "source_stage": "current",
        "event_labels": ["control", "stimulus"] if scenario == "synthetic_event_native" else [],
        "supported_analyses": ["record_info", "amplitude", "psd", "event_bandpower", "record_quality", "epoch_quality", "quality_selection"],
    }


def _parse_decision(message):
    calls = message.get("tool_calls") or []
    if len(calls) != 1 or calls[0].get("function", {}).get("name") != "submit_decision":
        return None, "missing_single_submit_decision"
    raw = calls[0]["function"].get("arguments", "{}")
    try:
        return (json.loads(raw) if isinstance(raw, str) else raw), None
    except (TypeError, json.JSONDecodeError):
        return None, "invalid_decision_json"


def score_decision(case, decision, parse_error=None):
    if parse_error or not isinstance(decision, dict):
        return {"accepted": False, "checks": {"valid_decision": False}, "error": parse_error}
    contract = case["contract"]
    expected_action = "execute" if contract["outcome"] == "complete" else contract["outcome"]
    analysis_aliases = {"bandpower": "psd", "band_power": "psd", "absolute_bandpower": "psd"}
    actual_analysis = analysis_aliases.get(decision.get("analysis_type"), decision.get("analysis_type"))
    checks = {
        "valid_decision": True,
        "action": decision.get("action") == expected_action,
        "analysis_type": actual_analysis == contract["analysis_type"],
        "channels": decision.get("channels", []) == contract["channels"],
        "source_stage": decision.get("source_stage") in {contract["source_stage"], "current"},
    }
    if contract["window"] is not None:
        actual = decision.get("window")
        checks["window"] = isinstance(actual, list) and len(actual) == 2 and all(
            abs(float(a) - float(b)) <= 1e-9 for a, b in zip(actual, contract["window"])
        )
    if contract["event_labels"]:
        checks["event_labels"] = set(decision.get("event_labels", [])) == set(contract["event_labels"])
    # Missing slots must remain empty rather than being silently guessed.
    for slot in contract["unknown_slots"]:
        checks[f"unknown_preserved:{slot}"] = not decision.get(slot)
    return {"accepted": all(checks.values()), "checks": checks, "error": None}


def rescore_comparison(payload, report):
    cases = {case["id"]: case for case in payload["cases"]}
    for item in report["results"]:
        item["score"] = score_decision(
            cases[item["case_id"]], item.get("decision"), item.get("parse_error")
        )
    by_method = {}
    for method in METHOD_PROMPTS:
        rows = [item for item in report["results"] if item["method"] == method]
        by_method[method] = {"cases": len(rows), "accepted": sum(item["score"]["accepted"] for item in rows)}
    report["summary"]["by_method"] = by_method
    return report


def run_comparison(payload, client):
    selected_ids = {"hold-missing-channel-01", "hold-channel-distractor-01"}
    cases = [case for case in payload["cases"] if case["id"] in selected_ids]
    outputs = []
    for case in cases:
        for method, prompt in METHOD_PROMPTS.items():
            before_tokens = client.total_usage.get("total_tokens", 0)
            before_requests = client.request_count
            started = time.perf_counter()
            message = client.complete(
                [
                    {"role": "system", "content": prompt + " RECORD_METADATA=" + json.dumps(_metadata(case), ensure_ascii=False)},
                    {"role": "user", "content": case["request"]},
                ],
                DECISION_TOOL,
                tool_choice={"type": "function", "function": {"name": "submit_decision"}},
            )
            decision, error = _parse_decision(message)
            outputs.append({
                "case_id": case["id"], "split": "holdout", "method": method,
                "decision": decision, "parse_error": error,
                "score": score_decision(case, decision, error),
                "usage_delta": {
                    "provider_requests": client.request_count - before_requests,
                    "total_tokens": client.total_usage.get("total_tokens", 0) - before_tokens,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                    "cost": None,
                },
            })
    by_method = {}
    for method in METHOD_PROMPTS:
        rows = [item for item in outputs if item["method"] == method]
        by_method[method] = {"cases": len(rows), "accepted": sum(item["score"]["accepted"] for item in rows)}
    return {
        "schema_version": "1.0", "runtime_received_gold": False,
        "privacy": {"synthetic_metadata_only": True, "raw_eeg_sent_to_llm": False, "credentials_recorded": False},
        "design": {"holdout_cases": len(cases), "methods": list(METHOD_PROMPTS), "provider_requests_per_method_case": 1, "eeg_tools_executed": False},
        "results": outputs,
        "summary": {
            "provider_requests": sum(item["usage_delta"]["provider_requests"] for item in outputs),
            "total_tokens": sum(item["usage_delta"]["total_tokens"] for item in outputs),
            "by_method": by_method,
        },
    }
