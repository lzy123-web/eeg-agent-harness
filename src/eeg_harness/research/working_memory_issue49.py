"""Issue49 independent budget, actual-tool preflight and natural Agent driver.

Evaluator expectations and controlled preflight calls never enter live Agent
messages. No API use without --real and current-stage human authorization.
"""
import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import time
import uuid

import numpy as np

from ..events import EEGEvent, EventSet
from ..llm import OpenAICompatibleClient, LLMServiceError
from ..tooling import ToolRequest
from ..working_memory import WorkingMemoryStore
from ..working_memory_agent import WorkingMemoryEEGAgent
from .task_memory import PROJECT_ROOT, synthetic_records
from .task_memory_v2 import independent_oracle
from .integrated_method.v2_validation import JournaledBudgetClient
from .task_memory_issue39_budget import _append, _ledger_lock, _rows, ledger_totals, StageBudgetExhausted
from .working_memory_issue48 import encoded, input_components as _prior_components, _charged, relevant_clarification

ROOT = PROJECT_ROOT / "artifacts" / "point1_task_memory" / "issue49"
LEDGER = ROOT / "budget.jsonl"
SPEC = PROJECT_ROOT / "config" / "point1_working_memory_issue49.json"
FINISH_CHOICE = {"type": "function", "function": {"name": "finish_task"}}


def protocol():
    return json.loads(SPEC.read_text(encoding="utf8"))


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def input_components(messages,tools):
    """Preserve old attribution while placing strong-S history in its category."""
    out=_prior_components(messages,tools)
    for message in messages:
        try: payload=json.loads(message.get("content", ""))
        except (ValueError,TypeError): continue
        if not isinstance(payload,dict) or "current_request" not in payload: continue
        if "generic_summary" in payload:
            out["parts"]["history_index"]=len(encoded(payload["generic_summary"]))
            state={k:v for k,v in payload.items() if k not in {
                "user_requests","current_request","archived_summaries","generic_summary","exact_evidence","restored_trajectories"}}
            out["parts"]["current_state"]=len(encoded(state))
            out["serialization_envelope_bytes"]=out["payload_bytes"]-sum(out["parts"].values())
        break
    return out


