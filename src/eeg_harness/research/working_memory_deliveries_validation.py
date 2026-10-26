"""Offline controlled continuation through EEGAgent.run, with real EEG tools.

Only this validation driver scripts actions. The method accepts no gold,
correct task sequence, or evaluator turn kind. Zero external completions.
"""
import argparse
import json
from pathlib import Path

import numpy as np

from ..working_memory_agent import WorkingMemoryEEGAgent
from ..applications.evidence_statement import make_statement, verify_statement
from .task_memory import synthetic_records
from .task_memory_v2 import independent_oracle

WINDOW = {"channels": ["SYNTH-C1"], "start": 0, "end": 2}
REVISED = dict(WINDOW, end=3)
EVENT = {"labels": ["stimulus"], "tmin": 0, "tmax": 1}


def delivery(key, tool, scope, **extra):
    return {"key": key, "tool": tool, "scope": scope, **extra}


class ControlledClient:
    """Mechanism intervention, explicitly NOT autonomous model validation."""
    def __init__(self, actions):
        self.actions = iter(actions)
        self.messages = []

    def complete(self, messages, tools):
        self.messages.append(json.loads(json.dumps(messages)))
        action = next(self.actions)
        name, args = action(messages) if callable(action) else action
        return {"role": "assistant", "content": None, "tool_calls": [{
            "id": f"controlled-{len(self.messages)}", "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)}}]}


def artifact_action(name, *, restored=False):
    def choose(messages):
        payload = json.loads(messages[1]["content"])
        if restored:
            observations = payload["restored_trajectories"][0]["action_observations"]
            observation = next(o for o in observations if o["request"]["name"] == "create_epochs")
        else:
            observation = next(json.loads(m["content"])["data"]["observation"] for m in reversed(messages)
                               if m["role"] == "tool" and "observation" in json.loads(m["content"])["data"])
        ident = observation["result"]["data"]["artifact_id"]
        return name, {"artifact_id": ident}
    return choose


def run_example():
    close = ("close_subgoal", {"status": "completed"})
    finish = ("finish_task", {"status": "completed", "answer": "受控机制验证结束；不代表模型自主完成。"})
    actions = [
        ("begin_subgoal", {"title": "连续幅值及功率", "record": "A", "deliveries": [delivery("amp", "amplitude", WINDOW), delivery("power", "psd", WINDOW)]}),
        ("amplitude", WINDOW), ("psd", WINDOW), close,
        ("begin_subgoal", {"title": "事件试次数及功率", "record": "A", "deliveries": [delivery("count", "epoch_summary", EVENT), delivery("power", "event_bandpower", EVENT)]}),
        ("create_epochs", EVENT), artifact_action("epoch_summary"), artifact_action("event_bandpower"), close, finish,
        ("restore_subgoal", {"subgoal_id": "example-s2", "reason": "使用原试次而非重建 Epoch 来追加质量测量"}),
        ("begin_subgoal", {"title": "保留旧事件功率并追加质量", "record": "A", "deliveries": [delivery("power", "event_bandpower", EVENT), delivery("quality", "epoch_quality", EVENT)]}),
        ("reuse_result", {"delivery_key": "power", "task_id": "example-t5"}), artifact_action("epoch_quality", restored=True), close,
        ("begin_subgoal", {"title": "比较连续旧新窗口", "record": "A", "deliveries": [delivery("old", "psd", WINDOW), delivery("new", "psd", REVISED, revision_of="example-t2")]}),
        ("reuse_result", {"delivery_key": "old", "task_id": "example-t2"}), ("psd", REVISED), close,
        ("read_evidence", {"task_id": "example-t2", "record": "A", "parameters": WINDOW, "field_paths": [["SYNTH-C1", "alpha"]]}), finish,
    ]
    fake = ControlledClient(actions)
    agent = WorkingMemoryEEGAgent(fake, synthetic_records(), session_id="example", memory_version="multi_result")
    requests = ["A 的 SYNTH-C1，连续 0–2 秒幅值与频带功率；另给 stimulus 条件事件后 0–1 秒试次数和频带功率，不筛选。",
                "在原事件试次上追加质量测量，保留已算功率；连续窗口改为 0–3 秒，比较旧新结果。"]
    outcomes = [agent.run(requests[0]).stop_reason, agent.continue_run(requests[1]).stop_reason]
    if outcomes != ["completed", "completed"]:
        raise AssertionError(f"Controlled workflow incomplete: {outcomes}")
    store = agent.working_memory.store
    checks = []
    for entry in store.entries:
        path = ({"amplitude": ["SYNTH-C1", "rms"], "psd": ["SYNTH-C1", "alpha"],
                 "epoch_summary": ["valid_epoch_count"], "event_bandpower": ["conditions", "stimulus", "channels", "SYNTH-C1", "alpha"]}).get(entry.capability)
        if path is None:
            continue
        value = entry.result
        for key in path:
            value = value[key]
        oracle = independent_oracle(store.records[entry.record], {"capability": entry.capability, "parameters": entry.parameters}, path)
        valid = bool(np.isclose(float(value), oracle, rtol=.005, atol=1e-13))
        checks.append({"task_id": entry.task_id, "path": path, "tool_value": value,
                       "independent_value": oracle, "absolute_difference": abs(float(value)-oracle), "valid": valid})
    # Legacy amplitude prints three significant digits; preserve its numerical logic.
    if not all(c["valid"] for c in checks):
        raise AssertionError(checks)
    claim = make_statement(store, "example-t5", ["conditions", "stimulus", "channels", "SYNTH-C1", "alpha"])
    checked = verify_statement(store, claim)
    if not checked["valid"]:
        raise AssertionError(checked)
    decisions = []
    for decision in agent.working_memory.decisions:
        p = json.loads(decision["messages"][1]["content"])
        decisions.append({"turn": decision["turn"], "before_action": decision["before_action"],
                          "active_subgoal": decision["active_subgoal"],
                          "restored_subgoals": [r["subgoal"]["subgoal_id"] for r in p["restored_trajectories"]],
                          "exact_result_ids": [r["task_id"] for r in p["exact_evidence"]],
                          "context_bytes": decision["context_bytes"]})
    evidence = {"protocol": "controlled offline mechanism test; not model autonomy or comparative efficacy",
                "memory_version": "multi_result_v1", "external_completions": 0,
                "requests": requests, "stop_reasons": outcomes,
                "synthetic_configuration": "research.task_memory.synthetic_records; 128 Hz, 2 channels, 8 s; A/B",
                "independent_oracle_checks": checks, "statement": claim, "statement_check": checked,
                "subgoals": [store.summary(g) for g in store.subgoals],
                "events": store.events, "actual_decision_visibility": decisions,
                "action_observations": [{"subgoal_id": g.subgoal_id, "observations": g.observations} for g in store.subgoals]}
    return evidence


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, help="New JSON file; existing results are never overwritten")
    args = p.parse_args(argv)
    evidence = run_example()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as f:
            json.dump(evidence, f, ensure_ascii=False, allow_nan=False, indent=2)
    print(json.dumps({"stop_reasons": evidence["stop_reasons"], "oracle_checks": len(evidence["independent_oracle_checks"]),
                      "statement_valid": evidence["statement_check"]["valid"], "external_completions": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
