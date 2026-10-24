"""Frozen cross-family development checks; synthetic EEG only.

The case requests and expected goals are specified before any model response.
Fake payloads exercise the protocol, not language understanding. Real responses
are journaled privately and never modify the expected goals.
"""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from ...context import ExecutionContext
from ...demo import (build_synthetic_event_record, build_synthetic_no_event_record,
                     build_synthetic_tuev_record)
from ...executor import Executor
from ...llm import OpenAICompatibleClient
from ...pipeline import load_config
from ...profiles import EDF_NATIVE, TUEV_BIPOLAR_22
from ...tools import build_default_registry
from .v2_validation import JournaledBudgetClient, PRIVATE_ROOT, PROJECT_ROOT, _inside_private_root
from .v3_agent import InstanceGoalEEGAgent


def _goal(instance_id, capability, parameters, anchor, concept, quotes):
    return {"instance_id": instance_id, "capability": capability, "parameters": parameters,
            "request_quote": anchor, "concept_quote": concept, "parameter_quotes": quotes}


def _case(case_id, request, record_factory, profile, expected, payloads,
          clarification=None, needs_model=False):
    return {"id": case_id, "request": request, "record_factory": record_factory,
            "profile": profile, "expected": expected, "payloads": payloads,
            "clarification": clarification, "needs_model": needs_model}


def _payload(goals, forbidden=(), unsupported=()):
    return {"goals": goals, "forbidden_operations": list(forbidden),
            "unsupported_requests": list(unsupported)}


EVENT_STIM = {"labels": ["stimulus"], "tmin": 0, "tmax": 1}
EVENT_CONTROL = {"labels": ["control"], "tmin": 0, "tmax": 1}
STIM_QUOTES = {"labels": "stimulus", "tmin": "0 秒到 1 秒", "tmax": "0 秒到 1 秒"}
CONTROL_QUOTES = {"labels": "control", "tmin": "0 秒到 1 秒", "tmax": "0 秒到 1 秒"}