class Issue49Client:
    """One append-only stage ledger; shared confirmation pool and finish reserve."""
    def __init__(self, client, ledger, *, phase, case, request_journal=None,
                 protocol=None, future_floors=None):
        if phase not in {"development", "confirmation"}:
            raise ValueError("Unknown phase")
        self.client, self.ledger = client, Path(ledger)
        self.protocol = protocol or globals()["protocol"]()
        if self.protocol["limits"] != {"completions":80,"api_tokens":500000,
                "development_completions":24,"development_tokens":150000,
                "confirmation_completions":56,"confirmation_tokens":350000}:
            raise StageBudgetExhausted("Protocol limits differ from this stage's authorization")
        if phase == "confirmation" and case not in self.protocol["confirmation"]:
            raise ValueError("Unknown confirmation case")
        self.context = {"phase": phase, "case": case}
        self.request_journal = Path(request_journal) if request_journal else None
        fixed_floors=self.protocol["budget_policy"]["future_floors"]
        if future_floors is not None and future_floors != fixed_floors:
            raise StageBudgetExhausted("Future admission/final floors are frozen by the protocol, not selected per run")
        self.future_floors = dict(fixed_floors)
        self.final_only = False
        self.final_reserve_ceiling_bytes = self.protocol["budget_policy"]["final_message_bytes_ceiling"]
        self.prepared = None
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        header = {"event":"opened", "stage":"issue49", "version":1,
                  "max_requests":80,"max_tokens":500000,
                  "development_requests":24,"development_tokens":150000,
                  "confirmation_requests":56,"confirmation_tokens":350000}
        with _ledger_lock(self.ledger):
            rows = _rows(self.ledger)
            if not rows:
                _append(self.ledger, header)
            elif any(rows[0].get(k) != v for k, v in header.items()):
                raise StageBudgetExhausted("Issue49 authorization differs; never reset or reuse a ledger")

    @property
    def request_count(self): return self.client.request_count
    @property
    def total_usage(self): return self.client.total_usage
    @property
    def model(self): return self.client.model
    @property
    def finish_reasons(self): return getattr(self.client, "finish_reasons", [])

    def set_context(self, **values):
        if set(values) & {"phase","case"}:
            raise ValueError("Cannot change accounting partition")
        if "turn" in values and values["turn"] != self.context.get("turn"):
            self.final_only = False
            self.prepared = None
        self.context.update(values)

    def wire(self, messages, tools, tool_choice="auto"):
        raw = self.client.client
        body = {"model":self.model,"messages":messages,"max_tokens":raw.max_tokens,
                "stream":False,"thinking":{"type":getattr(raw,"thinking","disabled")}}
        if tools:
            body.update(tools=tools, tool_choice=tool_choice)
        return body

    def reservation(self, messages, tools, tool_choice="auto"):
        return len(encoded(self.wire(messages,tools,tool_choice))) + self.client.client.max_tokens

    def _future(self, rows):
        if self.context["phase"] != "confirmation": return 0, 0
        order = self.protocol["confirmation_order"]
        remaining = order[order.index(self.context["case"])+1:]
        begun = {r["case"] for r in rows if r["event"] == "case_started"}
        unseen = [c for c in remaining if c not in begun]
        # Two minimal admission/final calls per unseen case. Not an allocation
        # cap and not a promise that its whole workflow can finish in two calls.
        return 2*len(unseen), sum(self.future_floors.get(c,0) for c in unseen)

    def _fits(self, rows, calls, tokens, *, keep_future=True):
        total_calls,total_tokens = _charged(rows,lambda c:True)
        phase_calls,phase_tokens = _charged(rows,lambda c:c.get("phase")==self.context["phase"])
        future_calls,future_tokens = self._future(rows) if keep_future else (0,0)
        cap_calls,cap_tokens = (24,150000) if self.context["phase"]=="development" else (56,350000)
        if total_calls+calls+future_calls>80 or total_tokens+tokens+future_tokens>500000: return "global"
        if phase_calls+calls+future_calls>cap_calls or phase_tokens+tokens+future_tokens>cap_tokens: return self.context["phase"]+"_pool"
        return None

    def prepare_decision(self, messages, tools, final_messages, final_tools):
        """Shared early close: reserve complete bounded final INPUT and output.

        The Controller checks the same default-spaced JSON byte limit on final
        messages. No empirical bytes/token ratio is used. A control view may
        still stop for scientific/context errors; this does not fabricate an
        answer. Actual final requests are reserved again atomically at send.
        """
        if self.final_only: return True
        actual_final = self.reservation(final_messages,final_tools,FINISH_CHOICE)
        envelope = self.reservation([],final_tools,FINISH_CHOICE)-len(encoded([]))
        final_ceiling = self.final_reserve_ceiling_bytes + envelope
        if len(encoded(final_messages)) > self.final_reserve_ceiling_bytes:
            raise LLMServiceError("FINAL_CONTEXT_CAPACITY", "Final message view exceeds its reliable reservation bound")
        normal = self.reservation(messages,tools)
        with _ledger_lock(self.ledger):
            rows = _rows(self.ledger)
            stop = self._fits(rows,2,normal+final_ceiling)
            final_problem = self._fits(rows,1,actual_final)
            _append(self.ledger,{"event":"decision_reserve_check","context":dict(self.context),
                "normal_request_reserve":normal,"actual_final_reserve":actual_final,
                "bounded_next_final_reserve":final_ceiling,"future_floor":self._future(rows)[1],
                "decision":"final_only" if stop else "continue", "reason":stop,
                "final_current_fit":final_problem is None,"timestamp_utc":time.time()})
            self.prepared = {"normal_reserve":normal,"final_ceiling":final_ceiling}
            self.final_only = bool(stop)
        return self.final_only

    def complete(self,messages,tools,tool_choice="auto"):
        raw = self.client.client
        payload_bytes=len(encoded(self.wire(messages,tools,tool_choice)))
        reserve=payload_bytes+raw.max_tokens
        ident=uuid.uuid4().hex
        forced_final = tool_choice == FINISH_CHOICE
        with _ledger_lock(self.ledger):
            rows=_rows(self.ledger)
            # Recheck ordinary+final space under this send's ledger lock.
            # The public real driver separately serializes live sessions; this
            # check alone is not a cross-process long-lived reservation lease.
            if self.prepared and not forced_final:
                problem=self._fits(rows,2,reserve+self.prepared["final_ceiling"])
            else:
                problem=self._fits(rows,1,reserve)
            if self.final_only and not forced_final:
                problem="finish_only_required"
            if problem:
                _append(self.ledger,{"event":"blocked_before_network","context":dict(self.context),
                    "reason":problem,"requested_reserve":reserve,"actual_charged_tokens":_charged(rows,lambda c:True)[1],
                    "timestamp_utc":time.time()})
                raise LLMServiceError("STAGE_BUDGET_EXHAUSTED","Issue49 reliable reservation: "+problem)
            _append(self.ledger,{"event":"reserved","request_id":ident,"context":dict(self.context),
                "input_bytes":payload_bytes,"output_cap":raw.max_tokens,"reserved_tokens":reserve,
                "final_only":forced_final,"timestamp_utc":time.time()})
        started=time.perf_counter()
        try:
            if self.request_journal:
                _append(self.request_journal,{"request_id":ident,"context":dict(self.context),
                    "messages":messages,"tools":tools,"tool_choice":tool_choice,
                    "actual_wire_payload_bytes":payload_bytes,
                    "settings":{"model":self.model,"max_output_tokens":raw.max_tokens,
                        "max_retries":raw.max_retries,"timeout_seconds":raw.timeout,
                        "thinking":getattr(raw,"thinking","disabled")},
                    "components":input_components(messages,tools),"timestamp_utc":time.time()})
            response=self.client.complete(messages,tools,tool_choice)
        except Exception as exc:
            with _ledger_lock(self.ledger):
                _append(self.ledger,{"event":"failed","request_id":ident,"error_type":type(exc).__name__,
                    "duration_seconds":time.perf_counter()-started,"timestamp_utc":time.time()})
            raise
        with _ledger_lock(self.ledger):
            usage=dict(raw.last_usage)
            _append(self.ledger,{"event":"received","request_id":ident,"response_model_reported":raw.last_response_model,
                "finish_reason":raw.last_finish_reason,"usage":usage,"total_tokens":usage.get("total_tokens"),
                "duration_seconds":time.perf_counter()-started,"timestamp_utc":time.time()})
        return response


