"""Bounded synthetic-only validation of the instance-goal natural-language path."""

import argparse
import json
from pathlib import Path

from ...context import ExecutionContext
from ...demo import build_synthetic_event_record, build_synthetic_no_event_record
from ...executor import Executor
from ...llm import OpenAICompatibleClient
from ...pipeline import load_config
from ...profiles import EDF_NATIVE
from ...tools import build_default_registry
from .v2_validation import JournaledBudgetClient, PRIVATE_ROOT, PROJECT_ROOT, _inside_private_root
from .v3_agent import InstanceGoalEEGAgent
from .v3_application import render_auxiliary_evidence_note


CASES = (
    ("continuous_two_windows",
     "请检查这段 EEG 整段记录的信号质量，并分别计算 SYNTH-C1 通道 0 秒到 2 秒、2 秒到 4 秒两个窗口的绝对频带功率。请分别呈现两段结果，不要筛除试次。",
     build_synthetic_no_event_record, None),
    ("mixed_continuous_event",
     "请计算 SYNTH-C1 通道 0 秒到 2 秒的连续 EEG 绝对频带功率；对 stimulus 事件后 0 秒到 1 秒的试次测量质量，并计算同一事件试次的各条件绝对频带功率。不要筛除试次。",
     build_synthetic_event_record, None),
    ("clarification",
     "请计算 SYNTH-C1 通道的绝对频带功率。",
     build_synthetic_no_event_record, "补充时间窗：0 秒到 2 秒。"),
)


class ScenarioFakeClient:
    """Scripted protocol fixtures, not a substitute for real language understanding."""

    def __init__(self, case_id):
        self.case_id = case_id
        self.calls = 0

    def complete(self, messages, tools, tool_choice="auto"):
        self.calls += 1
        window = lambda start, end: {
            "channels": ["SYNTH-C1"], "start": start, "end": end,
        }
        quotes = lambda span: {"channels": "SYNTH-C1", "start": span, "end": span}
        event = {"labels": ["stimulus"], "tmin": 0, "tmax": 1}
        event_quotes = {"labels": "stimulus", "tmin": "0 秒到 1 秒", "tmax": "0 秒到 1 秒"}
        if self.case_id == "continuous_two_windows":
            goals = [
                {"instance_id": "g_quality", "capability": "record_quality", "parameters": {},
                 "request_quote": "整段记录的信号质量", "concept_quote": "信号质量",
                 "parameter_quotes": {}},
                {"instance_id": "g_early", "capability": "psd", "parameters": window(0, 2),
                 "request_quote": "0 秒到 2 秒", "concept_quote": "绝对频带功率",
                 "parameter_quotes": quotes("0 秒到 2 秒")},
                {"instance_id": "g_late", "capability": "psd", "parameters": window(2, 4),
                 "request_quote": "2 秒到 4 秒", "concept_quote": "绝对频带功率",
                 "parameter_quotes": quotes("2 秒到 4 秒")},
            ]
        elif self.case_id == "mixed_continuous_event":
            goals = [
                {"instance_id": "g_continuous", "capability": "psd", "parameters": window(0, 2),
                 "request_quote": "连续 EEG 绝对频带功率", "concept_quote": "绝对频带功率",
                 "parameter_quotes": quotes("0 秒到 2 秒")},
                {"instance_id": "g_quality", "capability": "epoch_quality", "parameters": event,
                 "request_quote": "stimulus 事件后 0 秒到 1 秒的试次测量质量",
                 "concept_quote": "测量质量", "parameter_quotes": event_quotes},
                {"instance_id": "g_event_power", "capability": "event_bandpower", "parameters": event,
                 "request_quote": "同一事件试次的各条件绝对频带功率",
                 "concept_quote": "绝对频带功率", "parameter_quotes": event_quotes},
            ]
        elif self.calls == 1:
            goals = [{"instance_id": "g_psd", "capability": "psd",
                      "parameters": {"channels": ["SYNTH-C1"]},
                      "request_quote": "绝对频带功率", "concept_quote": "绝对频带功率",
                      "parameter_quotes": {"channels": "SYNTH-C1"}}]
        else:
            goals = [{"instance_id": "g_psd", "capability": "psd",
                      "parameters": window(0, 2), "request_quote": "绝对频带功率",
                      "concept_quote": "绝对频带功率",
                      "parameter_quotes": quotes("0 秒到 2 秒") }]
        payload = {"goals": goals, "forbidden_operations": ["selection"]
                   if self.case_id != "clarification" else [], "unsupported_requests": []}
        return {"tool_calls": [{"function": {"name": "submit_eeg_goals",
                 "arguments": json.dumps(payload, ensure_ascii=False)}}]}


def run_suite(*, real=False, output=None, max_requests=8, max_total_tokens=24000):
    destination = _inside_private_root(output or PRIVATE_ROOT / "point1_v3_validation.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shared = None
    if real:
        client = OpenAICompatibleClient.from_env()
        client.max_retries = 0
        shared = JournaledBudgetClient(
            client, destination.with_suffix(".responses.jsonl"),
            max_requests=max_requests, max_total_tokens=max_total_tokens)
    config = load_config(PROJECT_ROOT / "config" / "baseline.json")
    records = []
    for case_id, request, factory, clarification in CASES:
        context = ExecutionContext(factory(), EDF_NATIVE, Executor(build_default_registry(), config),
                                   task_id="v3-" + case_id)
        agent = InstanceGoalEEGAgent(shared if real else ScenarioFakeClient(case_id), context)
        first = agent.run(request)
        final = agent.resume(clarification) if clarification and first["status"] == "clarification_required" else first
        entry = {"case_id": case_id, "request": request, "first_status": first["status"],
                 "first_result": first, "final_result": final}
        if final["status"] == "completed":
            entry["application_note"] = render_auxiliary_evidence_note(final["evidence_bundle"])
        records.append(entry)
        # Persist each case before another paid call; never overwrite an initial failure.
        destination.write_text(json.dumps({"synthetic_only": True, "real_llm": real,
                                           "records": records}, ensure_ascii=False,
                                          indent=2, allow_nan=False) + "\n", encoding="utf-8")
    usage = {} if shared is None else dict(shared.total_usage)
    result = {"synthetic_only": True, "real_llm": real,
              "requested_model": None if shared is None else shared.model,
              "response_models": [] if shared is None else list(shared.client.response_models),
              "request_count": sum(2 if item["case_id"] == "clarification" and
                                   item["first_status"] == "clarification_required" else 1
                                   for item in records) if shared is None else shared.request_count,
              "usage": usage, "records": records}
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2,
                                      allow_nan=False) + "\n", encoding="utf-8")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real", action="store_true")
    parser.add_argument("--output")
    parser.add_argument("--max-requests", type=int, default=8)
    parser.add_argument("--max-total-tokens", type=int, default=24000)
    args = parser.parse_args(argv)
    result = run_suite(real=args.real, output=args.output,
                       max_requests=args.max_requests, max_total_tokens=args.max_total_tokens)
    print(json.dumps({"synthetic_only": True, "real_llm": args.real,
                      "statuses": [(item["case_id"], item["first_status"],
                                    item["final_result"]["status"]) for item in result["records"]],
                      "request_count": result["request_count"],
                      "total_tokens": result["usage"].get("total_tokens"),
                      "details_private": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
