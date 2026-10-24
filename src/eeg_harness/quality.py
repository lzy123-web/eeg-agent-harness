"""Measured EEG quality evidence with explicit validity and empirical rules."""

from collections import Counter
import hashlib
import json

import numpy as np
from scipy.signal import welch


DEFAULT_THRESHOLDS = {
    "flatline_delta_volts": 1e-8,
    "flatline_fraction": 0.95,
    "high_amplitude_volts": 200e-6,
    "high_amplitude_fraction": 0.01,
    "line_noise_ratio": 0.20,
}


def _evidence_id(kind, profile_id, scope):
    payload = json.dumps([kind, profile_id, scope], sort_keys=True).encode("utf-8")
    return f"evidence-{hashlib.sha256(payload).hexdigest()[:16]}"


def _processing_limits(record, line_frequency):
    for step in record.processing_metadata:
        if step.get("operation") == "notch_filter" and abs(
            float(step.get("frequency")) - line_frequency
        ) < 1e-6:
            return "not_applicable", "target frequency was explicitly notch-filtered"
        if step.get("operation") == "bandpass_filter":
            high = step.get("h_freq")
            if high is not None and float(high) < line_frequency + 1:
                return "not_observable", "target frequency is outside the processed passband"
    if record.sfreq / 2 <= line_frequency + 1:
        return "not_observable", "target frequency is above the usable Nyquist range"
    return "valid", None


def _channel_metrics(data, sfreq, thresholds, line_frequency, line_validity):
    difference = np.abs(np.diff(data))
    flatline_fraction = float(np.mean(difference <= thresholds["flatline_delta_volts"]))
    high_fraction = float(np.mean(np.abs(data) >= thresholds["high_amplitude_volts"]))
    output = {
        "flatline_fraction": {
            "value": flatline_fraction,
            "unit": "fraction_of_adjacent_differences",
            "threshold": thresholds["flatline_fraction"],
            "threshold_status": "empirical",
            "flagged": flatline_fraction >= thresholds["flatline_fraction"],
            "validity": "valid",
        },
        "high_amplitude_fraction": {
            "value": high_fraction,
            "unit": "fraction_of_samples",
            "amplitude_threshold_volts": thresholds["high_amplitude_volts"],
            "threshold": thresholds["high_amplitude_fraction"],
            "threshold_status": "empirical",
            "flagged": high_fraction >= thresholds["high_amplitude_fraction"],
            "validity": "valid",
        },
    }
    validity, reason = line_validity
    line_metric = {
        "value": None,
        "unit": "fraction_of_1_to_nyquist_power",
        "frequency_hz": line_frequency,
        "threshold": thresholds["line_noise_ratio"],
        "threshold_status": "empirical",
        "flagged": None,
        "validity": validity,
        "limitation": reason,
    }
    if validity == "valid":
        frequencies, density = welch(
            data, fs=sfreq, nperseg=min(len(data), max(256, int(round(sfreq * 2))))
        )
        denominator_mask = (frequencies >= 1) & (frequencies <= sfreq / 2)
        target_mask = abs(frequencies - line_frequency) <= 1.0
        total = float(np.trapz(density[denominator_mask], frequencies[denominator_mask]))
        target = float(np.trapz(density[target_mask], frequencies[target_mask]))
        ratio = 0.0 if total <= 0 else target / total
        line_metric.update({
            "value": float(ratio),
            "flagged": ratio >= thresholds["line_noise_ratio"],
            "limitation": "ratio is signal-processing evidence, not a calibrated reliability score",
        })
    output["line_noise_ratio"] = line_metric
    return output


def record_quality(record, profile_id, *, channels=None, start=None, end=None,
                   line_frequency=50.0, thresholds=None):
    thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    selected = tuple(channels) if channels is not None else record.channel_names
    start = 0.0 if start is None else float(start)
    end = record.duration_seconds if end is None else float(end)
    data = record.slice(start, end, selected)
    line_validity = _processing_limits(record, float(line_frequency))
    per_channel = {
        name: _channel_metrics(
            data[index], record.sfreq, thresholds, float(line_frequency), line_validity
        )
        for index, name in enumerate(selected)
    }
    flagged = [
        name for name, metrics in per_channel.items()
        if any(item.get("flagged") is True for item in metrics.values())
    ]
    scope = {"channels": list(selected), "start_seconds": start, "end_seconds": end}
    return {
        "evidence_id": _evidence_id("record_quality", profile_id, scope),
        "evidence_type": "record_quality",
        "profile_id": profile_id,
        "source_stage": "current_EEGRecord_after_declared_processing",
        "scope": scope,
        "measured_facts": {
            "sfreq_hz": record.sfreq,
            "duration_seconds": end - start,
            "channel_count": len(selected),
            "event_count": 0 if record.events is None else len(record.events.events),
        },
        "thresholds": thresholds,
        "threshold_status": "empirical_not_clinically_calibrated",
        "channel_metrics": per_channel,
        "flagged_channels": flagged,
        "validity": "measurement_only_not_scientific_or_clinical_reliability",
    }


def epoch_quality(epochs, profile_id, *, thresholds=None):
    thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    artifact_fingerprint = epochs.content_fingerprint()
    bad_indices = []
    reasons = Counter()
    line_validity = ("unknown", "Epoch provenance does not establish raw line-noise observability")
    for epoch_index, epoch in enumerate(epochs.data):
        bad = False
        for channel in epoch:
            metrics = _channel_metrics(
                channel, epochs.sfreq, thresholds, 50.0, line_validity
            )
            if metrics["flatline_fraction"]["flagged"]:
                reasons["FLATLINE"] += 1
                bad = True
            if metrics["high_amplitude_fraction"]["flagged"]:
                reasons["HIGH_AMPLITUDE"] += 1
                bad = True
        if bad:
            bad_indices.append(epoch_index)
    original_valid = int(epochs.data.shape[0])
    boundary_rejected = len(epochs.rejected)
    quality_valid = original_valid - len(bad_indices)
    total = original_valid + boundary_rejected
    label_counts = Counter(epochs.event_labels)
    usable_label_counts = Counter(
        label for index, label in enumerate(epochs.event_labels)
        if index not in set(bad_indices)
    )
    return {
        "evidence_id": _evidence_id("epoch_quality", profile_id, {
            "artifact_id": epochs.artifact_id,
            "artifact_fingerprint": artifact_fingerprint,
            "thresholds": thresholds,
        }),
        "evidence_type": "epoch_quality",
        "profile_id": profile_id,
        "source_stage": "EpochSet_after_declared_record_processing_and_optional_baseline",
        "artifact_id": epochs.artifact_id,
        "artifact_fingerprint": artifact_fingerprint,
        "epoch_counts": {
            "requested_or_boundary_checked": total,
            "created": original_valid,
            "boundary_rejected": boundary_rejected,
            "quality_flagged": len(bad_indices),
            "quality_usable": quality_valid,
        },
        "condition_counts_before_quality": dict(sorted(label_counts.items())),
        "condition_counts_quality_usable": dict(sorted(usable_label_counts.items())),
        "quality_flag_reasons": dict(sorted(reasons.items())),
        "flagged_epoch_indices": bad_indices,
        "usable_fraction_of_created": 0.0 if original_valid == 0 else quality_valid / original_valid,
        "thresholds": thresholds,
        "threshold_status": "empirical_not_clinically_calibrated",
        "validity": "screening_suggestion_only; no automatic deletion performed",
    }
