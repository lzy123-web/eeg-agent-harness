"""Issue52 offline paired mechanism replay and actual-wire preflight.

All plans/actions below are explicit controlled interventions. They never enter
method modules and are NOT evidence of model autonomy or request success rate.
No external model client is imported or constructed. Old budgets are not read.
"""
import argparse
from collections import Counter
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from ..task_plan_agent import TaskPlanEEGAgent
from .task_memory import PROJECT_ROOT, synthetic_records
from .task_memory_v2 import independent_oracle

SPEC = PROJECT_ROOT / "config" / "point1_working_memory_issue52.json"
ARMS = ("A", "B", "C")
IMPLEMENTED_CASES = ("T01", "T02", "T03", "T04", "T05", "T06", "T07", "T08")


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf8")


def protocol():
    return json.loads(SPEC.read_text(encoding="utf8"))


def records_for(partition="development"):
    records = synthetic_records()
    if partition == "confirmation":
        scales = protocol()["synthetic_data"]["confirmation_scales"]
        records = {alias: replace(record, data=record.data * scales[alias],
            source=f"synthetic://issue52-confirmation-{alias}") for alias, record in records.items()}
    elif partition != "development":
        raise ValueError("Unknown deterministic partition")
    return records


def window(start=0, end=2):
    return {"channels": ["SYNTH-C1"], "start": start, "end": end}


def event_scope():
    return {"labels": ["stimulus"], "tmin": 0, "tmax": 1.25}


def ref(task, key, *, fields=None, level="result", revision=None):
    row = {"task_id": task, "key": key, "level": level, "fields": fields or []}
    if revision is not None:
        row["revision"] = revision
    return row


def delivery(key, capability, record="A", scope=None, refs=None, acceptance=None):
    return {"key": key, "capability": capability, "record": record,
        "scope": scope or {}, "input_refs": refs or [], "acceptance_rule": acceptance or []}


def node(ident, goal, outputs, dependencies=None):
    return {"task_id": ident, "goal": goal, "dependencies": dependencies or [],
        "required_outputs": outputs}


def finish(status="completed", unresolved=None):
    args = {"status": status, "answer": "受控离线机制回放；本段固定文本不是模型自主科学回答，不参与回答正确率评分。"}
    if unresolved:
        args["unresolved"] = unresolved
    return "finish_task", args


def payload(messages):
    return json.loads(messages[1]["content"])


def comparison_from_actual_input(messages):
    rows = payload(messages)["dependency_evidence"]
    evidence = [row.get("evidence") for row in rows]
    if len(evidence) != 2 or any(not e for e in evidence):
        raise AssertionError("Two actually presented upstream results required")
    return "compare_results", {"left_result": evidence[0]["task_id"],
        "right_result": evidence[1]["task_id"], "left_path": ["SYNTH-C1", "alpha"],
        "right_path": ["SYNTH-C1", "alpha"]}


def process_or_quality(messages):
    current = payload(messages)
    presented_process = any(row.get("process") for row in current.get("dependency_evidence", []))
    if not presented_process and not current.get("restored_trajectories"):
        return "read_dependency", {"task_id": "epochs", "key": "ep", "level": "process"}
    return "epoch_quality", {}


