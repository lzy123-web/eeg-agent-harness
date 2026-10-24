"""Independent field and validator scoring for frozen intent cases."""

from ..integrated_method.intent import IntentSpec
from .compiler import _exact_span, _value_is_grounded


OBJECTIVE_CONCEPTS = {
    "epoch_quality": "quality_measurement",
    "trial_selection": "trial_selection",
    "epoch_summary": "epoch_summary",
    "event_bandpower": "spectral_power",
    "epoch_rereference": "epoch_rereference",
}

ANALYSIS_CONCEPTS = {
    "record_info": {"record_metadata"},
    "amplitude": {"time_domain_amplitude"},
    "psd": {"spectral_power"},
    "record_quality": {"quality_measurement"},
    "seizure_detection": {"seizure_detection"},
    "unsupported": set(),
}


def expected_semantic_concepts(gold):
    if gold["analysis_type"] != "event_workflow":
        return ANALYSIS_CONCEPTS[gold["analysis_type"]]
    return {"event_locked"} | {
        OBJECTIVE_CONCEPTS[objective] for objective in gold["objectives"]
    }


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
    expected_forbidden = set(gold.get("forbidden_operations", ()))
    expected_concepts = expected_semantic_concepts(gold)
    semantic_spans_exact = all(
        _exact_span(case["request"], quote)
        for quote in intent.semantic_evidence.values()
    )
    parameter_evidence_grounded = all(
        _exact_span(case["request"], intent.explicit_evidence.get(key))
        and _value_is_grounded(value, intent.explicit_evidence.get(key))
        for key, value in gold.get("parameters", {}).items()
    )
    checks = {
        "analysis_type": intent.analysis_type == gold["analysis_type"],
        "objectives": set(intent.objectives) == set(gold["objectives"]),
        "parameters": all(parameter_checks.values()),
        "forbidden_operations": set(intent.forbidden_operations) == expected_forbidden,
        "semantic_concepts": set(intent.semantic_evidence) == expected_concepts,
        "semantic_spans_exact": semantic_spans_exact,
        "parameter_evidence_grounded": parameter_evidence_grounded,
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
