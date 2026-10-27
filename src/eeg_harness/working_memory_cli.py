"""Unified natural-language opt-in entry, synthetic-only for external LLM use."""

import argparse
from datetime import datetime, timezone
import json
import re
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


def new_stage_client(config_path):
    """Explicit future authorization manifest; never reopens Issue45's quota.

    The file records a human-authorized budget; creating it is not authorization.
    Disabled/missing limits fail before credentials or network are accessed.
    """
    config = json.loads(Path(config_path).read_text(encoding="utf-8-sig"))
    stage = config.get("stage", "")
    if (config.get("enabled") is not True or not re.fullmatch(r"[a-z][a-z0-9-]{2,63}", stage)
            or stage.startswith("issue") or any(type(config.get(k)) is not int or config[k] <= 0
                                               for k in ("max_requests", "max_tokens"))):
        raise ValueError("A new explicitly authorized stage and positive cumulative limits are required")
    raw = OpenAICompatibleClient.from_env()
    raw.max_retries, raw.timeout, raw.max_tokens = 0, min(raw.timeout, 45), min(raw.max_tokens, 1200)
    directory = PROJECT_ROOT / "artifacts" / "working_memory_stages" / stage
    directory.mkdir(parents=True, exist_ok=True)
    journal = JournaledBudgetClient(raw, directory / "responses.jsonl",
                                   max_requests=config["max_requests"], max_total_tokens=config["max_tokens"])
    client = ReservedPhaseClient(journal, directory / "budget.jsonl", max_requests=config["max_requests"],
                                 max_tokens=config["max_tokens"], model_label=raw.model, phase="confirmation")
    return client, directory


def run_requests(requests, client, *, records=None, session_id="interactive", context_mode="working",
                 memory_version="single", output_root=None, request_closure=False, plan_arm=None):
    """Only ordinary requests and loaded records enter the method. No turn kinds."""
    if plan_arm is not None:
        from .task_plan_agent import TaskPlanEEGAgent
        agent = TaskPlanEEGAgent(client, records or synthetic_records(), session_id=session_id, arm=plan_arm)
    else:
        agent = WorkingMemoryEEGAgent(client, records or synthetic_records(),
                                      session_id=session_id, context_mode=context_mode, memory_version=memory_version,
                                      request_closure=request_closure)
    results = []
    directory = (Path(output_root) if output_root is not None else PRIVATE) / session_id
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
    parser.add_argument("--context-mode", choices=("working", "full", "summary"), default="working")
    parser.add_argument("--memory-version", choices=("single", "multi_result", "lifecycle", "managed", "scientific"), default="single")
    parser.add_argument("--request-closure", action="store_true", help="Use common request progress and evidence-grounded final delivery with lifecycle")
    parser.add_argument("--plan-arm", choices=("A","B","C","C-no-delivery","C-no-selection","A-equivalent"),
                        help="Opt-in shared Plan-and-Execute comparison. Real calls still require a separately authorized new budget; Issue52 grants none.")
    parser.add_argument("--budget-config", type=Path, required=True,
                        help="Private JSON for a separately authorized stage; no default quota")
    args = parser.parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    client, directory = new_stage_client(args.budget_config)
    run_requests(args.request, client, session_id=f"interactive-{stamp}", context_mode=args.context_mode,
                 memory_version=args.memory_version, output_root=directory, request_closure=args.request_closure,
                 plan_arm=args.plan_arm)
    print(json.dumps(ledger_totals(client.ledger)))


if __name__ == "__main__":
    main()
