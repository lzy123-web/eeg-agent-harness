"""Fair shared-parsed planning comparison for the frozen evidence phase."""

import json
from pathlib import Path

from ...context import ExecutionContext
from ...executor import Executor
from ...pipeline import load_config
from ...planning import ConstrainedPlanRunner, StateAwareConstrainedPlanner
from ...profiles import EDF_NATIVE
from ...record import EEGRecord
from ...tools import build_default_registry
from ..integrated_method.contracts import (
    close_ledger, compile_intent, validate_plan_against_ledger,
)
from ..integrated_method.intent import IntentSpec
from .protocol import load_protocol
from .synthetic import build_quality_selection_record


def _record_for_fixture(name):
    anomalies = {"one_bad": (1,), "all_bad": (0, 1, 2), "clean": ()}.get(name, (1,))
    record, _ = build_quality_selection_record(anomalies)
    if name == "no_events":
        return EEGRecord(
            record.data.copy(), record.sfreq, record.channel_names,
            record.reference, record.montage, record.source,
            record.processing_metadata, dict(record.metadata), None,
        )
    return record


def _context(case, method):
    return ExecutionContext(
        _record_for_fixture(case["fixture"]), EDF_NATIVE,
        Executor(build_default_registry(), load_config("config/baseline.json")),
        f"{case['case_id']}:{method}",
    )


def _intent(payload):
    return IntentSpec(
        analysis_type=payload["analysis_type"],
        objectives=tuple(payload.get("objectives", ())),
        parameters=dict(payload.get("parameters", {})),
        explicit_evidence={}, semantic_evidence={}, unknown_slots=(),
        forbidden_operations=tuple(payload.get("forbidden_operations", ())),
        source_stage=payload.get("source_stage", "current"),
        output_boundary="research_only", rationale="shared parsed task",
    )


def _execute(case, method):
    if case["shared_intent"] is None:
        return {
            "method": method, "planning_applicable": False,
            "status": "clarification_owned_by_e2e_layer", "tool_results": [],
            "plan": None, "evidence": None,
        }
    context = _context(case, method)
    task, ledger = compile_intent(_intent(case["shared_intent"]), context)
    plan = StateAwareConstrainedPlanner(context).plan(task)
    validator = (
        (lambda candidate: validate_plan_against_ledger(candidate, ledger))
        if method == "ccep" else None
    )
    execution = ConstrainedPlanRunner(
        context, max_replans=1, plan_validator=validator,
    ).execute_plan(task, plan)
    evidence = close_ledger(ledger, execution) if method == "ccep" else None
    return {
        "method": method, "planning_applicable": True,
        "status": execution.status, "plan": plan.to_dict(),
        "tool_results": list(execution.tool_results),
        "trace": execution.execution_trace,
        "planning_trace": list(execution.planning_trace),
        "replans": execution.replans,
        "evidence": evidence,
    }