def records_for(variant):
    records=synthetic_records()
    if variant=="original": return records
    if variant!="confirmation": raise ValueError("Unknown synthetic variant")
    spec=protocol()["data_definition"]
    for alias,record in records.items():
        t=np.arange(record.data.shape[1],dtype=float)/record.sfreq
        if alias=="A":
            signals=[np.where(t<3,7e-6,13e-6)*np.sin(2*np.pi*10*t)+2e-6*np.sin(2*np.pi*24*t),
                     np.where(t<4,11e-6,5e-6)*np.sin(2*np.pi*6*t)]
        else:
            signals=[9e-6*np.sin(2*np.pi*10*t)+3e-6*np.sin(2*np.pi*5*t),
                     np.where(t<4,10e-6,5e-6)*np.sin(2*np.pi*6*t)+2e-6*np.sin(2*np.pi*28*t)]
        events=EventSet(tuple(EEGEvent(label,onset,source_index=i) for i,(label,onset) in enumerate(spec[alias]["events"])),
                        f"synthetic://issue49-{alias}-events")
        records[alias]=replace(record,data=np.asarray(signals,dtype=record.data.dtype),events=events,
                              source=f"synthetic://issue49-confirmation-{alias}")
    return records


def _raw_result(context,name,args):
    value=context.execute(ToolRequest(name,args,f"preflight-{len(context.history)+1}")).to_dict()
    return value


