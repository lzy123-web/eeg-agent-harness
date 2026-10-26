"""Issue48 independent cumulative budget and ordinary-language validation.

This is a research driver, not a planner. Only natural requests, synthetic
records and common tool/state interfaces enter WorkingMemoryEEGAgent. Protocol
criteria never enter model messages. No network access without explicit --real.
"""
import argparse
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
from ..working_memory_agent import WorkingMemoryEEGAgent
from .task_memory import PROJECT_ROOT, synthetic_records
from .integrated_method.v2_validation import JournaledBudgetClient
from .task_memory_issue39_budget import _append, _ledger_lock, _rows, ledger_totals, StageBudgetExhausted

ROOT = PROJECT_ROOT / "artifacts" / "point1_task_memory" / "issue48"
LEDGER = ROOT / "budget.jsonl"
SPEC = PROJECT_ROOT / "config" / "point1_working_memory_issue48.json"


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf8")


def input_components(messages, tools):
    """Serialized bytes for attribution, explicitly NOT category token counts."""
    components = {"system_instructions": sum(len(encoded(m)) for m in messages if m.get("role") == "system"),
                  "tool_schema": len(encoded(tools)), "user_original": 0,
                  "current_state": 0, "history_index": 0, "exact_evidence": 0,
                  "active_trajectory": 0, "restored_trajectory": 0}
    found_state = False
    for message in messages:
        if message.get("role") == "system":
            continue
        content = message.get("content")
        try:
            payload = json.loads(content) if isinstance(content, str) else None
        except (ValueError, TypeError):
            payload = None
        if not found_state and isinstance(payload, dict) and "current_request" in payload:
            found_state = True
            groups = {
                "user_original": {k: payload[k] for k in ("user_requests", "current_request") if k in payload},
                "history_index": payload.get("archived_summaries", []),
                "exact_evidence": payload.get("exact_evidence", []),
                "restored_trajectory": payload.get("restored_trajectories", []),
                "current_state": {k: v for k, v in payload.items() if k not in {
                    "user_requests", "current_request", "archived_summaries", "exact_evidence", "restored_trajectories"}},
            }
            for key, value in groups.items():
                components[key] += len(encoded(value))
        elif message.get("role") == "user":
            components["user_original"] += len(encoded(message))
        else:
            components["active_trajectory"] += len(encoded(message))
    total = len(encoded({"messages": messages, "tools": tools, "tool_choice": "auto"}))
    return {"unit": "serialized_utf8_bytes_not_api_tokens", "parts": components,
            "payload_bytes": total, "serialization_envelope_bytes": total-sum(components.values())}


def _charged(rows, predicate):
    starts = {r["request_id"]: r for r in rows if r["event"] == "reserved" and predicate(r.get("context", {}))}
    ends = {r["request_id"]: r for r in rows if r["event"] in {"received", "failed"}}
    return len(starts), sum(ends[k]["total_tokens"] if k in ends and ends[k].get("total_tokens") is not None
                            else start["reserved_tokens"] for k, start in starts.items())


