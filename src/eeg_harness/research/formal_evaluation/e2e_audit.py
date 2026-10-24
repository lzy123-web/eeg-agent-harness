"""Append-only audit of already recorded real-LLM rows."""

from copy import deepcopy

from .e2e import _native_terminal, audit_answer


def audit_recorded_report(report):
    audited = []
    for original in report["rows"]:
        row = deepcopy(original)
        raw = row["result"]
        execution = raw.get("execution") or {}
        tool_results = raw.get("tool_results") or execution.get("tool_results") or []
        score = row["score"]
        if row["method"] == "native_agent":
            observed = _native_terminal(raw)
            if observed != score["actual_terminal"]:
                score["actual_terminal"] = observed
                terminal_ok = observed == score["expected_terminal"]
                score["dimensions"]["intent"] = (
                    terminal_ok if score["expected_terminal"] == "clarification_required" else True)
                if score["expected_terminal"] != "completed":
                    score["dimensions"]["scientific_state"] = terminal_ok
                score["error_type"] = next((code for dimension, code in (
                    ("intent", "intent_error"), ("planning", "planning_error"),
                    ("scientific_state", "scientific_state_error"),
                    ("recovery", "recovery_error"), ("provenance", "provenance_error"),
                    ("answer_evidence", "answer_evidence_error"),
                ) if not score["dimensions"][dimension]), None)
                score["passed"] = terminal_ok and all(score["dimensions"].values()) \
                    and not score.get("unsafe_transform", False)
        answer = audit_answer(raw.get("final_answer", ""), row["request"], tool_results)
        pipeline_answer_valid = not (
            row["method"] == "CIEDG" and raw.get("answer_check") is not None
            and not raw["answer_check"].get("valid", False))
        row["answer_audit"] = answer
        row["pipeline_answer_valid"] = pipeline_answer_valid
        row["accepted"] = score["passed"] and answer["valid"] and pipeline_answer_valid
        audited.append(row)
    return {
        "source_experiment_id": report["experiment_id"],
        "source_rows_immutable": True,
        "audit_reason": [
            "CIEDG pipeline answer_check must gate acceptance",
            "clarification may follow non-substantive state inspection",
            "identifiers and hashes are not numerical scientific claims",
            "unresolved tool failures must be disclosed",
        ],
        "rows": audited,
        "summary": {
            "rows": len(audited),
            "accepted": sum(row["accepted"] for row in audited),
            "by_method": {
                method: {
                    "n": sum(row["method"] == method for row in audited),
                    "accepted": sum(row["method"] == method and row["accepted"] for row in audited),
                }
                for method in sorted({row["method"] for row in audited})
            },
        },
    }
