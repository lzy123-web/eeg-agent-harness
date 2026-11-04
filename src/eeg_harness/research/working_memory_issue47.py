"""Issue47 independent budget and frozen ordinary-request validation driver.

The driver passes only records and natural requests to the existing Agent. It
never supplies a gold action sequence, goal ID or reference answer. All online
attempts share one append-only ledger; there are no automatic retries.
"""
import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import re

from ..events import EventSet
from ..llm import OpenAICompatibleClient, LLMServiceError
from ..working_memory_agent import WorkingMemoryEEGAgent
from .task_memory import PROJECT_ROOT, synthetic_records
from .integrated_method.v2_validation import JournaledBudgetClient
from .task_memory_issue39_budget import Issue39BudgetClient, StageBudgetExhausted, ledger_totals, _rows
from .working_memory_validation import audit_entries

ROOT = PROJECT_ROOT / "artifacts" / "point1_task_memory" / "issue47"
LEDGER = ROOT / "budget.jsonl"
SPEC = PROJECT_ROOT / "config" / "point1_working_memory_issue47.json"


class Issue47Client(Issue39BudgetClient):
    def __init__(self, client, ledger, *, phase, model_label=None):
        if phase not in {"development", "confirmation"}:
            raise ValueError("Unknown stage phase")
        super().__init__(client, ledger, max_requests=48, max_tokens=300000,
                         model_label=model_label, phase=phase)

    def complete(self, messages, tools, tool_choice="auto"):
        try:
            if self.context["phase"] == "development":
                rows = _rows(self.ledger)
                starts = {r["request_id"]: r for r in rows if r["event"] == "reserved" and r.get("context", {}).get("phase") == "development"}
                ends = {r["request_id"]: r for r in rows if r["event"] in {"received", "failed"}}
                charged = sum(ends.get(k, {}).get("total_tokens") if ends.get(k, {}).get("total_tokens") is not None else v["reserved_tokens"] for k, v in starts.items())
                reserve = len(json.dumps({"messages": messages, "tools": tools, "tool_choice": tool_choice}, ensure_ascii=False).encode("utf8")) + self.client.client.max_tokens
                if len(starts) >= 16 or charged + reserve > 100000:
                    raise StageBudgetExhausted("Preserve 32 calls and 200000 tokens for confirmation")
            return super().complete(messages, tools, tool_choice)
        except StageBudgetExhausted as exc:
            raise LLMServiceError("STAGE_BUDGET_EXHAUSTED", "Issue47 cumulative reservation limit reached") from exc


def records_for(variant):
    records = synthetic_records()
    if variant == "confirmation":
        for key, record in records.items():
            events = EventSet(tuple(replace(e, label={"stimulus": "tone", "control": "rest"}[e.label]) for e in record.events.events),
                              f"synthetic://issue47-{key}-events")
            records[key] = replace(record, events=events, data=record.data * 1.07,
                                   source=f"synthetic://issue47-confirmation-{key}")
    elif variant != "original":
        raise ValueError("Unknown synthetic variant")
    return records


def real_case(case, run_id):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,127}", run_id):
        raise ValueError("Run ID must be a new simple directory name")
    spec = json.loads(SPEC.read_text(encoding="utf8"))
    selected = spec[case]
    phase = "development" if case == "development" else "confirmation"
    directory = ROOT / run_id
    directory.mkdir(parents=True, exist_ok=False)
    raw = OpenAICompatibleClient.from_env()
    raw.max_retries, raw.timeout, raw.max_tokens = 0, min(raw.timeout, 45), 1200
    journal = JournaledBudgetClient(raw, directory / "responses.jsonl", max_requests=48, max_total_tokens=300000)
    client = Issue47Client(journal, LEDGER, phase=phase, model_label=raw.model)
    client.set_context(case=case, run_id=run_id, protocol_sha256=hashlib.sha256(SPEC.read_bytes()).hexdigest())
    agent = WorkingMemoryEEGAgent(client, records_for(selected["record_variant"]), session_id=run_id,
                                  memory_version="multi_result", timeout_seconds=600)
    for number, request in enumerate(selected["requests"], 1):
        client.set_context(turn=number)
        result = agent.run(request) if number == 1 else agent.continue_run(request)
        with (directory / f"turn-{number}.json").open("x", encoding="utf8") as f:
            json.dump(result.to_dict(), f, ensure_ascii=False, allow_nan=False, indent=2)
        audit = audit_entries(agent.working_memory.store)
        with (directory / f"audit-{number}.json").open("x", encoding="utf8") as f:
            json.dump(audit, f, ensure_ascii=False, allow_nan=False, indent=2)
        print(json.dumps({"case": case, "turn": number, "stop_reason": result.stop_reason, "rounds": result.rounds,
                          "tool_calls": result.tool_calls, "answer": result.final_answer,
                          "oracle_checks": len(audit), "oracle_pass": all(x["numerically_valid"] for x in audit),
                          "budget": ledger_totals(LEDGER)}, ensure_ascii=False), flush=True)
        if result.stop_reason in {"llm_error", "budget_exhausted"}:
            break
    return agent


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--real", action="store_true", required=True)
    p.add_argument("--case", choices=("development", "mixed", "short", "clarification"), required=True)
    p.add_argument("--run-id", help="New directory, never overwrite a previous run")
    args = p.parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    real_case(args.case, args.run_id or f"{args.case}-{stamp}")


if __name__ == "__main__":
    main()