def controlled_steps(case_id):
    """Fixed mechanism interventions, only this offline runner knows the plan."""
    alpha = ["SYNTH-C1", "alpha"]
    if case_id == "T01":
        nodes = [node("basic", "基础信号两个指标", [delivery("rms", "amplitude", scope=window()),
            delivery("alpha", "psd", scope=window())])]
        return [[("plan_tasks", {"nodes": nodes}), ("amplitude", {}), ("psd", {}), finish()]]
    if case_id == "T02":
        nodes = [node("windows", "两个连续窗口", [delivery("early", "psd", scope=window()),
            delivery("late", "psd", scope=window(4, 6))]),
            node("comparison", "两个窗口的描述性比较", [delivery("change", "compare_results", refs=[
                ref("windows", "early", fields=[alpha]), ref("windows", "late", fields=[alpha])])], ["windows"])]
        return [[("plan_tasks", {"nodes": nodes}), ("psd", window()),
            ("psd", window(4, 6)), comparison_from_actual_input, finish()]]
    if case_id == "T03":
        nodes = [node("continuous", "记录B连续信号", [delivery("rms", "amplitude", "B", window(2, 4))]),
            node("epochs", "待补窗的记录A事件", [delivery("ep", "create_epochs", scope={"labels": ["stimulus"]})]),
            node("power", "原试次的theta功率", [delivery("power", "event_bandpower", refs=[ref("epochs", "ep")])], ["epochs"])]
        return [[("plan_tasks", {"nodes": nodes}), ("amplitude", {}),
            ("wait_node", {"task_id": "epochs", "reason": "缺少事件相对窗口"}),
            finish("clarification_required", ["请提供事件相对窗口；记录B结果已保留"])],
            [("revise_plan", {"task_id": "epochs", "updates": {"required_outputs": [delivery("ep", "create_epochs", scope=event_scope())]},
                "reason": "用户补充事件相对窗口"}), ("create_epochs", {}), ("event_bandpower", {}), finish()]]
    if case_id == "T04":
        nodes = [node("records", "两个记录的独立范围", [delivery("a", "amplitude", "A", window()),
            delivery("b", "amplitude", "B", window(2, 4))])]
        return [[("plan_tasks", {"nodes": nodes}), ("amplitude", {"record": "A", **window()}),
            ("amplitude", {"record": "B", **window(2, 4)}), finish()]]
    if case_id == "T05":
        nodes = [node("alpha", "记录A频带分析", [delivery("alpha", "psd", scope=window())]),
            node("b", "记录B幅值", [delivery("rms", "amplitude", "B", window(2, 4))])]
        comparison = node("comparison", "保留旧版本并比较", [delivery("change", "compare_results", refs=[
            ref("alpha", "alpha", fields=[alpha], revision=1), ref("alpha", "alpha", fields=[alpha])])], ["alpha"])
        return [[("plan_tasks", {"nodes": nodes}), ("psd", {}), ("amplitude", {}), finish()],
            [("revise_plan", {"task_id": "alpha", "updates": {"required_outputs": [delivery("alpha", "psd", scope=window(4, 6))]},
                "reason": "用户合法修订窗口，保留旧结果"}), ("plan_tasks", {"nodes": [comparison]}),
                ("psd", {"request_span": "把记录A的分析窗口修订为4到6秒"}), comparison_from_actual_input, finish()]]
    if case_id == "T06":
        quote = "至少4个实际有效试次才允许把该任务标为满足条件"
        rule = {"path": ["valid_epoch_count"], "op": "gte", "value": 4, "source": quote}
        nodes = [node("epochs", "实际事件试次", [delivery("ep", "create_epochs", scope=event_scope())]),
            node("count", "核对至少4个试次条件", [delivery("count", "epoch_summary", refs=[ref("epochs", "ep")], acceptance=[rule])], ["epochs"])]
        return [[("plan_tasks", {"nodes": nodes}), ("create_epochs", {}), ("epoch_summary", {}),
            ("check_deliveries", {"task_id": "count"}), ("wait_node", {"task_id": "count", "reason": "实际3个试次，小于用户要求4个，不扩大范围"}),
            finish("partial", ["实际有效试次3个，不满足至少4个条件；没有擅自扩大范围"])]]
    if case_id in {"T07", "T08"}:
        nodes = [node("epochs", "事件试次", [delivery("ep", "create_epochs", scope=event_scope())]),
            node("power", "事件功率", [delivery("power", "event_bandpower", refs=[ref("epochs", "ep")])], ["epochs"])]
        steps = [("plan_tasks", {"nodes": nodes}), ("create_epochs", {}), ("event_bandpower", {})]
        if case_id == "T07":
            nodes.insert(0, node("continuous", "记录A历史RMS", [delivery("rms", "amplitude", scope=window())]))
            steps.insert(1, ("amplitude", {}))
        steps.append(finish())
        quality = node("quality", "沿用原试次追加质量", [delivery("quality", "epoch_quality", refs=[
            ref("epochs", "ep", level="process" if case_id == "T08" else "result")])], ["epochs"])
        follow = [("plan_tasks", {"nodes": [quality]})]
        if case_id == "T07":
            follow += [("read_dependency", {"task_id": "continuous", "key": "rms", "level": "result", "fields": [["SYNTH-C1", "rms"]]}),
                ("epoch_quality", {}),
                ("read_dependency", {"task_id": "power", "key": "power", "level": "result",
                    "fields": [["conditions", "stimulus", "channels", "SYNTH-C2", "theta"]]})]
        else:
            follow += [process_or_quality]
            # Optional second controlled decision only if first was a read. The
            # client branches on the ACTUAL previous action, not comparison arm.
            follow += ["quality_if_not_executed"]
        follow.append(finish())
        return [steps, follow]
    raise ValueError("Unknown offline case")


