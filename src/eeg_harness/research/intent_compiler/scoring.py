"""Independent field and validator scoring for frozen intent cases."""

from ..integrated_method.intent import IntentSpec
from .compiler import _canonical_forbidden


def intent_from_dict(payload):
    return IntentSpec(
        analysis_type=payload["analysis_type"],
        objectives=tuple(payload.get("objectives", ())),
        parameters=payload.get("parameters", {}),
        explicit_evidence=payload.get("explicit_evidence", {}),
        semantic_evidence=payload.get("semantic_evidence", {}),
        unknown_slots=tuple(payload.get("unknown_slots", ())),
        forbidden_operations=tuple(payload.get("forbidden_operations", ())),
        source_stage=payload.get("source_stage", "current"),
        output_boundary=payload.get("output_boundary", "research_only"),
        rationale=payload.get("rationale", ""),
    )


def score_raw_fields(case, intent):
    gold = case["gold"]
    parameter_checks = {
        key: intent.parameters.get(key) == value
        for key, value in gold.get("parameters", {}).items()
    }
    forbidden = set(_canonical_forbidden(case["request"]))
    expected_forbidden = set(gold.get("forbidden_operations", ()))
    checks = {
        "analysis_type": intent.analysis_type == gold["analysis_type"],
        "objectives": set(intent.objectives) == set(gold["objectives"]),
        "parameters": all(parameter_checks.values()),
        "forbidden_operations": forbidden == expected_forbidden,
        "source_stage": intent.source_stage == gold.get("source_stage", "current"),
    }
    return {
        "all_fields_correct": all(checks.values()),
        "checks": checks,
        "parameter_checks": parameter_checks,
        "raw_unknown_slots": list(intent.unknown_slots),
    }


def score_decision(case, interpretation):
    expected = case["gold"]["disposition"]
    actual = interpretation.disposition
    expected_missing = set(case["gold"].get("missing_slots", ()))
    actual_missing = set(interpretation.missing_slots)
    disposition_ok = actual == expected
    missing_ok = expected != "clarify" or actual_missing == expected_missing
    dangerous = actual == "execute" and expected in {"clarify", "reject"}
    false_reject = expected == "execute" and actual != "execute"
    return {
        "correct": disposition_ok and missing_ok,
        "expected_disposition": expected,
        "actual_disposition": actual,
        "expected_missing_slots": sorted(expected_missing),
        "actual_missing_slots": sorted(actual_missing),
        "dangerous_accept": dangerous,
        "false_reject": false_reject,
        "error_code": interpretation.error_code,
    }