class Issue48Client:
    """One atomic global/phase/session reservation with append-only settlement."""
    def __init__(self, client, ledger, *, phase, case, request_journal=None, protocol=None):
        if phase not in {"development", "confirmation"}:
            raise ValueError("Unknown phase")
        self.client, self.ledger = client, Path(ledger)
        self.protocol = protocol or json.loads(SPEC.read_text(encoding="utf8"))
        if phase == "confirmation" and case not in self.protocol["confirmation"]:
            raise ValueError("Unknown confirmation case")
        self.context = {"phase": phase, "case": case}
        self.request_journal = Path(request_journal) if request_journal else None
        case_limits = {k: {"requests": v["request_cap"], "tokens": v["token_cap"]}
                       for k, v in self.protocol["confirmation"].items()}
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        with _ledger_lock(self.ledger):
            rows = _rows(self.ledger)
            if not rows:
                _append(self.ledger, {"event": "opened", "stage": "issue48", "version": 1,
                    "max_requests": 80, "max_tokens": 500000,
                    "development_requests": 24, "development_tokens": 150000,
                    "confirmation_caps": case_limits})
            elif any(rows[0].get(k) != v for k, v in {
                "event": "opened", "stage": "issue48", "max_requests": 80, "max_tokens": 500000,
                "development_requests": 24, "development_tokens": 150000,
                "confirmation_caps": case_limits}.items()):
                raise StageBudgetExhausted("Issue48 ledger does not match authorization; never reset it")

    @property
    def request_count(self):
        return self.client.request_count

    @property
    def total_usage(self):
        return self.client.total_usage

    @property
    def model(self):
        return self.client.model

    @property
    def finish_reasons(self):
        return getattr(self.client, "finish_reasons", [])

    def set_context(self, **values):
        if set(values) & {"phase", "case"}:
            raise ValueError("Cannot change accounting partition on an active client")
        self.context.update(values)

    def complete(self, messages, tools, tool_choice="auto"):
        raw = self.client.client
        wire_body = {"model": self.model, "messages": messages, "max_tokens": raw.max_tokens,
                     "stream": False, "thinking": {"type": getattr(raw, "thinking", "disabled")}}
        if tools:
            wire_body.update(tools=tools, tool_choice=tool_choice)
        payload_bytes = len(encoded(wire_body))
        reserve = payload_bytes + raw.max_tokens
        ident = uuid.uuid4().hex
        with _ledger_lock(self.ledger):
            rows = _rows(self.ledger)
            total_calls, total_tokens = _charged(rows, lambda c: True)
            dev_calls, dev_tokens = _charged(rows, lambda c: c.get("phase") == "development")
            case_calls, case_tokens = _charged(rows, lambda c: c.get("phase") == self.context["phase"] and c.get("case") == self.context["case"])
            problem = None
            if total_calls >= 80 or total_tokens + reserve > 500000:
                problem = "global"
            elif self.context["phase"] == "development" and (dev_calls >= 24 or dev_tokens + reserve > 150000):
                problem = "development_reserve"
            elif self.context["phase"] == "confirmation":
                limits = self.protocol["confirmation"][self.context["case"]]
                if case_calls >= limits["request_cap"] or case_tokens + reserve > limits["token_cap"]:
                    problem = "confirmation_case_reserve"
            if problem:
                _append(self.ledger, {"event": "blocked_before_network", "context": dict(self.context),
                    "reason": problem, "requested_reserve": reserve,
                    "actual_charged_tokens": total_tokens, "timestamp_utc": time.time()})
                raise LLMServiceError("STAGE_BUDGET_EXHAUSTED", "Issue48 reservation boundary: " + problem)
            _append(self.ledger, {"event": "reserved", "request_id": ident, "context": dict(self.context),
                "input_bytes": payload_bytes, "output_cap": raw.max_tokens,
                "reserved_tokens": reserve, "timestamp_utc": time.time()})
        start = time.perf_counter()
        try:
            if self.request_journal:
                _append(self.request_journal, {"request_id": ident, "context": dict(self.context),
                    "messages": messages, "tools": tools, "tool_choice": tool_choice,
                    "settings": {"model": self.model, "max_output_tokens": raw.max_tokens,
                                 "max_retries": raw.max_retries, "timeout_seconds": raw.timeout,
                                 "thinking": getattr(raw, "thinking", "disabled")},
                    "components": input_components(messages, tools), "timestamp_utc": time.time()})
            response = self.client.complete(messages, tools, tool_choice)
        except Exception as exc:
            with _ledger_lock(self.ledger):
                _append(self.ledger, {"event": "failed", "request_id": ident,
                    "error_type": type(exc).__name__, "duration_seconds": time.perf_counter()-start,
                    "timestamp_utc": time.time()})
            raise
        usage = dict(raw.last_usage)
        with _ledger_lock(self.ledger):
            _append(self.ledger, {"event": "received", "request_id": ident,
                "response_model_reported": raw.last_response_model, "finish_reason": raw.last_finish_reason,
                "usage": usage, "total_tokens": usage.get("total_tokens"),
                "duration_seconds": time.perf_counter()-start, "timestamp_utc": time.time()})
        return response


def records_for(variant):
    records = synthetic_records()
    if variant == "original":
        return records
    if variant != "confirmation":
        raise ValueError("Unknown synthetic variant")
    spec = json.loads(SPEC.read_text(encoding="utf8"))["data_definition"]
    for alias, record in records.items():
        t = np.arange(record.data.shape[1], dtype=float) / record.sfreq
        if alias == "A":
            signals = [np.where(t < 3, 12e-6, 8e-6)*np.sin(2*np.pi*10*t)+2e-6*np.sin(2*np.pi*24*t),
                       np.where(t < 3, 8e-6, 12e-6)*np.sin(2*np.pi*6*t)]
        else:
            signals = [10e-6*np.sin(2*np.pi*9*t)+2e-6*np.sin(2*np.pi*3*t),
                       np.where(t < 4, 6e-6, 12e-6)*np.sin(2*np.pi*6*t)+2e-6*np.sin(2*np.pi*30*t)]
        events = EventSet(tuple(EEGEvent(label, onset, source_index=i) for i, (label, onset) in enumerate(spec[alias]["events"])),
                          f"synthetic://issue48-{alias}-events")
        records[alias] = replace(record, data=np.asarray(signals, dtype=record.data.dtype), events=events,
                                source=f"synthetic://issue48-confirmation-{alias}")
    return records


