"""Frozen Issue #8 benchmark with independent synthetic scientific oracles."""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from .models import ScientificRequirement
from .planner import CandidateEEGSemanticPlanner, ExpertConditionalDAG, GenericSemanticPlanner
from .runtime import SemanticRuntime
from .synthetic import build_scene


PLANNERS = {
    "expert_dag": ExpertConditionalDAG,
    "generic_semantic": GenericSemanticPlanner,
    "candidate_eeg_semantic": CandidateEEGSemanticPlanner,
}


def canonical_hash(payload):
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_suite(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _ancestor_payload(runtime, artifact):
    if not artifact.parent_ids:
        return None
    return runtime.context.artifacts.get(artifact.parent_ids[0])


def _oracle_completed(case, runtime, plan, truth):
    errors, alignment_errors = [], []
    requirements = [ScientificRequirement.from_dict(goal, index) for index, goal in enumerate(case["request"]["goals"])]
    if len(plan.output_artifact_ids) != len(requirements):
        errors.append("OUTPUT_COUNT_MISMATCH")
        return errors, alignment_errors
    for requirement, artifact_id in zip(requirements, plan.output_artifact_ids):
        payload = runtime.context.artifacts.get(artifact_id)
        if payload is None:
            errors.append("OUTPUT_ARTIFACT_MISSING")
            continue
        artifact = payload.semantic
        parent = _ancestor_payload(runtime, artifact)
        if requirement.kind == "line_noise":
            if parent is None or parent.semantic.stage != "raw":
                errors.append("LINE_NOISE_NOT_FROM_RAW")
            elif any(step.get("operation") in ("lowpass_filter", "notch_filter") for step in parent.value.processing_metadata):
                errors.append("LINE_NOISE_FROM_PROCESSED_SIGNAL")
            if artifact.get("frequency_hz") != requirement.parameters.get("frequency_hz", 50.0):
                errors.append("LINE_NOISE_FREQUENCY_CHANGED")
        elif requirement.kind == "bandpower":
            if parent is None:
                errors.append("BANDPOWER_SOURCE_MISSING")
            required = requirement.parameters.get("require_lowpass_hz")
            if required is not None and parent is not None:
                actual = [step.get("h_freq") for step in parent.value.processing_metadata if step.get("operation") == "lowpass_filter"]
                if not any(abs(float(value) - float(required)) < 1e-9 for value in actual):
                    errors.append("BANDPOWER_REQUIRED_BRANCH_MISSING")
        elif requirement.kind == "epochs":
            epochs = payload.value
            selected_labels = set(requirement.parameters["labels"])
            expected = [
                onset for label, onset in zip(truth["event_labels"], truth["event_onsets_seconds"])
                if label in selected_labels
            ]
            if len(expected) != len(epochs.event_onsets_seconds):
                errors.append("EPOCH_COUNT_MISMATCH")
            else:
                alignment_errors.extend(abs(float(actual) - float(source)) for actual, source in zip(epochs.event_onsets_seconds, expected))
        elif requirement.kind in ("condition_feature", "epoch_variance"):
            if parent is None or parent.semantic.kind != "epochs":
                errors.append("FEATURE_EPOCH_SOURCE_MISSING")
                continue
            if payload.value is None:
                errors.append("FEATURE_VALUE_MISSING")
            counts = dict(zip(*np.unique(parent.value.event_labels, return_counts=True)))
            minimum = int(requirement.parameters.get("min_trials_per_label", 1))
            if any(int(counts.get(label, 0)) < minimum for label in requirement.parameters.get("labels", ())):
                errors.append("FEATURE_INSUFFICIENT_TRIALS")
            selection = requirement.parameters.get("selection")
            if selection and not parent.semantic.selection_history:
                errors.append("FEATURE_USED_UNSELECTED_EPOCHS")
            if artifact.get("source_epoch_artifact_id") != parent.semantic.artifact_id:
                errors.append("FEATURE_LINEAGE_MISMATCH")
    if case["expected"].get("distinct_source_branches") and len(plan.output_artifact_ids) >= 2:
        parents = [runtime.context.artifacts[item].semantic.parent_ids[0] for item in plan.output_artifact_ids]
        if len(set(parents)) != len(parents):
            errors.append("DISTINCT_BRANCHES_COLLAPSED")
    maximum = case["expected"].get("max_alignment_error_seconds")
    if maximum is not None and alignment_errors and max(alignment_errors) > float(maximum) + 1e-12:
        errors.append("EVENT_ALIGNMENT_EXCEEDS_TOLERANCE")
    return errors, alignment_errors


def evaluate_case(case, planner_name, budgets):
    record, payloads, truth = build_scene(case["initial"])
    requirements = [
        ScientificRequirement.from_dict(goal, index)
        for index, goal in enumerate(case["request"]["goals"])
    ]
    planner = PLANNERS[planner_name](max_steps=budgets["max_tool_calls"])
    plan = planner.plan(requirements, [item.semantic for item in payloads])
    runtime = SemanticRuntime(record, payloads)
    results, oracle_errors, alignment_errors = [], [], []
    actual_status = "plan_rejected" if plan.status == "rejected" else plan.status
    if plan.status == "planned":
        results = runtime.execute_plan(plan)
        if not all(result.success for result in results):
            actual_status = "executor_rejected"
        else:
            oracle_errors, alignment_errors = _oracle_completed(case, runtime, plan, truth)
            actual_status = "completed_invalid" if oracle_errors else "completed_valid"
    expected_complete = case["expected"]["status"] == "completed"
    correct = actual_status == ("completed_valid" if expected_complete else "plan_rejected")
    if not expected_complete and actual_status == "plan_rejected":
        correct = plan.reason_code == case["expected"].get("reason")
    return {
        "case_id": case["id"], "split": case["split"], "scenario": case["scenario"],
        "planner": planner_name, "expected": case["expected"],
        "actual_status": actual_status, "reason_code": plan.reason_code,
        "correct": correct, "tool_calls": len(results), "planned_steps": len(plan.steps),
        "state_queries": plan.state_queries, "planning_duration_ms": plan.planning_duration_ms,
        "execution_duration_ms": round(sum(result.duration_ms for result in results), 3),
        "max_event_alignment_error_seconds": max(alignment_errors) if alignment_errors else None,
        "oracle_errors": oracle_errors,
        "tool_results": [result.to_dict() for result in results],
        "plan": plan.to_dict(),
    }


def _aggregate(rows):
    output = {}
    for planner in PLANNERS:
        selected = [row for row in rows if row["planner"] == planner]
        legal = [row for row in selected if row["expected"]["status"] == "completed"]
        reject = [row for row in selected if row["expected"]["status"] == "rejected"]
        holdout = [row for row in selected if row["split"] == "holdout"]
        alignments = [row["max_event_alignment_error_seconds"] for row in selected if row["max_event_alignment_error_seconds"] is not None]
        output[planner] = {
            "case_count": len(selected),
            "legal_completion_rate": sum(row["actual_status"] == "completed_valid" for row in legal) / len(legal),
            "correct_refusal_rate": sum(row["actual_status"] == "plan_rejected" and row["correct"] for row in reject) / len(reject),
            "false_rejection_count": sum(row["actual_status"] == "plan_rejected" for row in legal),
            "executed_semantically_invalid_count": sum(row["actual_status"] == "completed_invalid" for row in selected),
            "executor_rejection_count": sum(row["actual_status"] == "executor_rejected" for row in selected),
            "overall_correct_rate": sum(row["correct"] for row in selected) / len(selected),
            "holdout_correct_rate": sum(row["correct"] for row in holdout) / len(holdout),
            "tool_calls": sum(row["tool_calls"] for row in selected),
            "state_queries": sum(row["state_queries"] for row in selected),
            "mean_planning_duration_ms": sum(row["planning_duration_ms"] for row in selected) / len(selected),
            "max_event_alignment_error_seconds": max(alignments) if alignments else None,
        }
    return output


def run_evaluation(suite_path):
    suite = load_suite(suite_path)
    rows = [
        evaluate_case(case, planner, suite["budgets"])
        for planner in suite["methods"] for case in suite["cases"]
    ]
    return {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "suite_sha256": canonical_hash(suite),
        "suite_case_count": len(suite["cases"]),
        "budgets": suite["budgets"],
        "aggregate": _aggregate(rows),
        "extension_maintenance_observation": {
            "scope": "single-developer code-point count; weak evidence, not elapsed effort",
            "shared_contract_and_runtime_points": 2,
            "method_specific_points": {
                "expert_dag": 2,
                "generic_semantic": 0,
                "candidate_eeg_semantic": 1
            },
            "interpretation": "The generic planner consumed the new contract without planner changes; candidate added a ranking entry. This does not support H2 against the generic baseline."
        },
        "cases": rows,
    }