def scientific_preflight():
    """Real Registry/Executor with synthetic records; no model, independent truth."""
    spec=protocol()["evaluation_only"]["preflight"]
    records=records_for("confirmation")
    store=WorkingMemoryStore("issue49-scientific-preflight",records)
    operations=[]; checks=[]
    def run(alias,name,args,*,expect=True):
        result=_raw_result(store.contexts[alias],name,args)
        operations.append({"record":alias,"tool":name,"arguments":args,"result":result,"expected_success":expect})
        if result["success"]!=expect: raise AssertionError(operations[-1])
        return result["data"]
    info=run("B","record_info",{})
    assert info["sfreq"]==128 and info["duration_seconds"]==8 and info["channel_names"]==list(records["B"].channel_names)
    for alias,window in (("A",spec["continuous_old"]),("A",spec["continuous_new"]),("B",spec["mixed_continuous"])):
        for tool in ("amplitude","psd"):
            data=run(alias,tool,window)
            fields=[[channel,field] for channel in window["channels"] for field in (["rms"] if tool=="amplitude" else data[channel])]
            for field in fields:
                actual=float(data[field[0]][field[1]])
                expected=independent_oracle(records[alias],{"capability":tool,"parameters":window},field)
                valid=bool(np.isclose(actual,expected,rtol=.005,atol=5e-13))
                checks.append({"record":alias,"tool":tool,"scope":window,"field":field,"actual":actual,"oracle":expected,"valid":valid})
    scope=spec["event_scope"]
    epochs=run("B","create_epochs",scope)
    artifact=epochs["artifact_id"]
    summary=run("B","epoch_summary",{"artifact_id":artifact})
    powers=run("B","event_bandpower",{"artifact_id":artifact})
    quality=run("B","epoch_quality",{"artifact_id":artifact})
    assert epochs["valid_epoch_count"]==summary["valid_epoch_count"]==3
    assert quality["artifact_id"]==powers["artifact_id"]==artifact
    assert store.contexts["B"].artifacts[artifact].baseline is None
    for channel,p in powers["conditions"]["target"]["channels"].items():
        for band,actual in p.items():
            field=["conditions","target","channels",channel,band]
            expected=independent_oracle(records["B"],{"capability":"event_bandpower","parameters":scope},field)
            checks.append({"record":"B","tool":"event_bandpower","scope":scope,"field":field,
                           "actual":actual,"oracle":expected,"valid":bool(np.isclose(actual,expected,rtol=1e-6,atol=5e-13))})
    short=run("B","create_epochs",dict(scope,tmax=spec["negative_event_window_seconds"]))
    run("B","event_bandpower",{"artifact_id":short["artifact_id"]},expect=False)
    assert all(c["valid"] for c in checks)
    return {"status":"passed","kind":"offline_expected_operations_not_agent_autonomy",
            "operations":operations,"oracle_checks":checks,
            "minimum_epoch_power_seconds":store.contexts["B"].executor.registry.get("event_bandpower").preconditions["min_artifact_duration_seconds"],
            "scope_units":"continuous absolute seconds; event relative seconds; amplitude V; power V²; count dimensionless",
            "quality_rule_status":"actual tool empirical rules, not clinical or user-specific acceptance thresholds"}