def _score(case, run):
    oracle = case["oracle"]
    if not run["planning_applicable"]:
        return {
            "evaluable": False, "reason": "clarification belongs to end-to-end experiment",
            "correct": None, "scientific_completion": False,
        }
    results = run["tool_results"]
    successful = [item["tool_name"] for item in results if item["success"]]
    successful_unique = list(dict.fromkeys(successful))
    executed = [item["tool_name"] for item in results]
    violations = []
    for tool in oracle["required_tools"]:
        if tool not in executed:
            violations.append(f"required_tool_missing:{tool}")
    for tool in oracle["forbidden_tools"]:
        if tool in successful:
            violations.append(f"forbidden_tool_succeeded:{tool}")

    expected = oracle["disposition"]
    if expected == "complete" and run["status"] != "completed":
        violations.append(f"expected_completion_got:{run['status']}")
    if expected == "reject" and run["status"] != "rejected":
        violations.append(f"expected_rejection_got:{run['status']}")
    if expected == "execution_failure" and run["status"] != "execution_failed":
        violations.append(f"expected_execution_failure_got:{run['status']}")

    create_results = [
        item for item in results if item["success"] and item["tool_name"] == "create_epochs"
    ]
    select_results = [
        item for item in results if item["success"] and item["tool_name"] == "select_quality_epochs"
    ]
    failed_empty_selections = [
        item for item in results
        if not item["success"]
        and item["tool_name"] == "select_quality_epochs"
        and item.get("error", {}).get("message")
        == "No Epochs remain after the declared quality rules"
    ]
    power_results = [
        item for item in results if item["success"] and item["tool_name"] == "event_bandpower"
    ]
    input_count = (
        create_results[-1]["data"]["valid_epoch_count"] if create_results else None
    )
    if select_results:
        output_count = select_results[-1]["data"]["selection"]["output_epoch_count"]
    elif failed_empty_selections:
        # The executor intentionally does not create an empty derived artifact.
        # Its typed failure is nevertheless independent evidence that zero
        # epochs survived selection, rather than evidence that input persisted.
        output_count = 0
    else:
        output_count = input_count
    if "input_epochs" in oracle and input_count != oracle["input_epochs"]:
        violations.append(f"input_epoch_count:{input_count}")
    if "output_epochs" in oracle and output_count != oracle["output_epochs"]:
        violations.append(f"output_epoch_count:{output_count}")

    if power_results and oracle.get("bandpower_source"):
        expected_id = (
            select_results[-1]["data"]["artifact_id"]
            if oracle["bandpower_source"] == "selected" else create_results[-1]["data"]["artifact_id"]
        )
        if power_results[-1]["data"]["artifact_id"] != expected_id:
            violations.append("bandpower_artifact_lineage_mismatch")

    scientific_completion = expected == "complete" and not violations
    return {
        "evaluable": True, "correct": not violations,
        "scientific_completion": scientific_completion,
        "expected_disposition": expected,
        "successful_tools": successful_unique,
        "input_epoch_count": input_count, "output_epoch_count": output_count,
        "violations": violations,
    }


def run_shared_planning(protocol_path="config/point1_evidence_phase_v1.json"):
    protocol = load_protocol(protocol_path)
    rows = []
    for case in protocol["cases"]:
        methods = {}
        for method in protocol["planning_methods"]:
            run = _execute(case, method)
            methods[method] = {"run": run, "score": _score(case, run)}
        rows.append({
            "case_id": case["case_id"], "split": case["split"],
            "oracle_disposition": case["oracle"]["disposition"], "methods": methods,
        })
    summary = {}
    for method in protocol["planning_methods"]:
        scores = [row["methods"][method]["score"] for row in rows]
        evaluable = [item for item in scores if item["evaluable"]]
        expected_complete = [item for item in evaluable if item["expected_disposition"] == "complete"]
        summary[method] = {
            "evaluable_cases": len(evaluable),
            "planning_inapplicable_clarification_cases": len(scores) - len(evaluable),
            "correct_cases": sum(item["correct"] for item in evaluable),
            "scientific_completion_count": sum(item["scientific_completion"] for item in evaluable),
            "expected_completion_cases": len(expected_complete),
            "total_tool_calls": sum(
                len(row["methods"][method]["run"]["tool_results"]) for row in rows
            ),
            "total_replans": sum(
                row["methods"][method]["run"].get("replans", 0) for row in rows
            ),
        }
    payload = {
        "protocol_id": protocol["protocol_id"],
        "corpus_sha256": protocol["corpus_sha256"],
        "experiment_layer": "shared_gold_or_shared_parsed_task_planning",
        "gold_visible_to_runtime": False,
        "method_difference": (
            "Both methods use identical route/preflight, Executor, state and recovery. "
            "Only CCEP applies persistent ledger validation and evidence closure."
        ),
        "summary": summary, "cases": rows,
    }
    json.dumps(payload, ensure_ascii=False, allow_nan=False)
    return payload


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", default="config/point1_evidence_phase_v1.json")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    payload = run_shared_planning(args.protocol)
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Evidence-phase result written to {output}")


if __name__ == "__main__":
    main()
