"""Deterministic natural-language protocol comparison for Issue #4."""

from dataclasses import dataclass
import json

from .agent import EEGAgent
from .llm import DeterministicComparisonFakeLLM
from .planning import ConstrainedPlanRunner
from .planning_agent import NaturalLanguageGoalInterpreter
from .planning_evaluation import _expert_with_recovery, make_synthetic_context
from .pipeline import load_config


@dataclass(frozen=True)
class NLCase:
    case_id: str
    text: str
    variant: str
    expected_goal: str
    expected_tool: str | None
    expected: str


CASES = (
    NLCase("basic_info", "给出基础信息", "native_events", "tool", "record_info", "complete"),
    NLCase("window", "分析第一个通道的窗口幅值", "native_events", "tool", "amplitude", "complete"),
    NLCase("bandpower", "计算频带功率", "native_events", "tool", "psd", "complete"),
    NLCase("event", "分析事件频带功率", "native_events", "event_bandpower", "event_bandpower", "complete"),
    NLCase("no_annotations", "分析事件频带功率", "native_no_events", "event_bandpower", "event_bandpower", "reject"),
    NLCase("model_incompatible", "调用癫痫模型", "native_events", "tool", "seizure_detection", "reject"),
    NLCase("model_resource_missing", "调用癫痫模型", "tuev", "tool", "seizure_detection", "reject"),
    NLCase("multiple", "组合执行：先幅值再事件", "native_events", "sequence", None, "complete"),
    NLCase("unsupported_diagnosis", "请给出临床诊断", "native_events", "clinical_diagnosis", None, "reject"),
)


def _task_matches(case, task):
    if task.goal != case.expected_goal:
        return False
    if case.expected_tool is None or task.goal != "tool":
        return True
    return task.arguments.get("tool_name") == case.expected_tool


def _native_intent_matches(case, result):
    names = [item["tool_name"] for item in result.tool_results]
    if case.expected_goal == "sequence":
        return "amplitude" in names and "event_bandpower" in names
    if case.expected_goal == "clinical_diagnosis":
        return not names and "诊断" in result.final_answer
    if case.expected_tool == "seizure_detection" and not names:
        return "seizure_detection" in result.final_answer
    return case.expected_tool in names


def _native_status(case, result, intent_correct):
    if not intent_correct:
        return "intent_failed"
    failures = [item for item in result.tool_results if not item["success"]]
    no_events = any(
        item["tool_name"] == "list_events"
        and item["success"] and item["data"]["event_count"] == 0
        for item in result.tool_results
    )
    rejected = failures or no_events or (
        case.expected == "reject" and result.tool_calls == 0
    )
    return "rejected" if rejected else "completed"


def run_fake_nl_comparison(config_path="config/baseline.json"):
    config = load_config(config_path)
    rows = []
    for strategy in ("native_tool_calling", "strong_expert", "constrained_planner"):
        for case in CASES:
            context = make_synthetic_context(
                case.variant, f"nl-{strategy}-{case.case_id}", config
            )
            client = DeterministicComparisonFakeLLM()
            if strategy == "native_tool_calling":
                result = EEGAgent(client, context, max_rounds=6, max_tool_calls=8).run(case.text)
                intent_correct = _native_intent_matches(case, result)
                status = _native_status(case, result, intent_correct)
                calls = result.tool_calls
                llm_calls = len(client.calls)
                error_codes = [
                    item["error"]["code"] for item in result.tool_results if item["error"]
                ]
            else:
                parsed = NaturalLanguageGoalInterpreter(client).interpret(case.text, context)
                intent_correct = bool(parsed.success and _task_matches(case, parsed.task))
                if not parsed.success or not intent_correct:
                    status, calls, error_codes = "intent_failed", 0, [
                        parsed.error_code or "INTENT_MISMATCH"
                    ]
                elif strategy == "strong_expert":
                    output = _expert_with_recovery(parsed.task, context)
                    status = output["status"]
                    calls = output["tool_calls"]
                    error_codes = [
                        item["error"]["code"]
                        for item in output["tool_results"] if item["error"]
                    ]
                else:
                    output = ConstrainedPlanRunner(context, max_replans=1).run(parsed.task)
                    status = output.status
                    calls = len(output.tool_results)
                    error_codes = [
                        item["error"]["code"]
                        for item in output.tool_results if item["error"]
                    ]
                llm_calls = len(client.calls)
            outcome_correct = (
                (case.expected == "complete" and status == "completed")
                or (case.expected == "reject" and status.startswith("reject"))
            )
            rows.append({
                "strategy": strategy,
                "case_id": case.case_id,
                "input_kind": "human_authored_template",
                "intent_correct": intent_correct,
                "status": status,
                "expected": case.expected,
                "outcome_correct": outcome_correct,
                "tool_calls": calls,
                "llm_calls": llm_calls,
                "error_codes": error_codes,
            })
    summary = {}
    for strategy in ("native_tool_calling", "strong_expert", "constrained_planner"):
        selected = [item for item in rows if item["strategy"] == strategy]
        summary[strategy] = {
            "intent_accuracy": sum(item["intent_correct"] for item in selected) / len(selected),
            "outcome_accuracy": sum(item["outcome_correct"] for item in selected) / len(selected),
            "tool_calls": sum(item["tool_calls"] for item in selected),
            "llm_calls": sum(item["llm_calls"] for item in selected),
        }
    payload = {
        "suite_version": "fake-nl-1.0",
        "case_count": len(CASES),
        "backend": "deterministic human-authored template simulator",
        "real_llm": "not tested by this function",
        "summary": summary,
        "outcomes": rows,
        "limits": [
            "Fake templates are software tests, not evidence of natural-language model quality",
            "Native and structured-goal modes use strategy-specific output prompts",
        ],
    }
    json.dumps(payload, ensure_ascii=False, allow_nan=False)
    return payload
