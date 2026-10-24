"""Small, executable diagnostics for LRSP v1.1; not a formal benchmark."""

from statistics import median
import time

import numpy as np

from ...events import EpochSet
from ...tooling import ToolRequest


def run_guarded_epoch_expert(
    context, *, labels, tmin, tmax, objectives, selection_authorized=False,
    max_tool_calls=16,
):
    """Run a transparent procedural strong baseline with the same tools/guards.

    This intentionally contains the workflow branches that CIEDG declares as
    contracts. It is used only for small matched-information diagnostics.
    """

    results = []
    sequence = 0

    def execute(name, arguments):
        nonlocal sequence
        if sequence >= max_tool_calls:
            return None
        sequence += 1
        rendered = context.execute(ToolRequest(
            name, arguments, request_id=f"expert-{sequence}-{name}",
        )).to_dict()
        results.append(rendered)
        return rendered

    def fail(code, message):
        return {
            "status": "blocked", "reason": {"code": code, "message": message},
            "tool_results": results,
        }

    observed = execute("list_events", {})
    if not observed or not observed["success"]:
        return fail("ACTION_FAILED", "list_events failed")
    created = execute("create_epochs", {
        "labels": list(labels), "tmin": tmin, "tmax": tmax,
    })
    if not created or not created["success"]:
        return fail("ACTION_FAILED", "create_epochs failed")
    source = {
        "artifact_id": created["data"]["artifact_id"],
        "expected_artifact_fingerprint": created["data"]["artifact_fingerprint"],
    }
    effective = dict(source)
    quality = None
    if "epoch_quality" in objectives or "trial_selection" in objectives:
        quality = execute("epoch_quality", source)
        if not quality or not quality["success"]:
            return fail("ACTION_FAILED", "epoch_quality failed")
    if "trial_selection" in objectives:
        if not selection_authorized:
            return fail("SELECTION_NOT_AUTHORIZED", "explicit authorization is absent")
        usable = quality["data"]["condition_counts_quality_usable"]
        missing = [label for label in labels if usable.get(label, 0) < 1]
        if missing:
            output = fail(
                "NO_USABLE_EPOCHS_FOR_CONDITION",
                "at least one requested condition has no quality-usable Epoch",
            )
            output["reason"]["labels"] = missing
            return output
        if quality["data"]["epoch_counts"]["quality_flagged"]:
            selected = execute("select_quality_epochs", {
                **source,
                "expected_quality_evidence_id": quality["data"]["evidence_id"],
            })
            if not selected or not selected["success"]:
                return fail("ACTION_FAILED", "select_quality_epochs failed")
            effective = {
                "artifact_id": selected["data"]["artifact_id"],
                "expected_artifact_fingerprint": selected["data"]["artifact_fingerprint"],
            }
    for goal, tool_name in (
        ("epoch_summary", "epoch_summary"),
        ("event_bandpower", "event_bandpower"),
    ):
        if goal in objectives:
            result = execute(tool_name, effective)
            if not result or not result["success"]:
                return fail("ACTION_FAILED", f"{tool_name} failed")
    return {
        "status": "completed", "reason": None, "tool_results": results,
        "effective_artifact_id": effective["artifact_id"],
        "effective_artifact_fingerprint": effective["expected_artifact_fingerprint"],
    }


def benchmark_epoch_fingerprint(shapes=None, repeats=7):
    """Measure full-content SHA-256 cost on deterministic in-memory EpochSets."""

    shapes = shapes or ((3, 2, 128), (64, 22, 512))
    rows = []
    for shape in shapes:
        data = np.arange(np.prod(shape), dtype=np.float32).reshape(shape) * np.float32(1e-9)
        epochs = EpochSet(
            data=data,
            sfreq=256.0,
            channel_names=tuple(f"C{index + 1}" for index in range(shape[1])),
            tmin=0.0,
            tmax=shape[2] / 256.0,
            event_labels=tuple("target" for _ in range(shape[0])),
            event_onsets_seconds=tuple(float(index) for index in range(shape[0])),
            baseline=None,
            rejected=(),
            source="synthetic://v11-fingerprint-benchmark",
        )
        timings = []
        fingerprints = []
        for _ in range(int(repeats)):
            started = time.perf_counter()
            fingerprints.append(epochs.content_fingerprint())
            timings.append((time.perf_counter() - started) * 1000.0)
        rows.append({
            "shape": list(shape),
            "bytes": int(data.nbytes),
            "repeats": int(repeats),
            "median_ms": float(median(timings)),
            "min_ms": float(min(timings)),
            "max_ms": float(max(timings)),
            "deterministic": len(set(fingerprints)) == 1,
        })
    return rows