def budget_preflight():
    """Build real Controller views over actual results, no paid/Fake success score.

    The lower-bound floors protect future admission and settled final messages;
    they are not per-case budgets and cannot promise arbitrary model paths fit.
    """
    spec=protocol(); samples=[]; floors={}
    for case in spec["confirmation_order"]:
        agent=WorkingMemoryEEGAgent(None,records_for("confirmation"),session_id="preflight-"+case,
                                   **spec["agent_settings"])
        c=agent.working_memory
        text=spec["confirmation"][case]["requests"][0]
        c.begin_turn(text)
        initial=c.build_messages(); initial_tools=c.tool_definitions()
        s=c.store
        if case=="C": c.begin_turn(spec["confirmation"][case]["requests"][1])
        if case=="D":
            result=s.execute_numeric("record_info",{},record="B")
            assert result["status"]=="observed",result
        else:
            ds=[]; sources={}
            if case in {"A","B"}:
                window=spec["evaluation_only"]["preflight"]["continuous_old" if case=="A" else "mixed_continuous"]
                quote="记录A中SYNTH-C1在0到2秒" if case=="A" else "记录B：给出SYNTH-C1在1到3秒"
                for name in ("amplitude","psd"):
                    ds.append({"key":name,"tool":name,"scope":window})
                    sources[name]={"kind":"user","turn":1,"quote":quote}
            if case in {"B","C"}:
                scope=spec["evaluation_only"]["preflight"]["event_scope"]
                # Scientific preflight sources come only from its actual text;
                # this controlled view is not supplied to any real LLM.
                for name in ("create_epochs","event_bandpower"):
                    ds.append({"key":name,"tool":name,"scope":scope})
                    sources[name]={"fields":{
                        "labels":{"kind":"user","turn":1,"quote":"target"},
                        "tmin":{"kind":"user","turn":2 if case=="C" else 1,"quote":"0到1.25秒"},
                        "tmax":{"kind":"user","turn":2 if case=="C" else 1,"quote":"0到1.25秒"}}}
                if case=="C": sources["record"]={"kind":"user","turn":1,"quote":text}
            begin=s.begin_subgoal("离线预算视图", "A" if case=="A" else "B",deliveries=ds,parameter_sources=sources)
            assert begin["status"]=="active",begin
            for d in ds:
                if d["tool"]=="event_bandpower":
                    args={"artifact_id":artifact}
                else: args=d["scope"]
                result=s.execute_numeric(d["tool"],args)
                assert result["status"]=="observed",result
                if d["tool"]=="create_epochs": artifact=result["observation"]["result"]["data"]["artifact_id"]
            result=s.close_subgoal("completed")
            assert result["status"]=="completed",result
        final,final_tools=c.build_final_messages("budget_preflight")
        raw=type("Raw",(),{"max_tokens":spec["model_settings"]["max_output_tokens"],"thinking":"disabled"})()
        def reserve(messages,tools,choice):
            return len(encoded({"model":"deepseek-chat","messages":messages,"max_tokens":raw.max_tokens,
                "stream":False,"thinking":{"type":"disabled"},"tools":tools,"tool_choice":choice}))+raw.max_tokens
        first=reserve(initial,initial_tools,"auto"); last=reserve(final,final_tools,FINISH_CHOICE)
        rounding=spec["budget_policy"]["future_floor_rounding"]
        measured_floor=int(math.ceil((first+last)/rounding)*rounding)
        floors[case]=spec["budget_policy"]["future_floors"][case]
        if measured_floor>floors[case]:
            raise AssertionError(f"{case} actual preflight exceeds frozen future floor; review before network")
        samples.append({"case":case,"initial_reserve":first,"settled_final_reserve":last,
                        "measured_minimum_floor":measured_floor,"future_admission_and_final_floor":floors[case],"initial_components":input_components(initial,initial_tools),
                        "final_components":input_components(final,final_tools),"final_message_bytes":len(encoded(final))})
        assert len(encoded(final))<=spec["budget_policy"]["final_message_bytes_ceiling"]
        if case=="A":
            old_power=next(e for e in s.entries if e.capability=="psd")
            old_amplitude=next(e for e in s.entries if e.capability=="amplitude")
            c.begin_turn(spec["confirmation"]["A"]["requests"][1])
            revised=spec["evaluation_only"]["preflight"]["continuous_new"]
            created=s.begin_subgoal("离线旧新比较","A",deliveries=[{"key":"new","tool":"psd","scope":revised,"revision_of":old_power.task_id}],
                dependencies=[old_power.task_id],parameter_sources={"new":{"fields":{
                    "channels":{"kind":"result","result_id":old_power.task_id},
                    "start":{"kind":"user","turn":2,"quote":"4到6秒"},
                    "end":{"kind":"user","turn":2,"quote":"4到6秒"}}}})
            assert created["status"]=="active",created
            assert s.execute_numeric("psd",revised)["status"]=="observed"
            assert s.close_subgoal("completed")["status"]=="completed"
            final,final_tools=c.build_final_messages("budget_preflight")
            assert len(encoded(final))<=spec["budget_policy"]["final_message_bytes_ceiling"]
            samples.append({"case":"A_revised_comparison","settled_final_reserve":reserve(final,final_tools,FINISH_CHOICE),
                            "final_message_bytes":len(encoded(final)),"final_components":input_components(final,final_tools)})
            c.begin_turn(spec["confirmation"]["A"]["requests"][2])
            read=c.execute(ToolRequest("read_evidence",{"task_id":old_amplitude.task_id,"record":"A", "parameters":old_amplitude.parameters,
                "field_paths":[["SYNTH-C1","rms"]]},"preflight-read"))
            assert read.success,read
            final,final_tools=c.build_final_messages("budget_preflight")
            assert len(encoded(final))<=spec["budget_policy"]["final_message_bytes_ceiling"]
            samples.append({"case":"A_history_value","settled_final_reserve":reserve(final,final_tools,FINISH_CHOICE),
                            "final_message_bytes":len(encoded(final)),"final_components":input_components(final,final_tools)})
        if case=="B":
            old_goal=s.subgoals[-1]; old_power=next(e for e in s.entries if e.capability=="event_bandpower")
            c.begin_turn(spec["confirmation"]["B"]["requests"][1])
            restored=c.execute(ToolRequest("restore_subgoal",{"subgoal_id":old_goal.subgoal_id,"reason":"离线测量原试次的追加质量及最终输入"},"preflight-restore"))
            assert restored.success,restored
            created=s.begin_subgoal("离线原工件质量","B",deliveries=[{"key":"quality","tool":"epoch_quality","scope":scope}],
                dependencies=[old_power.task_id],parameter_sources={"quality":{"kind":"artifact","artifact_id":artifact}})
            assert created["status"]=="active",created
            measured=s.execute_numeric("epoch_quality",{"artifact_id":artifact})
            assert measured["status"]=="observed",measured
            assert measured["observation"]["result"]["data"]["artifact_id"]==artifact
            assert s.close_subgoal("completed")["status"]=="completed"
            final,final_tools=c.build_final_messages("budget_preflight")
            assert final and len(encoded(final))<=spec["budget_policy"]["final_message_bytes_ceiling"]
            samples.append({"case":"B_restored_quality","settled_final_reserve":reserve(final,final_tools,FINISH_CHOICE),
                            "final_message_bytes":len(encoded(final)),"final_components":input_components(final,final_tools),
                            "same_artifact_used":True,"new_numerical_tool":"epoch_quality"})
    return {"status":"passed","samples":samples,"future_floors":floors,
            "interpretation":"Actual serialized current views, not token estimates or guarantees for arbitrary model trajectories; no single-case token bins"}