def relevant_clarification(result, requirement):
    """Evaluator-side permission to send the prewritten user reply, not advice.

    A generic clarify status, wrong record/purpose or an already executed
    guessed window must not cause the driver to silently fill the science.
    """
    if result.get("stop_reason") != "clarification_required":
        return False
    if any(a.get("success") and a.get("tool_name") in {
            "create_epochs", "epoch_summary", "event_bandpower", "epoch_quality"}
           for a in result.get("tool_results", [])):
        return False
    for goal in (result.get("working_memory") or {}).get("subgoals", []):
        if goal.get("record") != requirement["record"] or goal.get("status") != "awaiting_input":
            continue
        for delivery in goal.get("deliveries", []):
            if delivery.get("tool") != requirement["tool"] or any(
                    delivery.get("scope", {}).get(k) != v for k, v in requirement["scope"].items()):
                continue
            missing = {i["field"] for i in goal.get("admission_issues", [])
                       if i.get("delivery") == delivery["key"] and i.get("code") == "MISSING_SCIENTIFIC_PARAMETER"}
            if set(requirement["missing_fields"]).issubset(missing):
                return True
    return False


def real_case(case, run_id, *, context_mode="working"):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,127}", run_id):
        raise ValueError("Run ID must be a new simple directory name")
    spec = json.loads(SPEC.read_text(encoding="utf8"))
    phase = "development" if case == "development" else "confirmation"
    selected = spec["development"] if phase == "development" else spec["confirmation"][case]
    directory = ROOT / run_id
    directory.mkdir(parents=True, exist_ok=False)
    protocol_hash = hashlib.sha256(SPEC.read_bytes()).hexdigest()
    raw = OpenAICompatibleClient.from_env()
    raw.max_retries = 0
    raw.timeout = min(raw.timeout, spec["model_settings"]["timeout_seconds"])
    raw.max_tokens = spec["model_settings"]["max_output_tokens"]
    journal = JournaledBudgetClient(raw, directory / "responses.jsonl", max_requests=80, max_total_tokens=500000)
    client = Issue48Client(journal, LEDGER, phase=phase, case=case,
                          request_journal=directory / "requests.jsonl", protocol=spec)
    client.set_context(run_id=run_id, protocol_sha256=protocol_hash, context_mode=context_mode)
    settings = spec["agent_settings"]
    agent = WorkingMemoryEEGAgent(client, records_for("original" if phase == "development" else "confirmation"),
                                 session_id=run_id, context_mode=context_mode, **settings)
    (directory / "protocol.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf8")
    manifest = {"candidate_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True).strip(),
                "protocol_sha256": protocol_hash, "phase": phase, "case": case,
                "context_mode": context_mode, "settings": settings, "timestamp_utc": time.time()}
    (directory / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf8")
    prior = None
    for number, request in enumerate(selected["requests"], 1):
        if number > 1 and selected.get("continuation_gate") == "clarification_required" and not relevant_clarification(
                prior.to_dict(), spec["evaluation_only"]["C_reply_gate"]):
            _append(directory / "driver_events.jsonl", {"event": "continuation_not_sent", "reason": "no_actual_clarification",
                                                       "prior_stop": prior.stop_reason, "turn": number})
            break
        client.set_context(turn=number)
        result = agent.run(request) if number == 1 else agent.continue_run(request)
        with (directory / f"turn-{number}.json").open("x", encoding="utf8") as f:
            json.dump(result.to_dict(), f, ensure_ascii=False, allow_nan=False, indent=2)
        print(json.dumps({"case": case, "turn": number, "stop_reason": result.stop_reason,
                          "rounds": result.rounds, "tool_calls": result.tool_calls,
                          "answer": result.final_answer, "budget": ledger_totals(LEDGER)}, ensure_ascii=False), flush=True)
        prior = result
        if result.stop_reason in {"llm_error", "budget_exhausted"}:
            break
    return agent


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--real", action="store_true", required=True)
    p.add_argument("--case", choices=("development", "A", "B", "C", "D"), required=True)
    p.add_argument("--run-id")
    p.add_argument("--context-mode", choices=("working", "full", "summary"), default="working")
    args = p.parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    real_case(args.case, args.run_id or f"{args.case}-{stamp}", context_mode=args.context_mode)


if __name__ == "__main__":
    main()
