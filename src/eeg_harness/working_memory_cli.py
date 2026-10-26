"""Unified natural-language opt-in entry, synthetic-only for external LLM use."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from .llm import OpenAICompatibleClient, LLMServiceError
from .working_memory_agent import WorkingMemoryEEGAgent
from .research.task_memory import PROJECT_ROOT, synthetic_records
from .research.integrated_method.v2_validation import JournaledBudgetClient
from .research.task_memory_issue39_budget import Issue39BudgetClient, StageBudgetExhausted, ledger_totals, _rows


PRIVATE = PROJECT_ROOT / "artifacts" / "point1_task_memory" / "issue45"
LEDGER = PRIVATE / "budget.jsonl"


class ReservedPhaseClient(Issue39BudgetClient):
    """Protect confirmation reserve before any development network attempt.

    Shares the original append-only stage ledger. No earlier attempts are reset.
    """
    def complete(self, messages, tools, tool_choice="auto"):
        try:
            return self._complete_guarded(messages, tools, tool_choice)
        except StageBudgetExhausted as exc:
            raise LLMServiceError("STAGE_BUDGET_EXHAUSTED", "Stage allocation cannot safely reserve another request.") from exc

    def _complete_guarded(self, messages, tools, tool_choice):
        if self.context.get("phase") == "development":
            rows = _rows(self.ledger)
            starts = {r["request_id"]: r for r in rows if r["event"] == "reserved" and
                      r.get("context", {}).get("phase") == "development"}
            ends = {r["request_id"]: r for r in rows if r["event"] in {"received", "failed"}}
            spent = sum((ends.get(k, {}).get("total_tokens") or v["reserved_tokens"])
                        for k, v in starts.items())
            reserve = len(json.dumps({"messages": messages, "tools": tools,
                                      "tool_choice": tool_choice}, ensure_ascii=False).encode("utf-8")) + self.client.client.max_tokens
            if spent + reserve > 140000:
                raise StageBudgetExhausted("Development allocation exhausted; preserve confirmation budget")
        return super().complete(messages, tools, tool_choice)


def budgeted_client(phase, *, phase_cap=40):
    raw = OpenAICompatibleClient.from_env()
    raw.max_retries = 0  # Every external attempt must pass the persistent ledger.
    raw.timeout = min(raw.timeout, 45)
    raw.max_tokens = min(raw.max_tokens, 1200)
    private = PRIVATE / phase
    private.mkdir(parents=True, exist_ok=True)
    journal = JournaledBudgetClient(raw, private / "responses.jsonl",
                                    max_requests=96, max_total_tokens=240000)
    return ReservedPhaseClient(journal, LEDGER, max_requests=96, max_tokens=240000,
                                model_label=raw.model, phase=phase, phase_request_cap=phase_cap)


def run_requests(requests, client, *, records=None, session_id="interactive", context_mode="working"):
    """Only ordinary requests and loaded records enter the method. No turn kinds."""
    agent = WorkingMemoryEEGAgent(client, records or synthetic_records(),
                                  session_id=session_id, context_mode=context_mode)
    results = []
    directory = PRIVATE / session_id
    directory.mkdir(parents=True, exist_ok=True)
    for number, request in enumerate(requests, 1):
        result = agent.run(request) if number == 1 else agent.continue_run(request)
        value = result.to_dict()
        results.append(value)
        # Persist immediately, including partial failure; never overwrite old runs.
        path = directory / f"turn-{number}.json"
        with path.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        print(json.dumps({"turn": number, "stop_reason": result.stop_reason,
                          "rounds": result.rounds, "answer": result.final_answer}, ensure_ascii=False), flush=True)
        if result.stop_reason in {"llm_error", "budget_exhausted", "no_progress", "context_capacity", "evidence_capacity"}:
            break
    return agent, results


def main(argv=None):
    parser = argparse.ArgumentParser(description="Experimental EEG working memory; real LLM, synthetic records only")
    parser.add_argument("--request", action="append", required=True, help="Natural-language request; repeat for continuation")
    parser.add_argument("--real", action="store_true", required=True)
    parser.add_argument("--context-mode", choices=("working", "full"), default="working")
    args = parser.parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    client = budgeted_client("interactive", phase_cap=16)
    run_requests(args.request, client, session_id=f"interactive-{stamp}", context_mode=args.context_mode)
    print(json.dumps(ledger_totals(LEDGER)))


if __name__ == "__main__":
    main()
