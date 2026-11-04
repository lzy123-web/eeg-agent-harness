"""Issue51 independent budget and bounded scientific working-memory sessions.

The driver sends natural requests only. Controlled Executor history is limited
to offline preflight and the explicitly labelled optional context comparison.
It is never reported as autonomous task organization.
"""
import argparse
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

import numpy as np

from ..llm import OpenAICompatibleClient, LLMServiceError
from ..tooling import ToolRequest
from ..working_memory import WorkingMemoryStore
from ..working_memory_agent import WorkingMemoryEEGAgent
from .integrated_method.v2_validation import JournaledBudgetClient
from .task_memory import PROJECT_ROOT
from .task_memory_v2 import independent_oracle
from .task_memory_issue39_budget import _append, _ledger_lock, _rows, ledger_totals, StageBudgetExhausted
from .working_memory_issue48 import encoded
from .working_memory_issue50 import (
    Issue50Client, FINISH_CHOICE, STALE_NOTICE, records_for as previous_records,
    _relevant_window_clarification,
)

ROOT = PROJECT_ROOT / "artifacts" / "point1_task_memory" / "issue51"
LEDGER = ROOT / "budget.jsonl"
SPEC = PROJECT_ROOT / "config" / "point1_working_memory_issue51.json"
LIMITS = {"completions": 72, "api_tokens": 650000}
PHASE_LIMITS = {"development": {"completions": 18, "api_tokens": 150000},
                "confirmation": {"completions": 36, "api_tokens": 500000},
                "comparison": {"completions": 18, "api_tokens": 300000}}


def protocol():
    return json.loads(SPEC.read_text(encoding="utf8"))


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def _usage(rows, predicate=lambda _: True):
    starts = {r["request_id"]: r for r in rows
              if r.get("event") == "reserved" and predicate(r.get("context", {}))}
    ends = {r["request_id"]: r for r in rows if r.get("event") in {"received", "failed"}}
    return len(starts), sum(ends[i]["total_tokens"]
        if ends.get(i, {}).get("total_tokens") is not None else r["reserved_tokens"]
        for i, r in starts.items())


class Issue51Client(Issue50Client):
    """Reuse verified wire/lease mechanics, never the Issue50 allowance.

    Phase and matched-arm caps are maxima under the single total ceiling, not
    additive grants or predictions of autonomous completion. All calls,
    including failures, share one append-only ledger.
    With no usage receipt a reservation stays charged conservatively.
    """
    def __init__(self, client, ledger, *, phase, arm, request_journal=None, spec=None):
        self.client, self.ledger = client, Path(ledger)
        self.spec = spec or protocol()
        if self.spec["limits"] != LIMITS or self.spec["phase_limits"] != PHASE_LIMITS:
            raise StageBudgetExhausted("Issue51 authorization or protected phase pools differ")
        if phase not in PHASE_LIMITS or arm not in self.spec["arms"]:
            raise ValueError("Unknown Issue51 phase/arm")
        self.context = {"phase": phase, "arm": arm}
        self.request_journal = Path(request_journal) if request_journal else None
        self.final_only, self.delivery_checkpoint, self._lease = False, None, None
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        header = {"event": "opened", "stage": "issue51", "version": 1,
                  "max_requests": 72, "max_tokens": 650000, "phase_limits": PHASE_LIMITS}
        with _ledger_lock(self.ledger):
            rows = _rows(self.ledger)
            if not rows:
                _append(self.ledger, header)
            elif any(rows[0].get(k) != v for k, v in header.items()):
                raise StageBudgetExhausted("Do not reuse, reset or resize another stage's ledger")
            if any(r.get("event") == "stage_closed" for r in rows):
                raise StageBudgetExhausted("Issue51 was closed; do not reopen its allowance")

    def _fits(self, rows, calls, tokens):
        if any(r.get("event") == "stage_closed" for r in rows):
            return False
        checks = [(LIMITS, _usage(rows)),
                  (PHASE_LIMITS[self.context["phase"]], _usage(rows,
                      lambda c: c.get("phase") == self.context["phase"]))]
        if self.context["phase"] == "comparison":
            approved=next((r for r in rows if r.get("event") == "phase_frozen"
                and r.get("phase") == "comparison" and r.get("scientific_audit_sha256")),None)
            if approved is None or not any(r.get("event") == "arm_ended" and
                    r.get("phase") == "confirmation" for r in rows):
                return False
            checks.append((self.spec["comparison_arm_limits"], _usage(rows,
                lambda c: c.get("phase") == "comparison" and c.get("arm") == self.context["arm"])))
        return all(used[0] + calls <= limit["completions"] and
                   used[1] + tokens <= limit["api_tokens"] for limit, used in checks)

    def complete(self, messages, tools, tool_choice="auto"):
        try:
            return super().complete(messages, tools, tool_choice)
        except LLMServiceError as exc:
            if exc.code == "STAGE_BUDGET_EXHAUSTED":
                raise LLMServiceError(exc.code,
                    "Issue51 actual-wire reservation exceeds the remaining independent stage, phase or matched-arm allowance") from exc
            raise


