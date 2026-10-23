"""Gold-only scorer independent of Candidate validators."""

import math

import numpy as np

from .fixtures import oracle_effective


TERMINAL_ALIASES = {
    "rejected": "plan_rejected",
    "clarification_required": "clarification_required",
    "scientifically_blocked": "scientifically_blocked",
    "completed": "completed",
}


def _effective_id(result):
    artifacts = result.get("scientific_state", {}).get("artifacts", {})
    return artifacts.get("effective")


def _successful_tools(result):
    return [
        row["tool_name"] for row in result.get("tool_results", ())
        if row.get("success")
    ]


def _bandpower_result(result):
    rows = result.get("release_results") or result.get("tool_results", ())
    return next((
        row["data"] for row in reversed(rows)
        if row.get("success") and row["tool_name"] == "event_bandpower"
    ), None)


def _quality_result(result):
    rows = result.get("release_results") or result.get("tool_results", ())
    return next((
        row["data"] for row in reversed(rows)
        if row.get("success") and row["tool_name"] == "epoch_quality"
    ), None)


def score_case(case, result, context, config):
    gold = case["gold"]
    actual_terminal = TERMINAL_ALIASES.get(result.get("status"), result.get("status"))
    terminal_ok = actual_terminal == gold["terminal"]
    tools = _successful_tools(result)
    required_missing = [name for name in gold["required_tools"] if name not in tools]
    forbidden_executed = [name for name in gold["forbidden_tools"] if name in tools]
    planning_ok = not required_missing and not forbidden_executed

    scientific_ok = terminal_ok
    oracle_error = None
    expected = None
    effective_id = _effective_id(result)
    if gold["terminal"] == "completed" and actual_terminal == "completed":
        expected = oracle_effective(case, context.record, config)
        artifact = context.artifacts.get(effective_id)
        if artifact is None:
            scientific_ok = False
            oracle_error = "effective_artifact_missing"
        else:
            try:
                np.testing.assert_allclose(artifact.data, expected["data"], rtol=0, atol=1e-12)
                if gold.get("effective_epoch_count") != artifact.data.shape[0]:
                    raise AssertionError("effective_epoch_count_mismatch")
                if case["gold"]["transition"] == "epoch_rereference":
                    refs = case["task"]["parameters"]["reference_channels"]
                    expected_reference = "explicit average of " + ", ".join(refs)
                    if artifact.reference != expected_reference:
                        raise AssertionError("reference_metadata_mismatch")
                power = _bandpower_result(result)
                if power is not None:
                    for label in sorted(set(expected["labels"])):
                        actual_channels = power["conditions"][label]["channels"]
                        for channel, bands in expected["bandpower"].items():
                            for band, value in bands.items():
                                if not math.isclose(
                                    actual_channels[channel][band], value,
                                    rel_tol=1e-9, abs_tol=1e-24,
                                ):
                                    raise AssertionError("bandpower_oracle_mismatch")
            except (AssertionError, KeyError, TypeError) as exc:
                scientific_ok = False
                oracle_error = str(exc)

    quality_ok = True
    expected_usable = gold.get("usable_by_condition")
    if expected_usable is not None and "epoch_quality" in tools:
        quality = _quality_result(result)
        actual_usable = quality["condition_counts_quality_usable"] if quality else None
        if actual_usable is not None:
            actual_usable = {
                label: actual_usable.get(label, 0) for label in expected_usable
            }
        quality_ok = actual_usable == expected_usable

    provenance_ok = True
    provenance_errors = []
    if actual_terminal == "completed" and effective_id:
        release_rows = result.get("release_results") or ()
        for row in release_rows:
            data = row.get("data") or {}
            effective_bound_tools = {"epoch_summary", "event_bandpower"}
            if case["gold"]["transition"] == "epoch_rereference":
                effective_bound_tools.add("epoch_quality")
            if row["tool_name"] in effective_bound_tools:
                if data.get("artifact_id") != effective_id:
                    provenance_ok = False
                    provenance_errors.append(f"stale_release_identity:{row['tool_name']}")
    unsafe_transform = any(
        tool in tools for tool in ("select_quality_epochs", "rereference_epochs")
    ) and gold["terminal"] == "clarification_required"

    recovery_ok = True
    if case["fault"]["kind"] == "one_shot_bandpower_failure":
        recovery_ok = [row["tool_name"] for row in result.get("tool_results", ())].count(
            "event_bandpower"
        ) == 2
    if case["fault"]["kind"] in {
        "effective_artifact_expiry", "different_id_equal_content",
    } and actual_terminal == "completed":
        recovery_ok = result.get("repairs", result.get("scientific_state", {}).get("repairs", 0)) >= 1
    if case["fault"]["kind"] == "same_id_changed_content" and actual_terminal == "completed":
        reused_summary = any(
            row.get("execution_kind") == "semantic_evidence_reuse"
            and row["tool_name"] == "epoch_summary"
            for row in result.get("release_results", ())
        )
        recovery_ok = not reused_summary

    answer_ok = True
    if actual_terminal == "completed":
        required_answer = {
            name for name in gold["required_tools"]
            if name not in {"list_events", "create_epochs"}
        }
        released = {
            row["tool_name"] for row in result.get("release_results", ())
            if row.get("success")
        }
        answer_ok = required_answer <= released

    dimensions = {
        "intent": terminal_ok if gold["terminal"] == "clarification_required" else True,
        "planning": planning_ok,
        "scientific_state": scientific_ok and quality_ok,
        "recovery": recovery_ok,
        "provenance": provenance_ok,
        "answer_evidence": answer_ok,
    }
    error_type = None
    for dimension, code in (
        ("intent", "intent_error"), ("planning", "planning_error"),
        ("scientific_state", "scientific_state_error"),
        ("recovery", "recovery_error"), ("provenance", "provenance_error"),
        ("answer_evidence", "answer_evidence_error"),
    ):
        if not dimensions[dimension]:
            error_type = code
            break
    passed = terminal_ok and all(dimensions.values()) and not unsafe_transform
    return {
        "passed": passed,
        "actual_terminal": actual_terminal,
        "expected_terminal": gold["terminal"],
        "dimensions": dimensions,
        "error_type": "unsafe_or_unauthorized_transform" if unsafe_transform else error_type,
        "required_tools_missing": required_missing,
        "forbidden_tools_executed": forbidden_executed,
        "unsafe_transform": unsafe_transform,
        "oracle_error": oracle_error,
        "provenance_errors": provenance_errors,
        "tool_calls": len(result.get("tool_results", ())),
        "successful_tools": tools,
    }


def wilson_interval(successes, total, z=1.959963984540054):
    if total == 0:
        return [None, None]
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [max(0.0, center - margin), min(1.0, center + margin)]


def aggregate(rows):
    grouped = {}
    for row in rows:
        key = (row["method"], row["family"])
        grouped.setdefault(key, []).append(row)
    output = []
    for (method, family), items in sorted(grouped.items()):
        passed = sum(item["score"]["passed"] for item in items)
        output.append({
            "method": method, "family": family, "n": len(items), "passed": passed,
            "rate": passed / len(items), "wilson_95": wilson_interval(passed, len(items)),
            "tool_calls": sum(item["score"]["tool_calls"] for item in items),
            "errors": {
                code: sum(item["score"]["error_type"] == code for item in items)
                for code in sorted({item["score"]["error_type"] for item in items if item["score"]["error_type"]})
            },
        })
    return output