CASES = (
    _case("C1_continuous",
          "请报告这段脑电的采样率与通道信息，并测量 SYNTH-C1 在 0 秒到 2 秒的幅值和绝对频带功率。",
          build_synthetic_no_event_record, EDF_NATIVE,
          (("record_info", {}),
           ("amplitude", {"channels": ["SYNTH-C1"], "start": 0, "end": 2}),
           ("psd", {"channels": ["SYNTH-C1"], "start": 0, "end": 2})),
          (_payload([
              _goal("info", "record_info", {}, "采样率与通道信息", "采样率与通道信息", {}),
              _goal("amp", "amplitude", {"channels": ["SYNTH-C1"], "start": 0, "end": 2},
                    "0 秒到 2 秒的幅值", "幅值",
                    {"channels": "SYNTH-C1", "start": "0 秒到 2 秒", "end": "0 秒到 2 秒"}),
              _goal("power", "psd", {"channels": ["SYNTH-C1"], "start": 0, "end": 2},
                    "绝对频带功率", "绝对频带功率",
                    {"channels": "SYNTH-C1", "start": "0 秒到 2 秒", "end": "0 秒到 2 秒"}),
          ]),)),
    _case("C2_event",
          "请汇总 stimulus 事件后 0 秒到 1 秒的试次数，测量这些试次的质量并计算各条件绝对频带功率；只测量，不筛除试次。",
          build_synthetic_event_record, EDF_NATIVE,
          (("epoch_summary", EVENT_STIM), ("epoch_quality", EVENT_STIM),
           ("event_bandpower", EVENT_STIM)),
          (_payload([
              _goal("summary", "epoch_summary", EVENT_STIM, "stimulus 事件后 0 秒到 1 秒的试次数",
                    "试次数", STIM_QUOTES),
              _goal("quality", "epoch_quality", EVENT_STIM, "这些试次的质量", "质量", STIM_QUOTES),
              _goal("power", "event_bandpower", EVENT_STIM, "这些试次的质量并计算各条件绝对频带功率",
                    "绝对频带功率", STIM_QUOTES),
          ], ("selection",)),)),
    _case("C3_model",
          "对已验证双极配置的 FP1-F7 导联 0 秒到 1 秒片段，调用现有癫痫/非癫痫研究模型检查输出；这不是临床诊断。",
          build_synthetic_tuev_record, TUEV_BIPOLAR_22,
          (("seizure_detection", {"channels": ["FP1-F7"], "start": 0, "end": 1}),),
          (_payload([
              _goal("model", "seizure_detection", {"channels": ["FP1-F7"], "start": 0, "end": 1},
                    "FP1-F7 导联 0 秒到 1 秒片段，调用现有癫痫/非癫痫研究模型",
                    "癫痫/非癫痫", {"channels": "FP1-F7", "start": "0 秒到 1 秒",
                                    "end": "0 秒到 1 秒"}),
          ]),), needs_model=True),
    _case("C4_cross_family",
          "测量 SYNTH-C2 在 1 秒到 3 秒的连续 EEG 幅值；另外汇总 control 事件后 0 秒到 1 秒的试次数，并计算这些试次的各条件绝对频带功率。不得筛除任何试次。",
          build_synthetic_event_record, EDF_NATIVE,
          (("amplitude", {"channels": ["SYNTH-C2"], "start": 1, "end": 3}),
           ("epoch_summary", EVENT_CONTROL), ("event_bandpower", EVENT_CONTROL)),
          (_payload([
              _goal("amp", "amplitude", {"channels": ["SYNTH-C2"], "start": 1, "end": 3},
                    "SYNTH-C2 在 1 秒到 3 秒的连续 EEG 幅值", "幅值",
                    {"channels": "SYNTH-C2", "start": "1 秒到 3 秒", "end": "1 秒到 3 秒"}),
              _goal("summary", "epoch_summary", EVENT_CONTROL, "control 事件后 0 秒到 1 秒的试次数",
                    "试次数", CONTROL_QUOTES),
              _goal("power", "event_bandpower", EVENT_CONTROL, "这些试次的各条件绝对频带功率",
                    "绝对频带功率", CONTROL_QUOTES),
          ], ("selection",)),)),
    _case("C5_clarification", "请计算 SYNTH-C2 导联的绝对频带功率。",
          build_synthetic_no_event_record, EDF_NATIVE,
          (("psd", {"channels": ["SYNTH-C2"], "start": 1, "end": 3}),),
          (_payload([_goal("power", "psd", {"channels": ["SYNTH-C2"]}, "绝对频带功率",
                           "绝对频带功率", {"channels": "SYNTH-C2"})]),
           _payload([_goal("power", "psd", {"channels": ["SYNTH-C2"], "start": 1, "end": 3},
                           "绝对频带功率", "绝对频带功率",
                           {"channels": "SYNTH-C2", "start": "1 秒到 3 秒",
                            "end": "1 秒到 3 秒"})])),
          clarification="窗口是 1 秒到 3 秒。"),
    _case("C6_no_events",
          "对无事件记录，计算 stimulus 事件后 0 秒到 1 秒的条件频带功率。",
          build_synthetic_no_event_record, EDF_NATIVE, (),
          (_payload([], unsupported=("当前记录无事件，无法计算事件条件频带功率",)),)),
    _case("C7_unsupported", "给出完整 ERP 波形及儿童 ASD 诊断。",
          build_synthetic_event_record, EDF_NATIVE, (),
          (_payload([], unsupported=("完整 ERP 波形", "儿童 ASD 诊断")),)),
)


class CaseFakeClient:
    def __init__(self, payloads):
        self.payloads = iter(payloads)

    def complete(self, messages, tools, tool_choice="auto"):
        return {"tool_calls": [{"function": {"name": "submit_eeg_goals",
                "arguments": json.dumps(next(self.payloads), ensure_ascii=False)}}]}