class ControlledPlanClient:
    """Scripted intervention with real observed handles; never a model proxy."""
    model = "offline-controlled-decisions-not-an-LLM"
    total_usage = {}
    finish_reasons = []

    def __init__(self, turns, max_output_tokens=2200):
        self.turn_actions = deepcopy(turns)
        self.actions = []
        self.control_errors = []
        self.seen = []
        self.request_count = 0
        self.max_output_tokens = max_output_tokens
        self.last_action = None

    def begin_controlled_turn(self, index):
        self.actions = list(self.turn_actions[index])

    def complete(self, messages, tools, **kwargs):
        if not self.actions:
            self.control_errors.append({"error": "controlled_schedule_exhausted", "after_decisions": self.request_count})
            raise RuntimeError("Controlled local action schedule exhausted; not an external model failure")
        action = self.actions.pop(0)
        # A failed controlled action is preserved. Do not continue a hand-written
        # schedule as though its prerequisite succeeded or consume future turns.
        latest = next((m for m in reversed(messages) if m.get("role") == "tool"), None)
        if latest:
            observation = json.loads(latest["content"])
            if observation.get("success") is False:
                code = (observation.get("error") or {}).get("code", "ACTION_REJECTED")
                self.control_errors.append({"error": "controlled_schedule_stopped_after_actual_rejection", "code": code})
                action = finish("partial", [f"实际共享接口拒绝：{code}；未执行依赖该结果的后续动作"])
                self.actions.clear()
        if action == "quality_if_not_executed":
            action = self.actions.pop(0) if self.last_action == "epoch_quality" else ("epoch_quality", {})
        if callable(action):
            action = action(messages)
        name, arguments = action
        self.request_count += 1
        self.last_action = name
        wire = {"model": "offline-placeholder-for-wire-measurement", "messages": messages,
                "tools": tools, "max_tokens": self.max_output_tokens, **kwargs}
        self.seen.append({"decision": self.request_count, "messages": deepcopy(messages),
            "tools": deepcopy(tools), "wire_bytes": len(encoded(wire)),
            "conservative_token_reservation": len(encoded(wire)) + self.max_output_tokens,
            "controlled_action": {"name": name, "arguments": deepcopy(arguments)}})
        return {"role": "assistant", "content": None, "tool_calls": [{
            "id": f"offline-{self.request_count}", "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}}]}


def audit_entries(store):
    """Numerical oracle from raw samples, not controller completion booleans."""
    rows = []
    for entry in store.entries:
        step = {"capability": entry.capability, "parameters": entry.parameters}
        candidates = []
        if entry.capability == "amplitude":
            candidates = [([channel, "rms"], entry.result[channel]["rms"]) for channel in entry.parameters["channels"]]
        elif entry.capability == "psd":
            candidates = [([channel, band], entry.result[channel][band]) for channel in entry.parameters["channels"] for band in ("alpha", "theta")]
        elif entry.capability == "event_bandpower":
            candidates = [(["conditions", label, "channels", channel, band], bands[band])
                for label, condition in entry.result["conditions"].items()
                for channel, bands in condition["channels"].items() for band in ("alpha", "theta")]
        elif entry.capability in {"epoch_summary", "create_epochs"}:
            step = {"capability": "epoch_summary", "parameters": entry.parameters}
            candidates = [(["valid_epoch_count"], entry.result["valid_epoch_count"])]
        for field, actual in candidates:
            expected = independent_oracle(store.records[entry.record], step, field)
            passed = actual == expected if entry.capability in {"epoch_summary", "create_epochs"} else bool(np.isclose(float(actual), expected, rtol=.005, atol=1e-13))
            rows.append({"result_id": entry.task_id, "record": entry.record, "capability": entry.capability,
                "scope": deepcopy(entry.parameters), "field": field, "actual": actual,
                "independent_expected": expected, "passed": passed})
    return rows


def audit_comparisons(controller):
    rows = []
    for comparison in controller.comparisons:
        operands = []
        for operand in comparison["operands"]:
            entry = controller.store.find_entry(operand["result_id"])
            operands.append(independent_oracle(controller.store.records[entry.record],
                {"capability": entry.capability, "parameters": entry.parameters}, operand["field"]))
        a, b = operands
        for field, expected in (("right_minus_left", b-a), ("right_divided_by_left", b/a if a else None)):
            actual = comparison[field]
            rows.append({"comparison_id": comparison["comparison_id"], "capability": "compare_results",
                "operands": deepcopy(comparison["operands"]), "field": [field], "actual": actual,
                "independent_expected": expected,
                "passed": actual is None if expected is None else bool(np.isclose(actual, expected, rtol=.005, atol=1e-13))})
    return rows


def run_case(case_id, arm, *, partition="development", actions=None):
    spec = protocol()
    case = next(c for c in spec["cases"] if c["id"] == case_id)
    client = ControlledPlanClient(controlled_steps(case_id) if actions is None else actions, spec["model_settings"]["max_output_tokens"])
    records = records_for(partition)
    options = spec["agent_settings"]
    ident = hashlib.sha256(encoded([case_id, arm, partition])).hexdigest()[:12]
    agent = TaskPlanEEGAgent(client, records, arm=arm,
        session_id=f"offline-{ident}", max_rounds=options["max_rounds_per_turn"],
        max_tool_calls=options["max_tool_calls_per_turn"], timeout_seconds=options["timeout_seconds"],
        max_context_bytes=options["max_context_bytes"])
    results = []
    started = time.perf_counter()
    for index, request in enumerate(case["requests"]):
        client.begin_controlled_turn(index)
        result = agent.run(request) if index == 0 else agent.continue_run(request)
        results.append(result.to_dict())
        if result.stop_reason in {"llm_error", "no_progress", "round_limit", "tool_call_limit", "context_capacity", "partial"}:
            break
    store = agent.working_memory.store
    oracle = audit_entries(store) + audit_comparisons(agent.working_memory)
    wire = [r["conservative_token_reservation"] for r in client.seen]
    executor_events = [(alias, event) for alias, context in store.contexts.items() for event in context.trace.events]
    signatures = Counter(encoded([alias, event.tool_name, event.arguments]) for alias, event in executor_events)
    return {"case_id": case_id, "arm": arm, "partition": partition,
        "kind": "controlled_plan_and_actions_original_EEG_tools_not_autonomy",
        "record_sha256": {k: hashlib.sha256(v.data.tobytes()).hexdigest() for k, v in records.items()},
        "user_requests_sent": case["requests"][:len(results)], "raw_agent_results": results,
        "decisions": client.seen, "oracle": oracle,
        "metrics": {"external_completions": 0, "actual_api_tokens": 0,
            "controlled_decisions": client.request_count, "controlled_errors": deepcopy(client.control_errors), "numeric_executions": len(executor_events), "successful_result_entries": len(store.entries),
            "duplicate_numeric_invocations": sum(max(0,n-1) for n in signatures.values()),
            "control_actions": sum(r["controlled_action"]["name"] not in {e.tool_name for _,e in executor_events} for r in client.seen),
            "stop_reasons": [r["stop_reason"] for r in results],
            "oracle_count": len(oracle), "oracle_passed": sum(r["passed"] for r in oracle),
            "context_bytes_sum": sum(len(encoded(r["messages"])) for r in client.seen),
            "wire_reservation_witness": sum(wire), "max_wire_reservation": max(wire, default=0),
            "offline_wall_seconds": time.perf_counter()-started,
            "read_restore_log": deepcopy(agent.working_memory.evidence_log),
            "request_success_rate": None,
            "request_success_reason": "Fixed scripted final text and predetermined decisions are not autonomous task performance"}}


def offline_report(case_ids=("T01", "T03", "T05"), arms=ARMS, *, partition="development", include_raw=True):
    results = [run_case(case, arm, partition=partition) for case in case_ids for arm in arms]
    report = {"stage": "issue52", "protocol_sha256": hashlib.sha256(SPEC.read_bytes()).hexdigest(),
        "kind": "offline_controlled_paired_replay", "external_completions": 0, "actual_api_tokens": 0,
        "results": results, "interpretation": "Known controlled plans/actions with original numerical Executor; no LLM autonomy, request success rate or paid-token benefit inferred"}
    if not include_raw:
        for row in report["results"]:
            row.pop("raw_agent_results", None)
            row.pop("decisions", None)
    return report


def preflight(case_ids=("T03", "T05"), arms=ARMS):
    report = offline_report(case_ids, arms, include_raw=False)
    units = []
    for case in case_ids:
        rows = [r for r in report["results"] if r["case_id"] == case]
        max_witness = max(r["metrics"]["wire_reservation_witness"] for r in rows)
        units.append({"case_id": case, "all_arm_witness": sum(r["metrics"]["wire_reservation_witness"] for r in rows),
            "same_per_arm_witness_reserve": max_witness, "matched_unit_reserve": max_witness*len(rows),
            "maximum_actual_witness_decisions": max(r["metrics"]["controlled_decisions"] for r in rows),
            "stops": {r["arm"]: r["metrics"]["stop_reasons"] for r in rows}})
    return {"stage": "issue52", "kind": "actual_wire_offline_capacity_witness_not_API_usage",
        "protocol_sha256": report["protocol_sha256"], "external_completions": 0, "actual_api_tokens": 0,
        "paired_units": units,
        "paired_witness_reservation": sum(u["matched_unit_reserve"] for u in units),
        "authorization": "NONE: independent explicit future authorization required",
        "limitations": ["A controlled valid path is not an upper bound for arbitrary future model decisions",
            "Every future actual wire and full final-answer input must be reserved; all failed attempts count",
            "Wire bytes are conservative reservation units, not actual API tokens or monetary cost"],
        "mechanism_metrics": [{k: r[k] for k in ("case_id", "arm", "metrics", "oracle")} for r in report["results"]]}


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf8") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--offline", action="store_true")
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--real", action="store_true")
    parser.add_argument("--case", action="append", choices=IMPLEMENTED_CASES)
    parser.add_argument("--arm", action="append", choices=("A", "B", "C", "C-no-delivery", "C-no-selection", "A-equivalent"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.real:
        parser.error("Issue52 has zero external-model authorization; no old allowance may be reused")
    cases = tuple(args.case or (("T03", "T05") if args.preflight else ("T01", "T03", "T05")))
    arms = tuple(args.arm or ARMS)
    result = preflight(cases, arms) if args.preflight else offline_report(cases, arms)
    write_new(args.output, result)
    print(json.dumps({"kind": result["kind"], "external_completions": 0,
        "actual_api_tokens": 0, "cases": cases, "arms": arms}, ensure_ascii=False))


if __name__ == "__main__":
    main()
