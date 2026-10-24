"""Local R3 numerical cross-checks; no record-level result is public by default."""

from collections import Counter
from pathlib import Path

import mne
import numpy as np
from scipy.signal import welch

from ...provenance import source_reference
from .ciedg import run_r3_ciedg_edf
from .workflow import run_r3_event_workflow


def select_fixed_subset(data_root):
    """First two EDFs in each of two sorted storage partitions, before analysis."""

    root = Path(data_root).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError("Configured R3 data root is unavailable")
    partitions = []
    for directory in sorted((item for item in root.iterdir() if item.is_dir()), key=lambda p: p.name):
        files = sorted(
            (item for item in directory.rglob("*.edf") if item.resolve().is_relative_to(root)),
            key=lambda p: p.relative_to(directory).as_posix(),
        )
        if files:
            partitions.append(files)
    selected = [path for files in partitions[:2] for path in files[:2]]
    return selected, {"storage_partition_count": len(partitions), "edf_count": sum(len(files) for files in partitions)}


def _result(execution, name):
    return next(
        (item for item in execution["tool_results"] if item["tool_name"] == name and item["success"]),
        None,
    )


def _manual_epochs(record, rules):
    samples = int(round((rules.epoch_window[1] - rules.epoch_window[0]) * record.sfreq))
    baseline_start = int(round((rules.baseline[0] - rules.epoch_window[0]) * record.sfreq))
    baseline_end = int(round((rules.baseline[1] - rules.epoch_window[0]) * record.sfreq))
    selected = set(rules.analysis_labels)
    rows, labels = [], []
    rejected = 0
    for event in record.events.events:
        if event.label not in selected:
            continue
        start = int(round((event.onset_seconds + rules.epoch_window[0]) * record.sfreq))
        end = start + samples
        if start < 0 or end > record.data.shape[1]:
            rejected += 1
            continue
        row = np.array(record.data[:, start:end], dtype=np.float32, copy=True)
        row -= row[:, baseline_start:baseline_end].mean(axis=1, keepdims=True)
        rows.append(row)
        labels.append(event.label)
    if not rows:
        return None, (), rejected
    return np.stack(rows), tuple(labels), rejected


def _manual_bandpower(data, labels, sfreq, channels, freq_bands):
    output = {}
    for label in sorted(set(labels)):
        rows = data[[index for index, value in enumerate(labels) if value == label]]
        channel_powers = {}
        for channel_index, channel in enumerate(channels):
            epoch_powers = []
            for row in rows:
                frequencies, density = welch(
                    np.asarray(row[channel_index]), fs=sfreq,
                    nperseg=min(row.shape[-1], int(round(sfreq))),
                )
                epoch_powers.append({
                    band: float(np.trapz(density[(frequencies >= low) & (frequencies <= high)],
                                         frequencies[(frequencies >= low) & (frequencies <= high)]))
                    for band, (low, high) in freq_bands.items()
                })
            channel_powers[channel] = {
                band: float(np.mean([item[band] for item in epoch_powers]))
                for band in freq_bands
            }
        output[label] = {"epoch_count": len(rows), "channels": channel_powers}
    return output


def _power_comparison(actual, expected, *, rtol=1e-5, atol=1e-12):
    if set(actual) != set(expected):
        return False, None
    differences = []
    for label, expected_condition in expected.items():
        actual_condition = actual[label]
        if actual_condition["epoch_count"] != expected_condition["epoch_count"]:
            return False, None
        if set(actual_condition["channels"]) != set(expected_condition["channels"]):
            return False, None
        for channel, bands in expected_condition["channels"].items():
            if set(actual_condition["channels"][channel]) != set(bands):
                return False, None
            for band, value in bands.items():
                actual_value = actual_condition["channels"][channel][band]
                differences.append(abs(actual_value - value))
                if not np.isclose(actual_value, value, rtol=rtol, atol=atol):
                    return False, max(differences)
    return True, max(differences, default=0.0)


def _without_artifact_identity(payload):
    return {
        key: value for key, value in payload.items()
        if key not in {"artifact_id", "artifact_fingerprint", "evidence_id"}
    }