def records_for(variant="confirmation"):
    return {alias: replace(record, source=f"synthetic://issue51-{variant}-{alias}")
            for alias, record in previous_records(variant).items()}


def scientific_preflight():
    """Independent numbers on Issue51 sources through the original Executor."""
    records = records_for()
    store = WorkingMemoryStore("issue51-science-preflight", records)
    operations, checks = [], []
    def run(alias, name, args, expected=True):
        result = store.contexts[alias].execute(ToolRequest(name, args, f"preflight-{len(operations)+1}")).to_dict()
        operations.append({"record": alias, "tool": name, "arguments": args, "result": result})
        assert result["success"] == expected, operations[-1]
        return result["data"]
    info = run("A", "record_info", {})
    assert info["sfreq"] == 128 and info["duration_seconds"] == 8
    for alias in ("A", "B"):
        for start, end in ((0,2), (2,4), (4,6)):
            scope = {"channels": ["SYNTH-C1"], "start": start, "end": end}
            for tool in ("amplitude", "psd"):
                data = run(alias, tool, scope)
                for field in (["rms"] if tool == "amplitude" else data["SYNTH-C1"]):
                    expected = independent_oracle(records[alias], {"capability": tool, "parameters": scope}, ["SYNTH-C1", field])
                    actual = float(data["SYNTH-C1"][field])
                    checks.append({"record": alias, "tool": tool, "scope": scope, "field": ["SYNTH-C1", field],
                        "actual": actual, "oracle": expected, "valid": bool(np.isclose(actual, expected, rtol=.005, atol=5e-13))})
    scope = {"labels": ["stimulus"], "tmin": 0, "tmax": 1.25}
    epochs = run("A", "create_epochs", scope)
    artifact = epochs["artifact_id"]
    powers = run("A", "event_bandpower", {"artifact_id": artifact})
    quality = run("A", "epoch_quality", {"artifact_id": artifact})
    assert epochs["valid_epoch_count"] == 3
    assert quality["artifact_id"] == powers["artifact_id"] == artifact
    assert store.contexts["A"].artifacts[artifact].baseline is None
    for channel, values in powers["conditions"]["stimulus"]["channels"].items():
        for band, actual in values.items():
            path = ["conditions", "stimulus", "channels", channel, band]
            expected = independent_oracle(records["A"], {"capability": "event_bandpower", "parameters": scope}, path)
            checks.append({"record": "A", "tool": "event_bandpower", "scope": scope, "field": path,
                "actual": actual, "oracle": expected, "valid": bool(np.isclose(actual, expected, rtol=1e-6, atol=5e-13))})
    short = run("A", "create_epochs", dict(scope, tmax=.75))
    run("A", "event_bandpower", {"artifact_id": short["artifact_id"]}, expected=False)
    assert all(c["valid"] for c in checks)
    return {"status": "passed", "kind": "controlled_real_executor_not_agent_autonomy",
        "operations": operations, "oracle_checks": checks,
        "units": "amplitude V; power V²; continuous absolute seconds; Epoch relative seconds",
        "quality": "Actual empirical criteria; no clinical threshold or filtering invented"}


def build_agent(client, arm, session_id, *, variant="confirmation"):
    spec = protocol()
    settings = spec["arms"][arm]
    return WorkingMemoryEEGAgent(client, records_for(variant), session_id=session_id,
        memory_version=settings["architecture"], context_mode=settings["context_mode"],
        **spec["agent_settings"])


def requests_for(phase):
    spec = protocol()
    return spec["development"]["requests"] if phase == "confirmation" else spec[phase]["requests"]


def _write_new(path, value):
    with Path(path).open("x", encoding="utf8") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)


