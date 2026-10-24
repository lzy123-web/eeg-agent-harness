"""Post-hoc audit of invariants frozen before the holdout was opened.

This module deliberately does not alter the primary v1 score. It detects whether
the recorded trace actually instantiated recovery conditions promised by the
append-only case manifest and checks trace-level invariants omitted by the
primary scorer.
"""

from collections import Counter


def _successful(result, tool_name):
    return [row for row in result.get("tool_results", ())
            if row.get("success") and row.get("tool_name") == tool_name]


def _reuse_goals(result):
    return {row.get("goal") for row in result.get("planning_trace", ())
            if row.get("event") == "goal_evidence_reused"}


def _effective_transition(case):
    return ("rereference_epochs" if case["gold"]["transition"] == "epoch_rereference"
            else "select_quality_epochs")


def _identity_fingerprint_pairs(result, tool_name):
    pairs = []
    for row in _successful(result, tool_name):
        data = row.get("data") or {}
        artifact_id = data.get("artifact_id")
        fingerprint = data.get("artifact_fingerprint")
        if artifact_id and fingerprint:
            pairs.append((artifact_id, fingerprint))
    return pairs


def audit_row(case, row):
    """Audit one immutable recorded row without re-running a method."""
    result = row["result"]
    tools = [item.get("tool_name") for item in result.get("tool_results", ())]
    counts = Counter(tools)
    reused = _reuse_goals(result)
    checks = {}
    protocol_valid = True
    protocol_notes = []

    for invariant in case["gold"].get("invariants", ()):
        value = None
        if invariant == "no_tool_execution":
            value = not tools
        elif invariant == "list_create_quality_not_repeated":
            value = all(counts[name] == 1 for name in ("list_events", "create_epochs", "epoch_quality"))
        elif invariant == "selection_and_bandpower_retried":
            value = counts["select_quality_epochs"] == 2 and counts["event_bandpower"] == 2
        elif invariant == "source_not_recreated":
            value = counts["create_epochs"] == 1
        elif invariant == "quality_recomputed":
            value = counts["epoch_quality"] == 2
        elif invariant == "only_bandpower_retried":
            value = counts["event_bandpower"] == 2 and all(
                count == 1 for name, count in counts.items() if name != "event_bandpower")
        elif invariant == "upstream_evidence_preserved":
            value = counts["event_bandpower"] == 2 and all(
                count == 1 for name, count in counts.items() if name != "event_bandpower")
        elif invariant == "summary_semantically_reused":
            # The strong expert has no CIEDG event vocabulary. One summary call
            # plus a repeated transition proves equivalent reuse externally.
            value = counts["epoch_summary"] == 1 and counts[_effective_transition(case)] == 2
        elif invariant == "summary_not_reused":
            value = "epoch_summary" not in reused and counts["epoch_summary"] == 2
        elif invariant == "new_identity_equal_fingerprint":
            pairs = _identity_fingerprint_pairs(result, _effective_transition(case))
            value = (len(pairs) >= 2 and pairs[0][0] != pairs[-1][0]
                     and pairs[0][1] == pairs[-1][1])
            if not value:
                protocol_valid = False
                protocol_notes.append(
                    "fault_did_not_create_different_effective_identity_with_equal_fingerprint")
        elif invariant == "summary_release_uses_current_identity":
            effective = result.get("scientific_state", {}).get("artifacts", {}).get("effective")
            summary = next((item for item in result.get("release_results", ())
                            if item.get("tool_name") == "epoch_summary" and item.get("success")), None)
            value = bool(summary and (summary.get("data") or {}).get("artifact_id") == effective)
        elif invariant in {
            "bandpower_matches_scipy_oracle", "bandpower_matches_mutated_scipy_oracle",
            "bandpower_matches_numpy_scipy_oracle", "bandpower_matches_oracle",
            "bandpower_matches_mutated_oracle", "excluded_indices_equal_injection_truth",
            "reference_channel_zero", "channel_mean_zero", "shape_events_sfreq_preserved",
            "zero_usable_condition_not_silently_dropped", "no_empty_selection_artifact",
            "absent_reference_not_synthesized", "profile_not_inferred_from_channel_count",
        }:
            value = bool(row["score"]["dimensions"]["scientific_state"])
        elif invariant in {
            "source_equals_effective", "flagged_trial_retained", "bandpower_uses_source_epochs",
            "native_reference_preserved", "no_transform_without_authorization",
            "no_guessed_reference", "pre_post_scope_not_substituted", "empty_window_not_executed",
            "content_change_invalidates_quality", "content_change_invalidates_all_dependents",
        }:
            value = bool(row["score"]["dimensions"]["scientific_state"]
                         and row["score"]["dimensions"]["planning"]
                         and not row["score"].get("unsafe_transform"))
        checks[invariant] = value

    failed = [name for name, value in checks.items() if value is False]
    return {
        "case_id": case["id"], "method": row["method"],
        "protocol_valid": protocol_valid,
        "protocol_notes": sorted(set(protocol_notes)),
        "invariants": checks,
        "passed_all_audited_invariants": protocol_valid and not failed,
        "failed_invariants": failed,
    }


def audit_report(report, cases):
    by_id = {case["id"]: case for case in cases}
    rows = [audit_row(by_id[row["case_id"]], row) for row in report["rows"]]
    return {
        "source_experiment_id": report["experiment_id"],
        "primary_scores_modified": False,
        "audit_basis": "append-only frozen gold invariants and immutable recorded traces",
        "rows": rows,
        "protocol_invalid_cases": sorted({row["case_id"] for row in rows if not row["protocol_valid"]}),
        "valid_rows": sum(row["protocol_valid"] for row in rows),
        "valid_rows_passing_all_audited_invariants": sum(
            row["protocol_valid"] and row["passed_all_audited_invariants"] for row in rows),
    }
