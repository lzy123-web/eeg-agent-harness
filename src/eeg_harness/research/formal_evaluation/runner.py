"""Reproducible parsed-task experiment runner."""

from datetime import datetime, timezone
import json

from .candidate import run_ciedg
from .expert import run_strong_expert
from .faults import apply_fault
from .fixtures import build_fixture
from .protocol import FROZEN_CANDIDATE_SHA, load_cases
from .scoring import aggregate, score_case


ABLATIONS = (
    "without_dependency_invalidation",
    "without_semantic_evidence_reuse",
    "whole_plan_replay",
    "without_eeg_scientific_guards",
)


def _run_method(case, method, config_path):
    context, _, config = build_fixture(case, config_path)
    apply_fault(context, case)
    if method == "CIEDG":
        result = run_ciedg(case, context)
    elif method == "strong_dynamic_expert":
        result = run_strong_expert(case, context)
    elif method in ABLATIONS:
        result = run_ciedg(case, context, ablation=method)
    else:
        raise ValueError(f"Unknown formal evaluation method: {method}")
    score = score_case(case, result, context, config)
    return {
        "case_id": case["id"], "family": case["family"], "split": case["split"],
        "method": method, "fixture_seed": case["fixture"]["seed"],
        "fault": case["fault"], "score": score, "result": result,
    }


def run_suite(
    split, *, methods=("CIEDG", "strong_dynamic_expert"),
    cases_path="config/point1_formal_eval_cases_v1.json",
    config_path="config/baseline.json",
):
    protocol, digest = load_cases(cases_path)
    selected = [case for case in protocol["cases"] if case["split"] == split]
    rows = []
    for case in selected:
        for method in methods:
            rows.append(_run_method(case, method, config_path))
    report = {
        "experiment_id": f"ciedg-formal-parsed-task-{split}-v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "candidate_sha": FROZEN_CANDIDATE_SHA,
        "supplement_sha256": digest,
        "split": split,
        "methods": list(methods),
        "offline_gold_visible_to_runtime": False,
        "synthetic_only": True,
        "rows": rows,
        "aggregate": aggregate(rows),
    }
    json.dumps(report, ensure_ascii=False, allow_nan=False)
    return report