def view_reservation(controller, *, stage, model="deepseek-chat"):
    """Measure the exact generated view and tools, not character/token ratios."""
    settings = protocol()["model_settings"]
    normal, tools = controller.build_messages(), controller.tool_definitions()
    final, final_tools = controller.build_final_messages()
    def reserve(messages, definitions, choice="auto"):
        body = {"model": model, "messages": messages, "max_tokens": settings["max_output_tokens"],
                "stream": False, "thinking": {"type": "disabled"}, "tools": definitions,
                "tool_choice": choice}
        return len(encoded(body)) + settings["max_output_tokens"]
    return {"stage": stage, "turn": controller.store.turn,
            "decision_reserve": reserve(normal, tools),
            "final_reserve": reserve(final, final_tools, FINISH_CHOICE),
            "lease_reserve": reserve(final + [{"role": "system", "content": STALE_NOTICE}],
                                     final_tools, FINISH_CHOICE),
            "message_bytes": len(encoded(normal)), "tool_bytes": len(encoded(tools)),
            "successful_results": len(controller.store.entries),
            "active_task": bool(controller.store.active)}


def controlled_history(agent, *, capture_views=False):
    """Identical genuine-tool preparation for preflight/comparison, not autonomy.

    Numerical results are never fabricated. This small history covers active
    multiple outcomes, archival, versioned windows, Epoch objects, exact reads
    and process restoration. Views are sampled before each controlled action.
    """
    c = agent.working_memory
    actions, views = [], []
    def measure(label):
        if capture_views:
            views.append(view_reservation(c, stage=label))
        else:
            c.build_messages()  # The common Agent constructs a real input before every action.
    def call(name, arguments):
        measure("before_" + name)
        ident = f"controlled-{len(actions)+1}"
        assistant = {"role": "assistant", "content": None, "tool_calls": [
            {"id": ident, "type": "function", "function": {
                "name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}}]}
        result = c.execute(ToolRequest(name, arguments, ident)).to_dict()
        c.observe_exchange(assistant, [{"role": "tool", "tool_call_id": ident,
            "name": name, "content": json.dumps(result, ensure_ascii=False, allow_nan=False)}])
        actions.append({"controlled": True, "tool": name, "arguments": arguments, "result": result})
        if not result["success"]:
            raise AssertionError(actions[-1])
        return result
    def focus(title, requirements):
        return call("focus_task", {"title": title, "record": "A",
            "requirements": [{"record": "A", **r} for r in requirements]})
    def finish():
        call("finish_task", {"status": "completed", "answer": "受控真实工具准备，非模型自主任务记录。"})
        c.on_stop("completed")

    old = {"channels": ["SYNTH-C1"], "start": 0, "end": 2}
    new = {"channels": ["SYNTH-C1"], "start": 4, "end": 6}
    event = {"labels": ["stimulus"], "tmin": 0, "tmax": 1.25}
    c.begin_turn("请在记录A的SYNTH-C1、0到2秒这一范围同时计算RMS和alpha绝对功率，保留单位和来源。")
    focus("同一范围的幅值与频带描述", [{"tool": tool, "scope": old} for tool in ["amplitude", "psd"]])
    call("amplitude", {"record": "A", **old})
    call("psd", {"record": "A", **old})
    first = next(e for e in c.store.entries if e.capability == "psd")
    amplitude = next(e for e in c.store.entries if e.capability == "amplitude")
    finish()
    c.begin_turn("将记录A的SYNTH-C1连续分析窗口改为4到6秒，计算alpha绝对功率，保留旧结果。")
    call("psd", {"record": "A", **new, "inherit_result": first.task_id})
    second = c.store.entries[-1]
    call("compare_results", {"left_result": first.task_id, "right_result": second.task_id,
        "left_path": ["SYNTH-C1", "alpha"], "right_path": ["SYNTH-C1", "alpha"]})
    finish()
    c.begin_turn("请分析记录A的stimulus事件发生后0到1.25秒，给出两个通道的theta绝对功率与实际试次数，不做基线校正或筛选。")
    focus("实际事件试次及其频带描述", [{"tool": tool, "scope": event}
        for tool in ["create_epochs", "event_bandpower"]])
    call("create_epochs", {"record": "A", **event})
    artifact = next(reversed(c.store.contexts["A"].artifacts))
    call("event_bandpower", {"record": "A", "artifact_id": artifact})
    finish()
    process_goal = c.store.subgoals[-1].subgoal_id
    if capture_views:
        c.begin_turn(requests_for("comparison")[0])
        measure("historical_query_before_read")
        call("read_result", {"result_id": amplitude.task_id})
        measure("exact_read_enters_next_input")
        finish()
        c.begin_turn(requests_for("comparison")[0])
        call("restore_task", {"task_id": process_goal, "reason": "核查原事件过程后在原试次上追加质量测量"})
        measure("restored_process_enters_next_input")
        call("epoch_quality", {"record": "A", "artifact_id": artifact})
        measure("new_quality_enters_next_input")
        finish()
    def canonical(value):
        if isinstance(value, dict):
            return {k: canonical(v) for k, v in value.items() if k != "artifact_id"}
        if isinstance(value, list):
            return [canonical(v) for v in value]
        return value
    actual = [{"record": e.record, "capability": e.capability, "parameters": e.parameters,
               "result": canonical(e.result)} for e in c.store.entries]
    return {"kind": "controlled_real_executor_history_not_agent_autonomy", "actions": actions,
            "views": views, "history": c.snapshot(), "artifact_id": artifact,
            "entry_count": len(c.store.entries), "scientific_content_sha256": digest(actual),
            "hash_exclusion": "Only runtime artifact ID excluded; numerical facts, scope, parameters and fingerprints retained"}


def autonomous_unit_witness(variant="confirmation"):
    """Offline original-Executor witness for the exact three natural requests.

    This is an executable feasibility/resource check, never a model success.
    One snapshot may precede a batch only for already-independent actions.
    Dependent Epoch actions wait for the actual artifact observation.
    """
    agent = build_agent(None, "scientific-working", "issue51-main-unit-witness", variant=variant)
    c = agent.working_memory
    views, actions = [], []
    def batch(items):
        views.append(view_reservation(c, stage="before_" + "+".join(n for n,_ in items)))
        calls = [{"id":f"witness-{len(actions)+i+1}","type":"function","function":{
            "name":name,"arguments":json.dumps(args,ensure_ascii=False)}} for i,(name,args) in enumerate(items)]
        messages=[]
        for call,(name,args) in zip(calls,items):
            result = c.execute(ToolRequest(name,args,call["id"])).to_dict()
            actions.append({"controlled":True,"turn":c.store.turn,"tool":name,"arguments":args,"result":result})
            if not result["success"]:raise AssertionError(actions[-1])
            messages.append({"role":"tool","tool_call_id":call["id"],"name":name,
                "content":json.dumps(result,ensure_ascii=False,allow_nan=False)})
        c.observe_exchange({"role":"assistant","content":None,"tool_calls":calls},messages)
    def call(name,args):batch([(name,args)])
    def focus(title,reqs):call("focus_task",{"title":title,"record":"A","requirements":reqs})
    def end(status="completed"):
        args={"status":status,"answer":"离线受控科学与资源见证，不是模型自主完成。"}
        if status != "completed":args["unresolved"]=["请提供记录A事件相对时间窗。"]
        call("finish_task",args)
        c.on_stop(status)
    old={"channels":["SYNTH-C1"],"start":0,"end":2}
    bscope={"channels":["SYNTH-C1"],"start":2,"end":4}
    new={"channels":["SYNTH-C1"],"start":4,"end":6}
    event={"labels":["stimulus"],"tmin":0,"tmax":1.25}
    base=[{"tool":tool,"record":record,"scope":scope}
          for tool,record,scope in (("amplitude","A",old),("psd","A",old),("amplitude","B",bscope))]
    pending=[{"tool":tool,"record":"A","scope":{"labels":["stimulus"]}}
             for tool in ("create_epochs","event_bandpower")]
    title="两份记录基础情况及指定事件的科学描述"
    c.begin_turn(requests_for("confirmation")[0])
    focus(title,base+pending)
    batch([("amplitude",{"record":"A",**old}),("psd",{"record":"A",**old}),
           ("amplitude",{"record":"B",**bscope})])
    old_power=next(e for e in c.store.entries if e.record == "A" and e.capability == "psd")
    b_rms=next(e for e in c.store.entries if e.record == "B")
    end("clarification_required")

    c.begin_turn(requests_for("confirmation")[1])
    # Re-focus the unchanged declared partial purpose; admitted actual actions
    # supply the now-authorized missing window, rather than a driver mutation.
    focus(title,base+pending+[{"tool":"psd","record":"A","scope":new}])
    batch([("create_epochs",{"record":"A",**event}),
           ("psd",{"record":"A",**new,"inherit_result":old_power.task_id})])
    artifact=next(reversed(c.store.contexts["A"].artifacts))
    new_power=c.store.entries[-1]
    batch([("event_bandpower",{"record":"A","artifact_id":artifact}),
           ("compare_results",{"left_result":old_power.task_id,"right_result":new_power.task_id,
            "left_path":["SYNTH-C1","alpha"],"right_path":["SYNTH-C1","alpha"]})])
    event_power=next(e for e in reversed(c.store.entries) if e.capability == "event_bandpower")
    event_goal=c.store.active.subgoal_id
    end()

    c.begin_turn(requests_for("confirmation")[2])
    focus("原事件试次质量与历史数值核查",[{"tool":"epoch_quality","record":"A","scope":event}])
    call("restore_task",{"task_id":event_goal,"reason":"核查实际原试次及处理后继续质量测量"})
    batch([("read_result",{"result_id":event_power.task_id,"fields":[["conditions","stimulus","channels","SYNTH-C2","theta"]]}),
           ("read_result",{"result_id":b_rms.task_id,"fields":[["SYNTH-C1","rms"]]}),
           ("epoch_quality",{"record":"A","artifact_id":artifact})])
    end()
    # The actual final-answer call uses the current full view here, making this
    # witness conservative compared with the compact emergency final lease.
    reserve=sum(v["decision_reserve"] for v in views)
    compact_reserve=sum(v["lease_reserve"] if v["stage"] == "before_finish_task" else
                        v["decision_reserve"] for v in views)
    by_turn=[{"turn":turn,"calls":sum(v["turn"] == turn for v in views),
        "wire_and_output_reserve":sum(v["decision_reserve"] for v in views if v["turn"] == turn)}
        for turn in sorted({v["turn"] for v in views})]
    return {"kind":"controlled_real_executor_exact_natural_unit_not_model_autonomy",
        "variant":variant,"requests":requests_for("confirmation"),"actions":actions,"views":views,"by_turn":by_turn,
        "bounded_witness_calls":len(views),"bounded_witness_tokens":reserve,
        "compact_final_lease_witness_tokens":compact_reserve,
        "complete_unit_admissible":len(views)<=PHASE_LIMITS["confirmation"]["completions"]
            and reserve<=PHASE_LIMITS["confirmation"]["api_tokens"],
        "final_inputs_included":sum(v["stage"] == "before_finish_task" for v in views),
        "scope":"Exact authorized requests, independent-action batches only; includes real multi-result state, missing-window continuation, artifact recovery, actual reads and all three complete final inputs",
        "limitations":"This is one legal witnessed schedule, not a prediction or upper bound over every autonomous path. Actual calls enforce their full wire+output and current-final lease.",
        "history":c.snapshot()}


def comparison_history(agent):
    """Minimal identical three-result history; fully visible according to mode."""
    c=agent.working_memory
    actions=[]
    def call(name,args):
        c.build_messages()
        ident=f"comparison-seed-{len(actions)+1}"
        result=c.execute(ToolRequest(name,args,ident)).to_dict()
        c.observe_exchange({"role":"assistant","content":None,"tool_calls":[{"id":ident,
            "type":"function","function":{"name":name,"arguments":json.dumps(args,ensure_ascii=False)}}]},
            [{"role":"tool","tool_call_id":ident,"name":name,"content":json.dumps(result,ensure_ascii=False)}])
        actions.append({"controlled":True,"tool":name,"arguments":args,"result":result})
        if not result["success"]:raise AssertionError(actions[-1])
    def finish():
        call("finish_task",{"status":"completed","answer":"受控真实工具历史，不是模型自主历史。"})
        c.on_stop("completed")
    c.begin_turn("请计算记录A中SYNTH-C1在0到2秒的RMS，保留范围与单位。")
    call("amplitude",{"record":"A","channels":["SYNTH-C1"],"start":0,"end":2})
    finish()
    scope={"labels":["stimulus"],"tmin":0,"tmax":1.25}
    c.begin_turn("请计算记录A的stimulus事件发生后0到1.25秒两个通道的theta绝对功率和试次数，不做基线校正或筛选。")
    call("focus_task",{"title":"事件试次及频带描述","record":"A",
        "requirements":[{"tool":t,"record":"A","scope":scope} for t in ("create_epochs","event_bandpower")]})
    call("create_epochs",{"record":"A",**scope})
    artifact=next(reversed(c.store.contexts["A"].artifacts))
    call("event_bandpower",{"record":"A","artifact_id":artifact})
    finish()
    def canonical(value):
        if isinstance(value,dict):return {k:canonical(v) for k,v in value.items() if k != "artifact_id"}
        if isinstance(value,list):return [canonical(v) for v in value]
        return value
    facts=[{"record":e.record,"capability":e.capability,"parameters":e.parameters,"result":canonical(e.result)} for e in c.store.entries]
    return {"kind":"controlled_real_executor_history_not_agent_autonomy","actions":actions,
        "history":c.snapshot(),"artifact_id":artifact,"entry_count":len(c.store.entries),
        "scientific_content_sha256":digest(facts),"hash_exclusion":"Only ephemeral artifact ID excluded; exact results and scopes retained"}


def comparison_unit_witness(arm):
    """One complete useful followup; already-visible values need no read."""
    agent=build_agent(None,arm,"issue51-compact-resource")
    seed=comparison_history(agent)
    c=agent.working_memory
    c.begin_turn(requests_for("comparison")[0])
    initial=view_reservation(c,stage="before_history_use_and_independent_quality")
    items=[]
    for capability,field in (("amplitude",["SYNTH-C1","rms"]),
            ("event_bandpower",["conditions","stimulus","channels","SYNTH-C2","theta"])):
        entry=next(e for e in c.store.entries if e.capability == capability)
        # The actual view has already been built; this checks evidence exposed
        # by that view, not a private future answer or hidden gold selector.
        available=c.retrieved.get(entry.task_id,{}).get("fields",[])
        if not any(f["path"] == field for f in available):
            items.append(("read_result",{"result_id":entry.task_id,"fields":[field]}))
    items.append(("epoch_quality",{"record":"A","artifact_id":seed["artifact_id"]}))
    calls=[];messages=[];actions=[]
    for index,(name,args) in enumerate(items,1):
        ident=f"comparison-witness-{index}"
        calls.append({"id":ident,"type":"function","function":{"name":name,"arguments":json.dumps(args,ensure_ascii=False)}})
        result=c.execute(ToolRequest(name,args,ident)).to_dict()
        actions.append({"controlled":True,"tool":name,"arguments":args,"result":result})
        if not result["success"]:raise AssertionError(actions[-1])
        messages.append({"role":"tool","tool_call_id":ident,"name":name,"content":json.dumps(result,ensure_ascii=False)})
    c.observe_exchange({"role":"assistant","content":None,"tool_calls":calls},messages)
    final=view_reservation(c,stage="before_complete_final_answer")
    slots=[initial,final]
    total=sum(v["decision_reserve"] for v in slots)
    cap=protocol()["comparison_arm_limits"]
    return {"arm":arm,"context_mode":protocol()["arms"][arm]["context_mode"],
        "views":slots,"bounded_witness_calls":2,"bounded_witness_tokens":total,
        "whole_unit_admissible":total<=cap["api_tokens"] and 2<=cap["completions"],
        "arm_cap":cap,"controlled_entry_count":seed["entry_count"],"scientific_content_sha256":seed["scientific_content_sha256"],
        "controlled_actions":actions,"full_native_final_input_included":True,
        "reading_rule":"Only missing necessary facts are read; full and summary may use their directly visible exact values. All arms retain identical evidence and read rights."}


def budget_preflight():
    """Full-history-state witness and full-unit admission, never a success guarantee.

    Witness actions are public offline resource probes, not a script passed to
    a model. Every natural turn and final answer receives a measured slot. A
    live session still has hard pool enforcement and per-call exact-wire leases;
    unknown autonomous actions cannot honestly be promised a fixed cost.
    """
    samples = [comparison_unit_witness(arm) for arm in protocol()["arm_order"]["comparison"]]
    if len({s["scientific_content_sha256"] for s in samples}) != 1:
        raise ValueError("Matched context modes must receive identical real scientific history")
    return {"status": "measured", "samples": samples,
        "comparison_complete_unit_admissible": all(s["whole_unit_admissible"] for s in samples),
        "comparison_total_witness_tokens":sum(s["bounded_witness_tokens"] for s in samples),
        "comparison_protected_admission":PHASE_LIMITS["comparison"],
        "interpretation": "A complete common followup per arm includes actual quality execution and full final input. Only missing necessary facts are read. Initial expansive two-turn design is preserved in preflight-initial.json; no online attempt preceded this simplification. These are legal witnessed schedules, not predictions of arbitrary autonomous choices."}


def preflight():
    primary=autonomous_unit_witness()
    if not primary["complete_unit_admissible"]:
        raise StageBudgetExhausted("The known complete primary session does not fit the protected confirmation pool")
    development=autonomous_unit_witness("development")
    return {"protocol_sha256": hashlib.sha256(SPEC.read_bytes()).hexdigest(),
            "external_completions": 0, "scientific": scientific_preflight(),
            "primary_unit_witness":primary,"development_resource_witness":development,"budget": budget_preflight()}


def _start_run(phase, arm, run_id, manifest, ready, *, revision_note=None, audit=None):
    with _ledger_lock(LEDGER):
        rows = _rows(LEDGER)
        if phase == "development":
            started = [r for r in rows if r.get("event") == "arm_started" and r["phase"] == phase]
            if len(started) >= 3:
                raise StageBudgetExhausted("Initial development plus at most two root-caused revisions")
            if started and not revision_note:
                raise StageBudgetExhausted("Further development requires a saved root cause and offline repair record")
        else:
            frozen = {k: manifest[k] for k in ("candidate_commit", "protocol_sha256", "model_settings", "model_requested")}
            existing = next((r for r in rows if r.get("event") == "phase_frozen" and r["phase"] == phase), None)
            if existing and any(existing.get(k) != v for k, v in frozen.items()):
                raise StageBudgetExhausted("Candidate/protocol/model are frozen; do not revise after confirmation")
            started = [r["arm"] for r in rows if r.get("event") == "arm_started" and r["phase"] == phase]
            order = protocol()["arm_order"][phase]
            if len(started) >= len(order) or started != order[:len(started)] or arm != order[len(started)]:
                raise StageBudgetExhausted("Run each arm once in frozen order; preserve every first outcome")
            if phase == "comparison" and not existing:
                if not ready["budget"]["comparison_complete_unit_admissible"]:
                    raise StageBudgetExhausted("Complete matched unit does not fit measured whole-session reservations; skip all arms")
                if not audit or audit.get("autonomous_scientific_conversation_passed") is not True:
                    raise StageBudgetExhausted("Comparison requires explicit scientific audit, not tool-name presence")
                runs = {r["run_id"] for r in rows if r.get("event") == "arm_ended" and r["phase"] == "confirmation"}
                if audit.get("run_id") not in runs or not audit.get("evidence_sha256"):
                    raise StageBudgetExhausted("Audit must identify the completed confirmation and actual evidence digest")
                used_calls,used_tokens=_usage(rows)
                reserve=PHASE_LIMITS["comparison"]
                if used_calls+reserve["completions"]>LIMITS["completions"] or used_tokens+reserve["api_tokens"]>LIMITS["api_tokens"]:
                    raise StageBudgetExhausted("Insufficient global remainder for all three complete arms; do not start only the candidate")
            if not existing:
                _append(LEDGER, {"event": "phase_frozen", "phase": phase, **frozen,
                    "scientific_audit_sha256":digest(audit) if audit else None,
                    "resource_witness_sha256": digest(ready["budget"]), "timestamp_utc": time.time()})
        _append(LEDGER, {"event": "arm_started", "phase": phase, "arm": arm, "run_id": run_id,
            "revision_note": revision_note, "scientific_audit": audit, "timestamp_utc": time.time()})


def real_session(phase, arm, run_id, *, development_turns=None, revision_note=None, audit=None):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,127}", run_id):
        raise ValueError("Use a fresh simple run ID")
    if phase not in PHASE_LIMITS or arm not in protocol()["arms"]:
        raise ValueError("Unknown phase/arm")
    if phase in {"development", "confirmation"} and arm != "scientific-working":
        raise ValueError("Priority autonomous unit uses the actual task working-memory mode")
    if development_turns is not None and (phase != "development" or development_turns not in {1, 2, 3}):
        raise ValueError("Only development may explicitly use a natural request prefix")
    ROOT.mkdir(parents=True, exist_ok=True)
    with _ledger_lock(ROOT / "active-live-session"):
        ready = preflight()  # No credential or network access before this succeeds.
        if phase in {"development", "confirmation"}:
            witness=ready["development_resource_witness" if phase == "development" else "primary_unit_witness"]
            count=development_turns or 3
            slots=[v for v in witness["views"] if v["turn"] <= count]
            used_calls,used_tokens=_usage(_rows(LEDGER),lambda c:c.get("phase") == phase)
            cap=PHASE_LIMITS[phase]
            if (used_calls+len(slots)>cap["completions"] or
                    used_tokens+sum(v["decision_reserve"] for v in slots)>cap["api_tokens"]):
                raise StageBudgetExhausted("The complete selected natural-session witness does not fit the remaining protected phase pool")
        if phase != "development" and subprocess.check_output(["git", "status", "--porcelain"], cwd=PROJECT_ROOT, text=True).strip():
            raise RuntimeError("Commit a clean candidate before frozen confirmation")
        raw = OpenAICompatibleClient.from_env()
        spec = protocol()
        raw.max_retries = 0
        raw.max_tokens = spec["model_settings"]["max_output_tokens"]
        raw.timeout = min(raw.timeout, spec["model_settings"]["timeout_seconds"])
        variant = "development" if phase == "development" else "confirmation"
        manifest = {"candidate_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True).strip(),
            "protocol_sha256": hashlib.sha256(SPEC.read_bytes()).hexdigest(), "phase": phase, "arm": arm,
            "protocol_content_sha256": digest(spec),
            "model_requested": raw.model, "model_settings": {"max_output_tokens": raw.max_tokens,
                "max_retries": 0, "timeout_seconds": raw.timeout, "thinking": getattr(raw, "thinking", "disabled")},
            "data_sha256": {k: hashlib.sha256(v.data.tobytes()).hexdigest() for k,v in records_for(variant).items()},
            "development_turns": development_turns, "timestamp_utc": time.time()}
        directory = ROOT / run_id
        directory.mkdir(parents=True, exist_ok=False)
        for name, value in (("protocol.json", spec), ("manifest.json", manifest), ("preflight.json", ready)):
            _write_new(directory / name, value)
        journal = JournaledBudgetClient(raw, directory / "responses.jsonl", max_requests=72, max_total_tokens=650000)
        client = Issue51Client(journal, LEDGER, phase=phase, arm=arm, request_journal=directory / "requests.jsonl")
        _start_run(phase, arm, run_id, manifest, ready, revision_note=revision_note, audit=audit)
        client.set_context(run_id=run_id, protocol_sha256=manifest["protocol_sha256"])
        agent = build_agent(client, arm, run_id, variant=variant)
        if phase == "comparison":
            _write_new(directory / "controlled-history.json", comparison_history(agent))
        requests = requests_for(phase)[:development_turns] if development_turns else requests_for(phase)
        prior, outcome = None, "driver_error"
        try:
            for number, request in enumerate(requests, 1):
                if number == 2 and phase != "comparison" and not _relevant_window_clarification(prior.to_dict()):
                    _append(directory / "driver_events.jsonl", {"event": "continuation_not_sent", "turn": number,
                        "reason": "no_actual_relevant_window_clarification", "prior_stop": prior.stop_reason})
                    outcome = "no_relevant_clarification"
                    break
                client.set_context(turn=number)
                result = agent.run(request) if number == 1 and phase != "comparison" else agent.continue_run(request)
                _write_new(directory / f"turn-{number}.json", result.to_dict())
                print(json.dumps({"phase": phase, "arm": arm, "turn": number, "stop_reason": result.stop_reason,
                    "rounds": result.rounds, "tool_calls": result.tool_calls, "answer": result.final_answer,
                    "budget": ledger_totals(LEDGER)}, ensure_ascii=False), flush=True)
                prior, outcome = result, result.stop_reason
                if outcome in {"llm_error", "budget_exhausted", "no_progress", "context_capacity", "evidence_capacity",
                               "deadline_exceeded", "round_limit", "tool_call_limit"}:
                    break
        finally:
            with _ledger_lock(LEDGER):
                _append(LEDGER, {"event": "arm_ended", "phase": phase, "arm": arm, "run_id": run_id,
                    "stop_reason": outcome, "timestamp_utc": time.time()})
        return agent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--real", action="store_true")
    parser.add_argument("--phase", choices=tuple(PHASE_LIMITS))
    parser.add_argument("--arm", choices=tuple(protocol()["arms"]), default="scientific-working")
    parser.add_argument("--run-id")
    parser.add_argument("--development-turns", type=int)
    parser.add_argument("--revision-note", type=Path)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.preflight:
        result = preflight()
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            _write_new(args.output, result)
        print(json.dumps({"scientific": result["scientific"]["status"],
            "oracle_checks": len(result["scientific"]["oracle_checks"]),
            "primary_unit":{k:result["primary_unit_witness"][k] for k in
                ("bounded_witness_calls","bounded_witness_tokens","complete_unit_admissible","final_inputs_included")},
            "comparison_units":[{k:r[k] for k in ("arm","bounded_witness_calls","bounded_witness_tokens","whole_unit_admissible")}
                for r in result["budget"]["samples"]],
            "external_completions": 0}, ensure_ascii=False))
        return
    if not args.real or not args.phase:
        parser.error("Use --preflight or explicitly authorized --real --phase")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    real_session(args.phase, args.arm, args.run_id or f"{args.phase}-{args.arm}-{stamp}",
        development_turns=args.development_turns,
        revision_note=args.revision_note.read_text(encoding="utf8") if args.revision_note else None,
        audit=json.loads(args.audit.read_text(encoding="utf8")) if args.audit else None)


if __name__ == "__main__":
    main()