def preflight():
    scientific=scientific_preflight(); budget=budget_preflight()
    return {"protocol_sha256":hashlib.sha256(SPEC.read_bytes()).hexdigest(),
            "external_completions":0,"scientific":scientific,"budget":budget}


def _start_case(ledger,case,run_id,manifest,floors):
    with _ledger_lock(ledger):
        rows=_rows(ledger)
        frozen={"candidate_commit":manifest["candidate_commit"],"protocol_sha256":manifest["protocol_sha256"],"future_floors":floors}
        previous=next((r for r in rows if r["event"]=="confirmation_frozen"),None)
        if previous and any(previous.get(k)!=v for k,v in frozen.items()):
            raise StageBudgetExhausted("Confirmation candidate/protocol/budget rules are frozen")
        started=[r["case"] for r in rows if r["event"]=="case_started"]
        if case in started or protocol()["confirmation_order"][:len(started)]!=started or protocol()["confirmation_order"][len(started)]!=case:
            raise StageBudgetExhausted("Confirmation must run once in frozen D,C,A,B order")
        if started and not any(r["event"]=="case_ended" and r["case"]==started[-1] for r in rows):
            raise StageBudgetExhausted("Previous case is not finished; inspect before another run")
        if not previous: _append(ledger,{"event":"confirmation_frozen",**frozen,"timestamp_utc":time.time()})
        _append(ledger,{"event":"case_started","case":case,"run_id":run_id,"timestamp_utc":time.time()})