def validate_one_edf(edf_path, config, rules):
    """Return sensitive local evidence and a compact check map for one EDF."""

    record, outputs, contexts = run_r3_ciedg_edf(edf_path, config, rules)
    deterministic = run_r3_event_workflow(edf_path, config, rules, include_quality=True)
    raw = mne.io.read_raw_edf(str(edf_path), preload=False, verbose=False)
    annotation_labels = Counter(str(value) for value in raw.annotations.description)
    events = record.events.events
    adjusted_onsets = np.asarray(raw.annotations.onset, dtype=float) - float(raw.first_time)
    event_onsets = np.asarray([event.onset_seconds for event in events], dtype=float)
    manual_data, manual_labels, manual_rejected = _manual_epochs(record, rules)
    summary_run = outputs["event_summary"]["execution"]
    analysis_run = outputs["quality_bandpower"]["execution"]
    summary_context = contexts["event_summary"]
    analysis_context = contexts["quality_bandpower"]
    listed = _result(summary_run, "list_events")
    summary_create = _result(summary_run, "create_epochs")
    summary = _result(summary_run, "epoch_summary")
    analysis_create = _result(analysis_run, "create_epochs")
    quality = _result(analysis_run, "epoch_quality")
    power = _result(analysis_run, "event_bandpower")
    deterministic_results = {item["tool_name"]: item for item in deterministic["results"]}
    checks = {
        "record_contract": record.data.shape[0] == 21 and record.sfreq == 300.0,
        "annotations_match": (
            len(events) == len(raw.annotations)
            and Counter(event.label for event in events) == annotation_labels
            and len(event_onsets) == len(adjusted_onsets)
            and np.allclose(event_onsets, adjusted_onsets, rtol=0, atol=1e-6)
        ),
        "both_tasks_completed": summary_run["status"] == analysis_run["status"] == "completed",
        "evidence_closed": summary_run["evidence_check"]["closed"] and analysis_run["evidence_check"]["closed"],
        "no_selection_or_rereference": all(
            item["tool_name"] not in {"select_quality_epochs", "rereference_epochs"}
            for run in (summary_run, analysis_run) for item in run["tool_results"]
        ),
    }
    if all(item is not None for item in (listed, summary_create, summary, analysis_create, quality, power)) and manual_data is not None:
        created_artifact = summary_context.artifacts[summary_create["data"]["artifact_id"]]
        analysis_artifact = analysis_context.artifacts[analysis_create["data"]["artifact_id"]]
        manual_power = _manual_bandpower(
            manual_data, manual_labels, record.sfreq, record.channel_names, config["freq_bands"],
        )
        oracle_match, oracle_error = _power_comparison(power["data"]["conditions"], manual_power)
        deterministic_match, deterministic_error = _power_comparison(
            power["data"]["conditions"], deterministic_results["event_bandpower"]["data"]["conditions"],
        )
        checks.update({
            "event_counts": listed["data"]["labels"] == dict(annotation_labels),
            "epoch_count_and_boundary": (
                summary_create["data"]["valid_epoch_count"] == len(manual_labels)
                and summary_create["data"]["rejected_epoch_count"] == manual_rejected
                and analysis_create["data"]["valid_epoch_count"] == len(manual_labels)
                and quality["data"]["epoch_counts"]["created"] == len(manual_labels)
                and quality["data"]["epoch_counts"]["boundary_rejected"] == manual_rejected
            ),
            "epoch_shape_values_labels": (
                created_artifact.data.shape == manual_data.shape == analysis_artifact.data.shape
                and np.isfinite(created_artifact.data).all()
                and np.isfinite(analysis_artifact.data).all()
                and np.allclose(created_artifact.data, manual_data, rtol=1e-5, atol=1e-12)
                and np.allclose(analysis_artifact.data, manual_data, rtol=1e-5, atol=1e-12)
                and created_artifact.event_labels == manual_labels == analysis_artifact.event_labels
            ),
            "deterministic_counts_quality": (
                deterministic_results["create_epochs"]["data"]["valid_epoch_count"] == len(manual_labels)
                and deterministic_results["create_epochs"]["data"]["rejected_epoch_count"] == manual_rejected
                and _without_artifact_identity(deterministic_results["epoch_quality"]["data"])
                == _without_artifact_identity(quality["data"])
            ),
            "summary_matches_manual_and_deterministic": (
                summary["data"]["valid_epoch_count"] == len(manual_labels)
                and summary["data"]["rejected_epoch_count"] == manual_rejected
                and summary["data"]["event_labels"] == list(manual_labels)
                and _without_artifact_identity(summary["data"])
                == _without_artifact_identity(deterministic_results["epoch_summary"]["data"])
            ),
            "bandpower_oracle": oracle_match,
            "bandpower_deterministic": deterministic_match,
            "artifact_lineage": all(
                item["data"]["artifact_id"] == creator["data"]["artifact_id"]
                and item["data"]["artifact_fingerprint"] == creator["data"]["artifact_fingerprint"]
                for item, creator in (
                    (summary, summary_create), (quality, analysis_create), (power, analysis_create),
                )
            ) and all(
                release["data"]["artifact_id"] == analysis_create["data"]["artifact_id"]
                for release in analysis_run["release_results"]
            ),
            "condition_retention": set(power["data"]["conditions"]) == set(manual_labels),
        })
    else:
        oracle_error = deterministic_error = None
        checks["required_tools_present"] = False
    return {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": {key: bool(value) for key, value in checks.items()},
        "max_abs_bandpower_error_oracle": oracle_error,
        "max_abs_bandpower_error_deterministic": deterministic_error,
        "resource": {"local_path": str(Path(edf_path).resolve()), **source_reference(edf_path)},
        "record": {
            "sfreq": record.sfreq, "shape": list(record.data.shape),
            "processing": list(record.processing_metadata),
        },
        "ciedg": outputs,
        "deterministic": deterministic,
        "context_bundles": {name: context.reproducibility_bundle() for name, context in contexts.items()},
    }

