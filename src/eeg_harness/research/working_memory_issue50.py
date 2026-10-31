"""Issue50 independent accounting, tool preflight and matched diagnostics.

Only this driver schedules controlled research sessions. It does not supply
correct actions, result IDs, gold values or task sequences to the live model.
Candidate method code lives in the common working-memory modules.
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
from .working_memory_issue48 import encoded
from .working_memory_issue49 import input_components

ROOT = PROJECT_ROOT / "artifacts" / "point1_task_memory" / "issue50"
LEDGER = ROOT / "budget.jsonl"
SPEC = PROJECT_ROOT / "config" / "point1_working_memory_issue50.json"
FINISH_CHOICE = {"type": "function", "function": {"name": "finish_task"}}
LIMITS = {"completions": 64, "api_tokens": 400000}
STALE_NOTICE = (
    "Budget checkpoint: this is an earlier immutable evidence view. Later actions may have executed "
    "but are not represented here. Deliver only the evidence actually present in this snapshot, "
    "state this resource limitation, and finish with partial status. Do not claim complete delivery "
    "or guess missing later results. The full execution trace is retained locally."
)


def protocol():
    return json.loads(SPEC.read_text(encoding="utf8"))


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


class Issue50Client:
    """Reliable actual-wire reservations and an immutable final-view lease.

    A successful normal reservation also leaves room for the *current* actual
    final view. That snapshot is retained rather than pretending a prediction
    bounds arbitrary future tool results. A fallback snapshot is explicitly a
    partial checkpoint; the controller must not represent unobserved later
    results as delivered. The live-session lock prevents another run spending
    the protected remainder between a decision and its final answer.
    """
    def __init__(self, client, ledger, *, phase, arm, request_journal=None, spec=None):
        self.client, self.ledger = client, Path(ledger)
        self.spec = spec or protocol()
        if self.spec["limits"] != LIMITS:
            raise StageBudgetExhausted("Issue50 limits differ from the stage authorization")
        if phase not in {"development", "layer1", "layer2"}:
            raise ValueError("Unknown Issue50 phase")
        if arm not in self.spec["arms"]:
            raise ValueError("Unknown Issue50 arm")
        self.context = {"phase": phase, "arm": arm}
        self.request_journal = Path(request_journal) if request_journal else None
        self.final_only = False
        self.delivery_checkpoint = None
        self._lease = None
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        header = {"event": "opened", "stage": "issue50", "version": 1,
                  "max_requests": 64, "max_tokens": 400000}
        with _ledger_lock(self.ledger):
            rows = _rows(self.ledger)
            if not rows:
                _append(self.ledger, header)
            elif any(rows[0].get(k) != v for k, v in header.items()):
                raise StageBudgetExhausted("Do not reuse, reset or resize another stage's ledger")

    @property
    def request_count(self): return self.client.request_count
    @property
    def total_usage(self): return self.client.total_usage
    @property
    def model(self): return self.client.model
    @property
    def finish_reasons(self): return getattr(self.client, "finish_reasons", [])

    def set_context(self, **values):
        if set(values) & {"phase", "arm"}:
            raise ValueError("Accounting identity is immutable")
        if "turn" in values and values["turn"] != self.context.get("turn"):
            self.final_only = False
            self.delivery_checkpoint = None
            self._lease = None
        self.context.update(values)

    def wire(self, messages, tools, tool_choice="auto"):
        raw = self.client.client
        body = {"model": self.model, "messages": messages, "max_tokens": raw.max_tokens,
                "stream": False, "thinking": {"type": getattr(raw, "thinking", "disabled")}}
        if tools:
            body.update(tools=tools, tool_choice=tool_choice)
        return body

    def reservation(self, messages, tools, tool_choice="auto"):
        return len(encoded(self.wire(messages, tools, tool_choice))) + self.client.client.max_tokens

    @staticmethod
    def _fits(rows, calls, tokens):
        starts = {r["request_id"]: r for r in rows if r["event"] == "reserved"}
        ends = {r["request_id"]: r for r in rows if r["event"] in {"received", "failed"}}
        used = sum(ends[i]["total_tokens"] if ends.get(i, {}).get("total_tokens") is not None
                   else r["reserved_tokens"] for i, r in starts.items())
        return len(starts) + calls <= 64 and used + tokens <= 400000

    def prepare_decision(self, messages, tools, final_messages, final_tools):
        if self.final_only:
            return True
        normal = self.reservation(messages, tools)
        final = self.reservation(final_messages, final_tools, FINISH_CHOICE)
        current = {"messages": deepcopy(final_messages), "tools": deepcopy(final_tools),
                   "captured_context": dict(self.context), "reason": "budget_checkpoint",
                   "checkpoint_only": False, "stale": False, "reserved_tokens": final}
        lease = deepcopy(current)
        lease["messages"].append({"role": "system", "content": STALE_NOTICE})
        lease["stale"] = lease["checkpoint_only"] = True
        lease["reserved_tokens"] = self.reservation(lease["messages"], final_tools, FINISH_CHOICE)
        with _ledger_lock(self.ledger):
            rows = _rows(self.ledger)
            if self._fits(rows, 2, normal + lease["reserved_tokens"]):
                self._lease = lease
                action = "continue_with_current_final_lease"
            else:
                chosen = current if self._fits(rows, 1, final) else self._lease
                if chosen is None or not self._fits(rows, 1, chosen["reserved_tokens"]):
                    _append(self.ledger, {"event": "decision_reservation_rejected", "context": dict(self.context),
                        "normal_reserve": normal, "current_final_reserve": final, "timestamp_utc": time.time()})
                    raise LLMServiceError("STAGE_BUDGET_EXHAUSTED", "No reliable final checkpoint fits the remaining stage budget")
                self.delivery_checkpoint = deepcopy(chosen)
                self.delivery_checkpoint["stale"] = chosen is not current
                self.final_only = True
                action = "deliver_previous_checkpoint" if chosen is not current else "deliver_current_checkpoint"
            _append(self.ledger, {"event": "final_lease_decision", "context": dict(self.context),
                "action": action, "normal_reserve": normal, "current_final_reserve": final,
                "lease_reserve": (self.delivery_checkpoint or self._lease)["reserved_tokens"],
                "message_sha256": digest((self.delivery_checkpoint or self._lease)["messages"]),
                "timestamp_utc": time.time()})
        return self.final_only

    def complete(self, messages, tools, tool_choice="auto"):
        raw = self.client.client
        if raw.max_retries != 0:
            raise LLMServiceError("AUTOMATIC_RETRY_FORBIDDEN", "Every attempt must be separately counted; retries must be zero")
        if self.final_only and self.delivery_checkpoint is not None:
            if (messages != self.delivery_checkpoint["messages"] or tools != self.delivery_checkpoint["tools"]
                    or tool_choice != FINISH_CHOICE):
                raise LLMServiceError("FINAL_CHECKPOINT_MISMATCH", "Send the reserved immutable final snapshot without adding or replacing its evidence")
        body = self.wire(messages, tools, tool_choice)
        payload_bytes = len(encoded(body))
        reserve = payload_bytes + raw.max_tokens
        ident = str(uuid.uuid4())
        with _ledger_lock(self.ledger):
            rows = _rows(self.ledger)
            if not self._fits(rows, 1, reserve):
                _append(self.ledger, {"event": "reservation_rejected", "context": dict(self.context),
                    "requested_reserve": reserve, "timestamp_utc": time.time()})
                raise LLMServiceError("STAGE_BUDGET_EXHAUSTED", "Issue50 actual-wire reservation exceeds the independent stage budget")
            _append(self.ledger, {"event": "reserved", "request_id": ident, "context": dict(self.context),
                "input_bytes": payload_bytes, "output_cap": raw.max_tokens, "reserved_tokens": reserve,
                "final_only": self.final_only, "timestamp_utc": time.time()})
        start = time.perf_counter()
        try:
            if self.request_journal:
                _append(self.request_journal, {"request_id": ident, "context": dict(self.context),
                    "messages": messages, "tools": tools, "tool_choice": tool_choice,
                    "actual_wire_payload_bytes": payload_bytes,
                    "settings": {"model": self.model, "max_output_tokens": raw.max_tokens,
                        "max_retries": raw.max_retries, "timeout_seconds": raw.timeout,
                        "thinking": getattr(raw, "thinking", "disabled")},
                    "components": input_components(messages, tools), "timestamp_utc": time.time()})
            response = self.client.complete(messages, tools, tool_choice)
        except Exception as exc:
            with _ledger_lock(self.ledger):
                _append(self.ledger, {"event": "failed", "request_id": ident,
                    "error_type": type(exc).__name__, "duration_seconds": time.perf_counter() - start,
                    "timestamp_utc": time.time()})
            raise
        usage = dict(raw.last_usage)
        with _ledger_lock(self.ledger):
            _append(self.ledger, {"event": "received", "request_id": ident,
                "response_model_reported": raw.last_response_model, "finish_reason": raw.last_finish_reason,
                "usage": usage, "total_tokens": usage.get("total_tokens"),
                "duration_seconds": time.perf_counter() - start, "timestamp_utc": time.time()})
        return response


def records_for(variant="confirmation"):
    records = synthetic_records()
    if variant == "development":
        return records
    if variant != "confirmation":
        raise ValueError("Unknown synthetic variant")
    for alias, record in records.items():
        t = np.arange(record.data.shape[1], dtype=float) / record.sfreq
        if alias == "A":
            signals = [np.where(t < 3, 8e-6, 14e-6) * np.sin(2*np.pi*10*t) + 2e-6*np.sin(2*np.pi*24*t),
                       np.where(t < 4, 12e-6, 6e-6) * np.sin(2*np.pi*6*t) + 2e-6*np.sin(2*np.pi*28*t)]
        else:
            signals = [10e-6*np.sin(2*np.pi*10*t) + 3e-6*np.sin(2*np.pi*5*t),
                       np.where(t < 4, 9e-6, 4e-6) * np.sin(2*np.pi*6*t)]
        events = EventSet(tuple(EEGEvent(label, onset, source_index=i)
            for i, (label, onset) in enumerate(protocol()["data_definition"][alias]["events"])),
            f"synthetic://issue50-{alias}-events")
        records[alias] = replace(record, data=np.asarray(signals, dtype=record.data.dtype), events=events,
                                source=f"synthetic://issue50-confirmation-{alias}")
    return records


def scientific_preflight():
    """Independent numerical oracle over actual Registry/Executor; no LLM."""
    spec = protocol()["evaluation_only"]["preflight"]
    records = records_for()
    store = WorkingMemoryStore("issue50-science-preflight", records)
    operations, checks = [], []
    def run(alias, name, args, expected=True):
        result = store.contexts[alias].execute(ToolRequest(name, args, f"preflight-{len(operations)+1}")).to_dict()
        operations.append({"record": alias, "tool": name, "arguments": args, "result": result})
        assert result["success"] == expected, operations[-1]
        return result["data"]
    info = run("A", "record_info", {})
    assert info["sfreq"] == 128 and info["duration_seconds"] == 8
    for alias in ("A", "B"):
        for window in (spec["continuous_old"], spec["continuous_new"]):
            for tool in ("amplitude", "psd"):
                data = run(alias, tool, window)
                for channel in window["channels"]:
                    for field in (["rms"] if tool == "amplitude" else data[channel]):
                        expected = independent_oracle(records[alias], {"capability": tool, "parameters": window}, [channel, field])
                        actual = float(data[channel][field])
                        checks.append({"record": alias, "tool": tool, "scope": window, "field": [channel, field],
                            "actual": actual, "oracle": expected, "valid": bool(np.isclose(actual, expected, rtol=.005, atol=5e-13))})
    scope = spec["event_scope"]
    epochs = run("A", "create_epochs", scope)
    artifact = epochs["artifact_id"]
    powers = run("A", "event_bandpower", {"artifact_id": artifact})
    quality = run("A", "epoch_quality", {"artifact_id": artifact})
    assert epochs["valid_epoch_count"] == 3
    assert quality["artifact_id"] == powers["artifact_id"] == artifact
    assert store.contexts["A"].artifacts[artifact].baseline is None
    for channel, values in powers["conditions"]["stimulus"]["channels"].items():
        for band, actual in values.items():
            field = ["conditions", "stimulus", "channels", channel, band]
            expected = independent_oracle(records["A"], {"capability": "event_bandpower", "parameters": scope}, field)
            checks.append({"record": "A", "tool": "event_bandpower", "scope": scope, "field": field,
                "actual": actual, "oracle": expected, "valid": bool(np.isclose(actual, expected, rtol=1e-6, atol=5e-13))})
    short = run("A", "create_epochs", dict(scope, tmax=spec["negative_event_window_seconds"]))
    run("A", "event_bandpower", {"artifact_id": short["artifact_id"]}, expected=False)
    assert all(c["valid"] for c in checks)
    return {"status": "passed", "kind": "controlled_real_executor_not_agent_autonomy",
        "operations": operations, "oracle_checks": checks,
        "units": "amplitude V; power V²; continuous absolute seconds; epoch relative seconds",
        "quality": "Actual empirical measurements, no clinical threshold or filtering invented"}


def build_agent(client, arm, session_id, *, variant="confirmation"):
    spec = protocol()
    settings = spec["arms"][arm]
    options = {"memory_version": settings["architecture"], "context_mode": settings["context_mode"]}
    if settings["architecture"] == "lifecycle":
        options["request_closure"] = True
    return WorkingMemoryEEGAgent(client, records_for(variant), session_id=session_id,
                                **spec["agent_settings"], **options)


def seed_controlled_history(agent):
    """Same real-tool history for every layer2 mode; never model autonomy.

    IDs below are obtained from actual completed calls, not future answers.
    Later live turns receive only the normal context interface. This preparation
    is archived separately so it cannot be reported as an autonomous session.
    """
    controller = agent.working_memory
    spec = protocol()["evaluation_only"]["preflight"]
    actions = []
    def call(name, arguments):
        # Match the common Agent's pre-action context construction. This is
        # controlled preparation, not a claim that a model chose these actions.
        controller.build_messages()
        ident = f"controlled-{len(actions)+1}"
        assistant = {"role": "assistant", "content": None, "tool_calls": [
            {"id": ident, "type": "function", "function": {
                "name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}}]}
        result = controller.execute(ToolRequest(name, arguments, ident)).to_dict()
        controller.observe_exchange(assistant, [{"role": "tool", "tool_call_id": ident,
            "name": name, "content": json.dumps(result, ensure_ascii=False, allow_nan=False)}])
        actions.append({"controlled": True, "tool": name, "arguments": arguments, "result": result})
        if not result["success"]:
            raise AssertionError(actions[-1])
        return result
    def finish():
        call("finish_task", {"status": "completed", "answer": "受控历史准备：本次要求的实际工具结果已保存；不是模型自主运行记录。"})
        controller.on_stop("completed")
    controller.begin_turn("请给出记录A的SYNTH-C1在0到2秒的RMS和alpha绝对功率，保留范围和单位。")
    call("focus_task", {"title": "初始连续分析", "record": "A", "expected_tools": ["amplitude", "psd"]})
    call("amplitude", {"record": "A", **spec["continuous_old"]})
    call("psd", {"record": "A", **spec["continuous_old"]})
    first_power = next(e for e in controller.store.entries if e.capability == "psd")
    finish()
    controller.begin_turn("将记录A的SYNTH-C1连续窗口改为4到6秒，计算alpha绝对功率，保留旧结果。")
    call("psd", {"record": "A", **spec["continuous_new"], "inherit_result": first_power.task_id})
    finish()
    controller.begin_turn("请分析记录A的stimulus事件发生后0到1.25秒，给出SYNTH-C1和SYNTH-C2的theta绝对功率与实际试次数，不做基线校正或筛选。")
    call("focus_task", {"title": "事件试次及频带", "record": "A", "expected_tools": ["create_epochs", "event_bandpower"]})
    call("create_epochs", {"record": "A", **spec["event_scope"]})
    artifact = next(reversed(controller.store.contexts["A"].artifacts))
    call("event_bandpower", {"record": "A", "artifact_id": artifact})
    finish()
    def canonical(value):
        if isinstance(value, dict):
            return {k: canonical(v) for k, v in value.items() if k != "artifact_id"}
        if isinstance(value, list):
            return [canonical(v) for v in value]
        return value
    scientific_content = [{"record": e.record, "capability": e.capability,
        "parameters": e.parameters, "result": canonical(e.result)} for e in controller.store.entries]
    return {"kind": "controlled_real_executor_history_not_agent_autonomy", "actions": actions,
            "history": controller.snapshot(), "artifact_id": artifact,
            "entry_count": len(controller.store.entries), "scientific_content_sha256": digest(scientific_content),
            "hash_exclusion": "Only runtime artifact ID excluded; scope, fingerprints, actual numerical results and sources retained"}


def budget_preflight():
    """Actual admission/final views, not fabricated full-conversation cost."""
    samples = []
    spec = protocol()
    for layer in ("layer1", "layer2"):
        for arm in spec["layer_order"][layer]:
            agent = build_agent(None, arm, "preflight-"+layer+"-"+arm)
            history = seed_controlled_history(agent) if layer == "layer2" else None
            controller = agent.working_memory
            controller.begin_turn(spec[layer]["requests"][0])
            normal, tools = controller.build_messages(), controller.tool_definitions()
            final, final_tools = controller.build_final_messages()
            def reserve(messages, toolset, choice="auto"):
                body = {"model": "deepseek-chat", "messages": messages,
                    "max_tokens": spec["model_settings"]["max_output_tokens"], "stream": False,
                    "thinking": {"type": "disabled"}, "tools": toolset, "tool_choice": choice}
                return len(encoded(body)) + spec["model_settings"]["max_output_tokens"]
            snapshot = final + [{"role": "system", "content": STALE_NOTICE}]
            samples.append({"layer": layer, "arm": arm, "initial_reserve": reserve(normal, tools),
                "current_final_reserve": reserve(final, final_tools, FINISH_CHOICE),
                "fallback_lease_reserve": reserve(snapshot, final_tools, FINISH_CHOICE),
                "initial_message_bytes": len(encoded(normal)), "initial_tool_bytes": len(encoded(tools)),
                "real_seed_entries": history["entry_count"] if history else 0,
                "context_mode": spec["arms"][arm]["context_mode"]})
    return {"status": "passed", "samples": samples,
        "interpretation": "Measured actual views. Admission margins are scheduling safeguards, not per-arm caps or proof arbitrary conversations fit."}


def preflight():
    return {"protocol_sha256": hashlib.sha256(SPEC.read_bytes()).hexdigest(), "external_completions": 0,
            "scientific": scientific_preflight(), "budget": budget_preflight()}


def _relevant_window_clarification(result):
    """Common reply gate examines actual output, not arm-specific task cards."""
    if result.get("stop_reason") not in {"clarification_required", "partial"}:
        return False
    if any(r.get("success") and r.get("tool_name") in {"create_epochs", "epoch_summary", "event_bandpower", "epoch_quality"}
           for r in result.get("tool_results", [])):
        return False
    # This is a prespecified evaluator-side reply condition, never a candidate
    # parser or source of tool choices. The actual reply is saved in the trace.
    return bool(re.search(r"窗口|时间范围|时窗|时间段|tmin|tmax|window|epoch", result.get("final_answer", ""), re.I))


def _safe_write(path, value):
    with Path(path).open("x", encoding="utf8") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)


def _start_arm(ledger, phase, arm, run_id, manifest):
    spec = protocol()
    with _ledger_lock(ledger):
        rows = _rows(ledger)
        if phase == "development":
            prior = [r for r in rows if r["event"] == "arm_started" and r["phase"] == phase]
            if len(prior) >= 3:
                raise StageBudgetExhausted("Initial development plus at most two root-caused revisions; no additional online trials")
        else:
            frozen = {"candidate_commit": manifest["candidate_commit"],
                      "protocol_sha256": manifest["protocol_sha256"], "model_settings": manifest["model_settings"],
                      "model_requested": manifest["model_requested"]}
            previous = next((r for r in rows if r["event"] == "layer_frozen" and r["phase"] == phase), None)
            if previous and any(previous.get(k) != v for k, v in frozen.items()):
                raise StageBudgetExhausted("The paired layer candidate, model and protocol are frozen")
            started = [r["arm"] for r in rows if r["event"] == "arm_started" and r["phase"] == phase]
            order = spec["layer_order"][phase]
            if arm in started or started != order[:len(started)] or arm != order[len(started)]:
                raise StageBudgetExhausted("Run each matched arm once in the frozen order")
            if started and not any(r["event"] == "arm_ended" and r["phase"] == phase and r["arm"] == started[-1] for r in rows):
                raise StageBudgetExhausted("Inspect unfinished previous arm; do not silently retry")
            if not previous:
                minimum_tokens = spec["budget_policy"]["paired_admission_tokens"][phase]
                minimum_calls = spec["budget_policy"]["paired_admission_calls"][phase]
                if not Issue50Client._fits(rows, minimum_calls, minimum_tokens):
                    raise StageBudgetExhausted("Insufficient remaining budget to admit the complete matched diagnostic unit")
                if phase == "layer2" and not any(r["event"] == "managed_basic_path_observed" for r in rows):
                    raise StageBudgetExhausted("Layer2 requires real new-path numerical success from layer1")
                _append(ledger, {"event": "layer_frozen", "phase": phase, **frozen,
                    "admission_calls_margin": minimum_calls, "admission_tokens_margin": minimum_tokens,
                    "timestamp_utc": time.time()})
        _append(ledger, {"event": "arm_started", "phase": phase, "arm": arm,
            "run_id": run_id, "timestamp_utc": time.time()})


def _real_session(phase, arm, run_id):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,127}", run_id):
        raise ValueError("Use a fresh simple run ID")
    spec = protocol()
    if phase not in {"development", "layer1", "layer2"} or arm not in spec["arms"]:
        raise ValueError("Unknown phase/arm")
    if phase == "development" and arm != "development":
        raise ValueError("Development uses the new managed architecture")
    ready = preflight()  # Before credentials and any network.
    if phase != "development" and subprocess.check_output(["git", "status", "--porcelain"], cwd=PROJECT_ROOT, text=True).strip():
        raise RuntimeError("Commit a clean candidate before matched confirmation")
    directory = ROOT / run_id
    directory.mkdir(parents=True, exist_ok=False)
    raw = OpenAICompatibleClient.from_env()
    raw.max_retries = 0
    raw.timeout = min(raw.timeout, spec["model_settings"]["timeout_seconds"])
    raw.max_tokens = spec["model_settings"]["max_output_tokens"]
    manifest = {"candidate_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True).strip(),
        "protocol_sha256": hashlib.sha256(SPEC.read_bytes()).hexdigest(), "phase": phase, "arm": arm,
        "model_requested": raw.model, "model_settings": {"max_output_tokens": raw.max_tokens, "max_retries": 0,
            "timeout_seconds": raw.timeout, "thinking": getattr(raw, "thinking", "disabled")},
        "agent_settings": spec["agent_settings"],
        "data_sha256": {alias: hashlib.sha256(record.data.tobytes()).hexdigest()
                        for alias, record in records_for("development" if phase == "development" else "confirmation").items()},
        "timestamp_utc": time.time()}
    for filename, data in (("protocol.json", spec), ("manifest.json", manifest), ("preflight.json", ready)):
        _safe_write(directory / filename, data)
    journal = JournaledBudgetClient(raw, directory / "responses.jsonl", max_requests=64, max_total_tokens=400000)
    client = Issue50Client(journal, LEDGER, phase=phase, arm=arm, request_journal=directory / "requests.jsonl")
    _start_arm(LEDGER, phase, arm, run_id, manifest)
    client.set_context(run_id=run_id, protocol_sha256=manifest["protocol_sha256"])
    agent = build_agent(client, arm, run_id, variant="development" if phase == "development" else "confirmation")
    if phase == "layer2":
        _safe_write(directory / "controlled-history.json", seed_controlled_history(agent))
    selected = spec[phase]["requests"]
    prior, outcome = None, "driver_error"
    try:
        for number, text in enumerate(selected, 1):
            if number == 2 and phase in {"development", "layer1"} and not _relevant_window_clarification(prior.to_dict()):
                _append(directory / "driver_events.jsonl", {"event": "continuation_not_sent", "turn": number,
                    "reason": "no_actual_relevant_window_clarification", "prior_stop": prior.stop_reason})
                outcome = "no_relevant_clarification"
                break
            client.set_context(turn=number)
            result = agent.run(text) if number == 1 and phase != "layer2" else agent.continue_run(text)
            _safe_write(directory / f"turn-{number}.json", result.to_dict())
            print(json.dumps({"phase": phase, "arm": arm, "turn": number,
                "stop_reason": result.stop_reason, "rounds": result.rounds, "tool_calls": result.tool_calls,
                "answer": result.final_answer, "budget": ledger_totals(LEDGER)}, ensure_ascii=False), flush=True)
            prior, outcome = result, result.stop_reason
            if result.stop_reason in {"llm_error", "budget_exhausted", "no_progress", "context_capacity", "evidence_capacity", "deadline_exceeded", "round_limit", "tool_call_limit"}:
                break
        if phase == "layer1" and arm == "managed-full":
            actual = {e.capability for e in agent.working_memory.store.entries if e.status == "completed"}
            if {"amplitude", "psd", "create_epochs", "event_bandpower"}.issubset(actual):
                with _ledger_lock(LEDGER):
                    _append(LEDGER, {"event": "managed_basic_path_observed", "run_id": run_id,
                        "meaning": "Actual successful numerical operations only; not proof of complete answer or benefit",
                        "timestamp_utc": time.time()})
    finally:
        with _ledger_lock(LEDGER):
            _append(LEDGER, {"event": "arm_ended", "phase": phase, "arm": arm, "run_id": run_id,
                "stop_reason": outcome, "timestamp_utc": time.time()})
    return agent


def real_session(phase, arm, run_id):
    ROOT.mkdir(parents=True, exist_ok=True)
    with _ledger_lock(ROOT / "active-live-session"):
        return _real_session(phase, arm, run_id)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--real", action="store_true")
    parser.add_argument("--phase", choices=("development", "layer1", "layer2"))
    parser.add_argument("--arm", choices=tuple(protocol()["arms"]))
    parser.add_argument("--run-id")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.preflight:
        data = preflight()
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            _safe_write(args.output, data)
        print(json.dumps({"scientific": data["scientific"]["status"], "oracle_checks": len(data["scientific"]["oracle_checks"]),
                          "budget": data["budget"], "external_completions": 0}, ensure_ascii=False))
        return
    if not args.real or not args.phase or not args.arm:
        parser.error("Use --preflight or explicitly authorized --real --phase --arm")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    real_session(args.phase, args.arm, args.run_id or f"{args.phase}-{args.arm}-{stamp}")


if __name__ == "__main__":
    main()
