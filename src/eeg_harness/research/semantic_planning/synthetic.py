"""Deterministic synthetic EEG scenes and independent injected truth."""

from collections import Counter
from dataclasses import replace

import numpy as np
from scipy.signal import butter, sosfiltfilt

from ...events import EEGEvent, EventSet, create_epoch_set
from ...record import EEGRecord
from .contracts import lowpass40
from .models import ArtifactPayload, ScientificRequirement, SemanticArtifact, stable_id


def _raw_record(sfreq=256.0, with_events=True, fractional=False):
    duration = 8.0
    times = np.arange(int(round(duration * sfreq))) / sfreq
    data = np.stack([
        20e-6 * np.sin(2 * np.pi * 10 * times) + 8e-6 * np.sin(2 * np.pi * 50 * times),
        12e-6 * np.sin(2 * np.pi * 6 * times) + 6e-6 * np.sin(2 * np.pi * 50 * times),
    ]).astype(np.float32)
    events = None
    truth_times = ()
    if with_events:
        truth_times = (1.013, 2.117, 3.209, 4.333, 5.407, 6.521) if fractional else (1., 2., 3., 4., 5., 6.)
        labels = ("A", "B", "A", "B", "A", "B")
        events = EventSet(tuple(
            EEGEvent(label, onset, source_index=index)
            for index, (label, onset) in enumerate(zip(labels, truth_times))
        ), source="synthetic://point1-events")
    record = EEGRecord(
        data=data, sfreq=sfreq, channel_names=("C3", "C4"),
        reference="synthetic common reference", montage="synthetic two-channel",
        source="synthetic://point1-record", events=events,
        metadata={"synthetic": True},
    )
    return record, truth_times


def _record_artifact(record, stage="raw", parent_ids=(), root_id="point1-root"):
    labels = tuple(event.label for event in record.events.events) if record.events else ()
    counts = Counter(labels)
    return SemanticArtifact(
        artifact_id=stable_id("seed", stage, record.sfreq, labels),
        kind="record", stage=stage, root_id=root_id, parent_ids=tuple(parent_ids),
        sfreq=record.sfreq, reference=record.reference, passband_hz=(0.0, None),
        channels=record.channel_names, time_reference="seconds_from_record_start",
        event_alignment_source="synthetic injected seconds" if record.events else None,
        event_labels=tuple(sorted(counts)), condition_counts=tuple(sorted(counts.items())),
        observability=(("raw_line_noise", "true"),),
        properties=(("event_labels_by_index", list(labels)),),
    )


def _filtered_payload(raw_payload):
    requirement = ScientificRequirement("seed-lowpass", "bandpower", {"require_lowpass_hz": 40.0})
    semantic, _, _ = lowpass40(raw_payload.semantic, requirement)
    record = raw_payload.value
    sos = butter(4, 40.0 / (record.sfreq / 2), btype="lowpass", output="sos")
    filtered = replace(
        record, data=sosfiltfilt(sos, record.data, axis=1).astype(np.float32),
        processing_metadata=({"operation": "lowpass_filter", "h_freq": 40.0},),
    )
    return ArtifactPayload(semantic, filtered)


def build_scene(initial):
    sfreq = 250.0 if "250" in initial else (128.0 if "128" in initial else 256.0)
    with_events = initial not in ("raw", "raw_and_lowpass40", "lowpass40", "raw_no_events")
    fractional = initial == "raw_fractional_events_250"
    record, truth_times = _raw_record(sfreq, with_events=with_events, fractional=fractional)
    raw_payload = ArtifactPayload(_record_artifact(record), record)
    payloads = [raw_payload]
    if initial in ("lowpass40", "raw_and_lowpass40"):
        filtered = _filtered_payload(raw_payload)
        payloads = [filtered] if initial == "lowpass40" else [raw_payload, filtered]
    if initial in ("epochs_clean", "epochs_with_bad"):
        record, truth_times = _raw_record(256.0, with_events=True)
        epochs = create_epoch_set(record, ["A", "B"], -0.1, 0.4)
        if initial == "epochs_with_bad":
            copied = epochs.data.copy()
            copied[1] += 500e-6
            epochs = replace(epochs, data=copied)
        labels = tuple(epochs.event_labels)
        counts = Counter(labels)
        semantic = SemanticArtifact(
            artifact_id=stable_id("seed", initial), kind="epochs", stage="epoched",
            root_id="point1-root", sfreq=epochs.sfreq, reference=record.reference,
            passband_hz=(0.0, None), channels=epochs.channel_names,
            time_reference="event_relative_seconds", event_alignment_source="synthetic injected seconds",
            event_labels=tuple(sorted(counts)), condition_counts=tuple(sorted(counts.items())),
            properties=(("epoch_labels_by_index", list(labels)), ("selected", False),
                        ("valid_epoch_count", len(labels))),
        )
        payloads = [ArtifactPayload(semantic, epochs)]
    truth = {
        "event_onsets_seconds": list(truth_times),
        "raw_line_frequency_hz": 50.0,
        "raw_line_injected": True,
        "initial": initial,
    }
    return record, tuple(payloads), truth
