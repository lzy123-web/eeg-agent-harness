"""Frozen Baseline v1 natural-language runner and deterministic acceptance checks."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

from .agent import EEGAgent
from .context import ExecutionContext
from .demo import (
    build_synthetic_event_record,
    build_synthetic_no_event_record,
    build_synthetic_tuev_record,
)
from .executor import Executor
from .llm import LLMServiceError, OpenAICompatibleClient
from .pipeline import load_config
from .profiles import EDF_NATIVE, TUEV_BIPOLAR_22
from .tools import build_default_registry


CASE_FILE_HASH = "e1713cda4c90c073d3b1290dc9af8df8cfa6788b88c969a310b3660884654ae1"


def load_case_suite(path):
    path = Path(path)
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    digest = sha256(canonical).hexdigest()
    return payload, digest


def build_case_context(case, config, model_path=None):
    scenario = case["scenario"]
    if scenario == "synthetic_event_native":
        record, profile = build_synthetic_event_record(), EDF_NATIVE
    elif scenario == "synthetic_no_event_native":
        record, profile = build_synthetic_no_event_record(), EDF_NATIVE
    elif scenario in {"synthetic_tuev_22_with_model", "synthetic_tuev_22_without_model"}:
        record, profile = build_synthetic_tuev_record(), TUEV_BIPOLAR_22
    else:
        raise ValueError(f"Unknown Baseline v1 scenario: {scenario}")
    resources = {}
    if scenario == "synthetic_tuev_22_with_model" and model_path:
        resources["seizure_model"] = model_path
    return ExecutionContext(
        record, profile, Executor(build_default_registry(), config, resources)
    )


def _tool_call(name, arguments, call_id):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [{
            "id": call_id,
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments)},
        }],
    }


class BaselineProtocolFakeLLM:
    """Case-aware protocol double; never used as language-model evidence."""

    model = "baseline-protocol-double"
    thinking = "not_applicable"

    def __init__(self, case):
        self.case = case
        self.calls = []
        self.pending = list(case["expected"]["required_tools"])
        self.request_count = 0
        self.total_usage = {}
        self.finish_reasons = []

    def _arguments(self, name, messages):
        expected = self.case["expected"].get("arguments", {}).get(name, {})
        if "labels_set" in expected:
            expected = {**expected, "labels": expected["labels_set"]}
            expected.pop("labels_set")
        if name in {"event_bandpower", "epoch_quality", "select_quality_epochs"}:
            for message in reversed(messages):
                if message["role"] != "tool":
                    continue
                result = json.loads(message["content"])
                if result.get("success") and result.get("tool_name") == "create_epochs":
                    return {"artifact_id": result["data"]["artifact_id"]}
        if name == "create_epochs" and not expected:
            return {"labels": ["stimulus"], "tmin": -0.2, "tmax": 0.8}
        return expected

    def complete(self, messages, tools):
        self.calls.append({"messages": messages, "tools": tools})
        self.request_count += 1
        self.finish_reasons.append("tool_calls" if self.pending else "stop")
        expected = self.case["expected"]
        if expected["outcome"] == "clarify" and not self.pending:
            return {"role": "assistant", "content": "请补充需要分析的通道、时间窗口和事件条件。"}
        if self.pending:
            name = self.pending.pop(0)
            return _tool_call(name, self._arguments(name, messages), f"fake-{self.case['id']}-{name}")
        if messages[-1]["role"] == "tool":
            result = json.loads(messages[-1]["content"])
            if not result["success"]:
                return {"role": "assistant", "content": f"无法完成：{result['error']['code']}，需要修正输入或资源。"}
            if self.case["id"] == "dev-no-events-01":
                return {"role": "assistant", "content": "当前记录没有事件，无法创建事件窗。"}
        if expected["outcome"] == "reject":
            checks = set(expected["answer_checks"])
            if "mentions_invalid_channel" in checks:
                return {"role": "assistant", "content": "该通道不存在，无法执行分析。"}
            if "mentions_invalid_window" in checks:
                return {"role": "assistant", "content": "请求的时间窗口无效或超出记录范围。"}
            if "mentions_missing_label" in checks:
                return {"role": "assistant", "content": "请求的事件标签不存在，无法分析。"}
            return {"role": "assistant", "content": "当前记录或工具不支持该请求，不能给出临床诊断或编造结果。"}
        return {"role": "assistant", "content": "已依据成功的工具结果完成分析；结果仅用于研究，不构成临床诊断。"}


class BudgetedClient:
    def __init__(self, client, max_requests, max_tokens):
        self.client = client
        self.max_requests = max_requests
        self.max_tokens = max_tokens

    def __getattr__(self, name):
        return getattr(self.client, name)

    def complete(self, messages, tools):
        if self.client.request_count >= self.max_requests:
            raise LLMServiceError("BUDGET_EXHAUSTED", "LLM request budget is exhausted.")
        if self.client.total_usage.get("total_tokens", 0) >= self.max_tokens:
            raise LLMServiceError("BUDGET_EXHAUSTED", "LLM token budget is exhausted.")
        return self.client.complete(messages, tools)


def _tool_arguments_match(actual, expected):
    for key, expected_value in expected.items():
        if key == "labels_set":
            if set(actual.get("labels", [])) != set(expected_value):
                return False
        elif isinstance(expected_value, (int, float)):
            if key not in actual or abs(float(actual[key]) - float(expected_value)) > 1e-9:
                return False
        elif actual.get(key) != expected_value:
            return False
    return True


def _answer_check(name, result):
    answer = result.final_answer.lower()
    failed_codes = {
        item["error"]["code"] for item in result.tool_results if not item["success"]
    }
    if name == "tool_grounded":
        return bool(result.tool_results) and bool(result.final_answer.strip())
    if name == "not_erd_ers":
        if "erd/ers" not in answer:
            return True
        for match in re.finditer(r"erd/ers", answer):
            prefix = answer[max(0, match.start() - 20):match.start()]
            if not any(marker in prefix for marker in ("不", "非", "不能", "不可", "not")):
                return False
        return True
    if name == "quality_not_score":
        return not any(term in answer for term in ("质量总分为", "质量评分为"))
    if name == "not_clinical":
        return not any(term in answer for term in ("确诊", "诊断为", "患有癫痫"))
    if name == "asks_for_channel_and_window":
        return "通道" in answer and any(term in answer for term in ("时间", "窗口"))
    if name == "asks_for_event_and_window":
        return any(term in answer for term in ("事件", "条件")) and any(term in answer for term in ("时间", "窗口"))
    if name == "mentions_no_events":
        return any(term in answer for term in ("没有事件", "无事件", "不存在事件"))
    if name == "mentions_missing_label":
        return any(term in answer for term in ("不存在", "没有", "未找到", "不匹配"))
    if name == "mentions_invalid_channel":
        return "通道" in answer and any(term in answer for term in ("无效", "不存在", "没有", "未知"))
    if name == "mentions_invalid_window":
        return bool(failed_codes.intersection({"INVALID_WINDOW", "INVALID_ARGUMENT"})) or any(
            term in answer for term in ("越界", "超出", "无效时间", "时间窗")
        )
    if name == "mentions_resource_failure":
        return "MODEL_RESOURCE_MISSING" in failed_codes or any(term in answer for term in ("资源", "权重", "不可用"))
    if name == "mentions_artifact_failure":
        return "ARTIFACT_NOT_FOUND" in failed_codes or "产物" in answer
    if name == "mentions_incompatible_profile":
        return any(term in answer for term in ("不兼容", "不支持", "不可用", "没有可用", "profile"))
    if name == "refuses_clinical_diagnosis":
        return any(term in answer for term in ("无法", "不能", "不支持", "不构成")) and "诊断" in answer
    if name == "mentions_unsupported":
        return any(term in answer for term in ("不支持", "无法", "不能", "没有"))
    return False


def evaluate_case(case, result):
    expected = case["expected"]
    events = result.execution_trace["events"]
    names = [item["tool_name"] for item in result.tool_results]
    successful_names = [
        item["tool_name"] for item in result.tool_results if item["success"]
    ]
    checks = {
        "stop_completed": result.stop_reason == "completed",
        "required_tools_attempted": all(name in names for name in expected["required_tools"]),
        "tools_allowed": all(name in expected["allowed_tools"] for name in names),
        "forbidden_tools_absent": all(name not in names for name in expected["forbidden_tools"]),
    }
    for name, arguments in expected.get("arguments", {}).items():
        matching = [event for event in events if event["tool_name"] == name]
        checks[f"arguments:{name}"] = bool(matching) and _tool_arguments_match(
            matching[-1]["arguments"], arguments
        )
    artifact_flow = expected.get("artifact_flow", [])
    flows = [artifact_flow] if artifact_flow and isinstance(artifact_flow[0], str) else artifact_flow
    for producer, consumer in flows:
        producer_result = next(
            (item for item in result.tool_results if item["tool_name"] == producer and item["success"]), None
        )
        consumer_event = next((item for item in events if item["tool_name"] == consumer), None)
        checks[f"artifact:{producer}->{consumer}"] = bool(
            producer_result and consumer_event
            and consumer_event["arguments"].get("artifact_id")
            == producer_result["data"].get("artifact_id")
        )
    if expected["outcome"] == "complete":
        checks["outcome"] = all(name in successful_names for name in expected["required_tools"])
    elif expected["outcome"] == "clarify":
        checks["outcome"] = not any(item["success"] for item in result.tool_results if item["tool_name"] in expected["forbidden_tools"])
    else:
        checks["outcome"] = result.stop_reason == "completed" and all(
            name not in successful_names for name in expected["forbidden_tools"]
        )
    for answer_check in expected["answer_checks"]:
        checks[f"answer:{answer_check}"] = _answer_check(answer_check, result)
    return checks


def run_suite(
    cases_payload, config, backend, model_path=None, real_client=None, case_ids=None
):
    budgets = cases_payload["budgets"]
    selected = [
        case for case in cases_payload["cases"]
        if (backend == "fake" or case["real_llm"])
        and (not case_ids or case["id"] in case_ids)
    ]
    shared = None
    if backend == "real":
        shared = BudgetedClient(
            real_client or OpenAICompatibleClient.from_env(),
            budgets["max_llm_requests"], budgets["max_total_tokens"],
        )
    outputs = []
    for case in selected:
        if shared and (
            shared.request_count >= budgets["max_llm_requests"]
            or shared.total_usage.get("total_tokens", 0) >= budgets["max_total_tokens"]
        ):
            outputs.append({
                "case_id": case["id"], "split": case["split"], "family": case["family"],
                "status": "not_run_budget_exhausted", "accepted": False,
            })
            continue
        context = build_case_context(case, config, model_path=model_path)
        client = shared if shared else BaselineProtocolFakeLLM(case)
        before_requests = getattr(client, "request_count", 0)
        before_tokens = getattr(client, "total_usage", {}).get("total_tokens", 0)
        result = EEGAgent(
            client, context,
            max_rounds=budgets["max_rounds_per_case"],
            max_tool_calls=budgets["max_tool_calls_per_case"],
        ).run(case["request"])
        checks = evaluate_case(case, result)
        outputs.append({
            "case_id": case["id"],
            "split": case["split"],
            "family": case["family"],
            "scenario": case["scenario"],
            "request": case["request"],
            "expected_outcome": case["expected"]["outcome"],
            "actual": result.to_dict(),
            "usage_delta": {
                "llm_requests": (getattr(client, "request_count", 0) - before_requests),
                "total_tokens": (
                    getattr(client, "total_usage", {}).get("total_tokens", 0) - before_tokens
                ),
                "cost": None,
            },
            "checks": checks,
            "accepted": all(checks.values()),
            "status": "completed",
        })
    summary = {
        "backend": backend,
        "case_count": len(outputs),
        "accepted_count": sum(item.get("accepted", False) for item in outputs),
        "failed_count": sum(not item.get("accepted", False) for item in outputs),
        "development": {
            "count": sum(item["split"] == "development" for item in outputs),
            "accepted": sum(item["split"] == "development" and item.get("accepted", False) for item in outputs),
        },
        "holdout": {
            "count": sum(item["split"] == "holdout" for item in outputs),
            "accepted": sum(item["split"] == "holdout" and item.get("accepted", False) for item in outputs),
        },
        "total_llm_requests": sum(item.get("usage_delta", {}).get("llm_requests", 0) for item in outputs),
        "total_tokens": sum(item.get("usage_delta", {}).get("total_tokens", 0) for item in outputs),
    }
    return {
        "schema_version": "1.0",
        "case_suite_hash": CASE_FILE_HASH,
        "backend": backend,
        "privacy": {
            "synthetic_only": True,
            "raw_eeg_sent_to_llm": False,
            "contains_credentials_headers_or_private_paths": False,
        },
        "budgets": budgets,
        "results": outputs,
        "summary": summary,
    }


def main(argv=None):
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Run frozen EEG Agent Baseline v1 cases")
    parser.add_argument("--backend", choices=("fake", "real"), default="fake")
    parser.add_argument("--cases", default=str(root / "config" / "agent_baseline_v1_cases.json"))
    parser.add_argument("--config", default=str(root / "config" / "baseline.json"))
    parser.add_argument("--model")
    parser.add_argument(
        "--case-id", action="append", dest="case_ids",
        help="Run only selected frozen case IDs; repeat for a bounded retest",
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    payload, digest = load_case_suite(args.cases)
    if digest != CASE_FILE_HASH:
        parser.error(f"case suite hash mismatch: {digest}")
    report = run_suite(
        payload, load_config(args.config), args.backend, model_path=args.model,
        case_ids=set(args.case_ids or ()),
    )
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["summary"], ensure_ascii=False, allow_nan=False))
    return 0 if report["summary"]["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