def _real_case(case,run_id,*,context_mode="working"):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,127}",run_id): raise ValueError("Use a new simple run ID")
    spec=protocol(); phase="development" if case=="development" else "confirmation"
    selected=spec["development"] if phase=="development" else spec["confirmation"][case]
    ready=preflight()  # actual science and complete final views before credentials/network
    if phase=="confirmation" and subprocess.check_output(["git","status","--porcelain"],cwd=PROJECT_ROOT,text=True).strip():
        raise RuntimeError("Commit a clean candidate before confirmation")
    directory=ROOT/run_id; directory.mkdir(parents=True,exist_ok=False)
    protocol_hash=hashlib.sha256(SPEC.read_bytes()).hexdigest()
    manifest={"candidate_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=PROJECT_ROOT,text=True).strip(),
        "protocol_sha256":protocol_hash,"phase":phase,"case":case,"context_mode":context_mode,
        "settings":spec["agent_settings"],"future_floors":ready["budget"]["future_floors"],"timestamp_utc":time.time()}
    for name,value in (("protocol.json",spec),("manifest.json",manifest),("preflight.json",ready)):
        (directory/name).write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2),encoding="utf8")
    raw=OpenAICompatibleClient.from_env(); raw.max_retries=0
    raw.timeout=min(raw.timeout,spec["model_settings"]["timeout_seconds"])
    raw.max_tokens=spec["model_settings"]["max_output_tokens"]
    journal=JournaledBudgetClient(raw,directory/"responses.jsonl",max_requests=80,max_total_tokens=500000)
    client=Issue49Client(journal,LEDGER,phase=phase,case=case,request_journal=directory/"requests.jsonl",
                         protocol=spec,future_floors=ready["budget"]["future_floors"])
    if phase=="confirmation": _start_case(LEDGER,case,run_id,manifest,client.future_floors)
    client.set_context(run_id=run_id,protocol_sha256=protocol_hash,context_mode=context_mode)
    agent=WorkingMemoryEEGAgent(client,records_for("original" if phase=="development" else "confirmation"),
                               session_id=run_id,context_mode=context_mode,**spec["agent_settings"])
    prior=None; outcome="driver_error"
    try:
        for number,text in enumerate(selected["requests"],1):
            if number>1 and selected.get("continuation_gate")=="clarification_required" and not relevant_clarification(prior.to_dict(),spec["evaluation_only"]["C_reply_gate"]):
                _append(directory/"driver_events.jsonl",{"event":"continuation_not_sent","reason":"no_actual_relevant_clarification","prior_stop":prior.stop_reason,"turn":number})
                break
            client.set_context(turn=number)
            result=agent.run(text) if number==1 else agent.continue_run(text)
            with (directory/f"turn-{number}.json").open("x",encoding="utf8") as f:
                json.dump(result.to_dict(),f,ensure_ascii=False,allow_nan=False,indent=2)
            print(json.dumps({"case":case,"turn":number,"stop_reason":result.stop_reason,"rounds":result.rounds,
                "tool_calls":result.tool_calls,"answer":result.final_answer,"budget":ledger_totals(LEDGER)},ensure_ascii=False),flush=True)
            prior=result; outcome=result.stop_reason
            if result.stop_reason in {"llm_error","budget_exhausted"}: break
    finally:
        if phase=="confirmation":
            with _ledger_lock(LEDGER): _append(LEDGER,{"event":"case_ended","case":case,"run_id":run_id,"stop_reason":outcome,"timestamp_utc":time.time()})
    return agent


def real_case(case,run_id,*,context_mode="working"):
    ROOT.mkdir(parents=True,exist_ok=True)
    # One formal live session at a time protects the forthcoming final-view
    # reserve during tool execution. A killed process leaves this lock for
    # explicit inspection, never an automatic duplicate/retry or budget reset.
    with _ledger_lock(ROOT/"active-live-session"):
        return _real_case(case,run_id,context_mode=context_mode)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--real",action="store_true")
    p.add_argument("--preflight",action="store_true")
    p.add_argument("--case",choices=("development","A","B","C","D"))
    p.add_argument("--run-id")
    p.add_argument("--context-mode",choices=("working","full","summary"),default="working")
    p.add_argument("--output",type=Path)
    a=p.parse_args(argv)
    if a.preflight:
        value=preflight()
        if a.output:
            a.output.parent.mkdir(parents=True,exist_ok=True)
            with a.output.open("x",encoding="utf8") as f: json.dump(value,f,ensure_ascii=False,allow_nan=False,indent=2)
        print(json.dumps({"scientific":value["scientific"]["status"],"budget":value["budget"],"external_completions":0},ensure_ascii=False));return
    if not a.real or not a.case: p.error("Use --preflight or explicitly authorized --real --case")
    real_case(a.case,a.run_id or a.case+"-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f"),context_mode=a.context_mode)


if __name__=="__main__": main()
