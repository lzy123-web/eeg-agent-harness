"""Offline R3 application bridge to the frozen CIEDG execution core."""

from dataclasses import asdict
import json
import math
from pathlib import Path

from ...context import ExecutionContext
from ...executor import Executor
from ...planning import StateAwareConstrainedPlanner
from ...research.integrated_method.contracts import (
    compile_intent, validate_plan_against_ledger,
)
from ...research.integrated_method.intent import IntentSpec
from ...research.integrated_method.v11 import ContractGraphResidualPlanner
from ...tools import build_default_registry
from .adapter import R3DatasetRules, R3_PROFILE, load_r3_edf


TASK_OBJECTIVES = {
    "event_summary": ("epoch_summary",),
    "quality_bandpower": ("epoch_quality", "event_bandpower"),
}


def load_application_config(path):
    """Load explicit application hypotheses without assigning event meanings."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    labels = tuple(payload["analysis_labels"])
    boundary = tuple(payload["boundary_labels"])
    if not labels or any(not isinstance(value, str) or not value for value in labels):
        raise ValueError("analysis_labels must be non-empty strings")
    if any(not isinstance(value, str) or not value for value in boundary):
        raise ValueError("boundary_labels must be non-empty strings")
    if len(set(labels)) != len(labels) or set(labels) & set(boundary):
        raise ValueError("analysis_labels must be unique and disjoint from boundary_labels")
    if len(payload["epoch_window"]) != 2 or len(payload["baseline"]) != 2:
        raise ValueError("epoch_window and baseline must each contain two bounds")
    tmin, tmax = (float(value) for value in payload["epoch_window"])
    bmin, bmax = (float(value) for value in payload["baseline"])
    if not all(math.isfinite(value) for value in (tmin, tmax, bmin, bmax)):
        raise ValueError("Epoch and baseline bounds must be finite")
    if not tmin < tmax or not tmin <= bmin < bmax <= tmax:
        raise ValueError("Baseline must be a non-empty interval inside the Epoch window")
    tasks = tuple(payload["tasks"])
    if not tasks or len(tasks) != len(set(tasks)) or any(
        not isinstance(name, str) or not name for name in tasks
    ):
        raise ValueError("tasks must contain unique non-empty names")
    rules = R3DatasetRules(
        analysis_labels=labels,
        boundary_labels=boundary,
        boundary_rule_status=str(payload["boundary_rule_status"]),
        epoch_window=(tmin, tmax),
        baseline=(bmin, bmax),
    )
    return rules, tasks


def run_r3_ciedg_record(record, config, rules, tasks=("event_summary", "quality_bandpower")):
    """Run configured parsed tasks through the unmodified CIEDG graph and Executor.

    Returns JSON-safe local results and contexts for independent in-process checks.
    No external LLM or network client is instantiated.
    """

    outputs, contexts = {}, {}
    for task_name in tasks:
        objectives = TASK_OBJECTIVES.get(task_name)
        if objectives is None:
            outputs[task_name] = {
                "status": "unsupported",
                "error": {"code": "UNSUPPORTED_R3_CIEDG_TASK", "message": "Task is not supported by the frozen application contract"},
                "execution": None,
            }
            continue
        context = ExecutionContext(
            record, R3_PROFILE, Executor(build_default_registry(), config),
            task_id=f"r3-ciedg-{task_name}",
        )
        contexts[task_name] = context
        parameters = {
            "labels": list(rules.analysis_labels),
            "tmin": rules.epoch_window[0],
            "tmax": rules.epoch_window[1],
            "baseline": list(rules.baseline),
        }
        intent = IntentSpec(
            "event_workflow", objectives, parameters,
            forbidden_operations=("selection", "rereference"),
            rationale="explicit local application configuration; no inferred event meaning",
        )
        task, ledger = compile_intent(intent, context)
        plan = StateAwareConstrainedPlanner(context).plan(task)
        check = validate_plan_against_ledger(plan, ledger)
        execution = ContractGraphResidualPlanner(
            context, task, ledger, max_retries=1, max_repairs=2, max_tool_calls=16,
        ).run(plan, check).to_dict()
        outputs[task_name] = {
            "status": execution["status"],
            "task": task.to_dict(),
            "ledger": ledger.to_dict(),
            "preflight": check,
            "execution": execution,
        }
    json.dumps(outputs, ensure_ascii=False, allow_nan=False)
    return outputs, contexts


def run_r3_ciedg_edf(edf_path, config, rules, tasks=("event_summary", "quality_bandpower")):
    record = load_r3_edf(edf_path)
    outputs, contexts = run_r3_ciedg_record(record, config, rules, tasks)
    return record, outputs, contexts


def application_config_snapshot(rules, tasks):
    return {"rules": asdict(rules), "tasks": list(tasks), "selection_performed": False}