def run_case(case, client, config, model_path=None):
    resources = {"seizure_model": model_path} if case["needs_model"] and model_path else {}
    context = ExecutionContext(case["record_factory"](), case["profile"],
                               Executor(build_default_registry(), config, resources),
                               "acceptance-" + case["id"])
    agent = InstanceGoalEEGAgent(client, context)
    initial = agent.run(case["request"])
    final = (agent.resume(case["clarification"])
             if case["clarification"] and initial["status"] == "clarification_required"
             else initial)
    bundle = final["evidence_bundle"]
    actual = tuple((item["capability"], item["parameters"]) for item in bundle["goals"])
    return {"case_id": case["id"], "request": case["request"],
            "expected_goals": [{"capability": name, "parameters": parameters}
                               for name, parameters in case["expected"]],
            "initial_status": initial["status"], "initial_result": initial,
            "final_result": final,
            "observed_goals": [{"capability": name, "parameters": parameters}
                               for name, parameters in actual],
            "goal_set_matches_predeclared": actual == case["expected"] if final["status"] == "completed" else None,
            "tool_count": len(final["tool_results"])}


def run_suite(*, real=False, output=None, max_requests=7, max_total_tokens=18000,
              model_path=None, case_ids=None):
    label = "real" if real else "fake"
    filename = f"multitask_acceptance_{label}_{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}.json"
    destination = _inside_private_root(output or PRIVATE_ROOT / filename)
    if destination.exists():
        raise FileExistsError("Refusing to overwrite a previous acceptance run")
    destination.parent.mkdir(parents=True, exist_ok=True)
    config = load_config(PROJECT_ROOT / "config" / "baseline.json")
    shared = None
    if real:
        raw = OpenAICompatibleClient.from_env()
        raw.max_retries = 0
        shared = JournaledBudgetClient(raw, destination.with_suffix(".responses.jsonl"),
                                       max_requests=max_requests,
                                       max_total_tokens=max_total_tokens)
    model_path = model_path or os.environ.get("EEG_HARNESS_MODEL_PATH")
    selected = tuple(CASES if case_ids is None else
                     (case for case in CASES if case["id"] in case_ids))
    if case_ids is not None and {case["id"] for case in selected} != set(case_ids):
        raise ValueError("Unknown acceptance case ID")
    observations = []
    for case in selected:
        if real and case["id"] == "C7_unsupported":
            continue  # Paid scope is C1-C6; C7 remains deterministic-only.
        if real and shared.request_count >= max_requests:
            observations.append({"case_id": case["id"], "status": "not_run_budget"})
            break
        client = shared if real else CaseFakeClient(case["payloads"])
        entry = run_case(case, client, config, model_path)
        observations.append(entry)
        destination.write_text(json.dumps({"synthetic_only": True, "real_llm": real,
                                           "records": observations}, ensure_ascii=False,
                                          indent=2, allow_nan=False) + "\n", encoding="utf-8")
    result = {"synthetic_only": True, "real_llm": real,
              "requested_model": None if shared is None else shared.model,
              "response_models": [] if shared is None else list(shared.client.response_models),
              "request_count": sum(2 if case["id"] == "C5_clarification" else 1
                                   for case in selected) if shared is None else shared.request_count,
              "usage": {} if shared is None else dict(shared.total_usage),
              "records": observations}
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2,
                                      allow_nan=False) + "\n", encoding="utf-8")
    return result, destination


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real", action="store_true")
    parser.add_argument("--output")
    parser.add_argument("--max-requests", type=int, default=7)
    parser.add_argument("--max-total-tokens", type=int, default=18000)
    parser.add_argument("--cases", nargs="+", help="Selected frozen case IDs; defaults to all")
    args = parser.parse_args(argv)
    result, destination = run_suite(real=args.real, output=args.output,
                                    max_requests=args.max_requests,
                                    max_total_tokens=args.max_total_tokens,
                                    case_ids=args.cases)
    print(json.dumps({"synthetic_only": True, "real_llm": args.real,
                      "statuses": [(item["case_id"], item.get("initial_status"),
                                    item.get("final_result", {}).get("status"),
                                    item.get("goal_set_matches_predeclared"))
                                   for item in result["records"]],
                      "request_count": result["request_count"],
                      "total_tokens": result["usage"].get("total_tokens"),
                      "private_output": str(destination.relative_to(PROJECT_ROOT))},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
