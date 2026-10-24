"""Bounded real-LLM comparison on the predeclared evidence-phase holdout pair."""

import json
from pathlib import Path

from ...agent import EEGAgent
from ...context import ExecutionContext
from ...executor import Executor
from ...llm import OpenAICompatibleClient
from ...pipeline import load_config
from ...profiles import EDF_NATIVE
from ...tools import build_default_registry
from ..integrated_method.agent import ConstraintCarryingEEGAgent
from .evaluation import _record_for_fixture, _score
from .protocol import load_protocol


REAL_HOLDOUT_CASE_IDS = (
    "hold-q-power-no-select-en",
    "hold-q-select-power-en",
)


def _context(case, method):
    return ExecutionContext(
        _record_for_fixture(case["fixture"]),
        EDF_NATIVE,
        Executor(build_default_registry(), load_config("config/baseline.json")),
        f"real:{case['case_id']}:{method}",
    )


def _client():
    return OpenAICompatibleClient.from_env()


def _normalise_for_score(method, result):
    if method == "native":
        status = "completed" if result["stop_reason"] == "completed" else result["stop_reason"]
        return {
            "planning_applicable": True,
            "status": status,
            "tool_results": list(result["tool_results"]),
        }
    execution = result.get("execution") or {}
    return {
        "planning_applicable": True,
        "status": execution.get("status", result["stop_reason"]),
        "tool_results": list(execution.get("tool_results", ())),
    }


def run_real_holdout(client_factory=_client, protocol_path="config/point1_evidence_phase_v1.json"):
    """Run native and CCEP from identical natural language and synthetic data.

    The case gold is passed only to the offline scorer after each Agent has
    returned.  Each run receives a fresh context and provider client.
    """

    protocol = load_protocol(protocol_path)
    by_id = {case["case_id"]: case for case in protocol["cases"]}
    rows = []
    total_requests = 0
    total_tokens = 0
    for case_id in REAL_HOLDOUT_CASE_IDS:
        case = by_id[case_id]
        methods = {}
        for method in ("native", "ccep"):
            client = client_factory()
            context = _context(case, method)
            agent = (
                EEGAgent(client, context, max_rounds=8, max_tool_calls=8)
                if method == "native"
                else ConstraintCarryingEEGAgent(client, context, max_replans=1)
            )
            result = agent.run(case["request"]).to_dict()
            score = _score(case, _normalise_for_score(method, result))
            usage = result.get("llm", {}).get("usage", {})
            total_requests += int(result.get("llm", {}).get("request_count") or 0)
            total_tokens += int(usage.get("total_tokens") or 0)
            methods[method] = {"result": result, "offline_score": score}
        rows.append({
            "case_id": case_id,
            "split": case["split"],
            "request": case["request"],
            "fixture": case["fixture"],
            "oracle_disposition": case["oracle"]["disposition"],
            "methods": methods,
        })
    return {
        "protocol_id": protocol["protocol_id"],
        "corpus_sha256": protocol["corpus_sha256"],
        "evaluation": "bounded_real_deepseek_holdout_pair",
        "case_ids_predeclared_in_code": list(REAL_HOLDOUT_CASE_IDS),
        "gold_visible_to_runtime": False,
        "external_data": "deterministic synthetic EEG only",
        "provider_budget": protocol["provider_budget"],
        "actual_usage": {
            "provider_requests": total_requests,
            "total_tokens": total_tokens,
        },
        "cases": rows,
    }


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    payload = run_real_holdout()
    if payload["actual_usage"]["provider_requests"] > payload["provider_budget"]["max_requests"]:
        raise RuntimeError("Provider request budget exceeded")
    if payload["actual_usage"]["total_tokens"] > payload["provider_budget"]["max_tokens"]:
        raise RuntimeError("Provider token budget exceeded")
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(f"Real evidence-phase result written to {output}")


if __name__ == "__main__":
    main()
