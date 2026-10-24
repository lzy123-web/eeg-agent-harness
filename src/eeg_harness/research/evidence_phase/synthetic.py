"""Deterministic EEG construction with injection truth independent of tool output."""

from dataclasses import dataclass

import numpy as np

from ...events import EEGEvent, EventSet
from ...record import EEGRecord


@dataclass(frozen=True)
class SyntheticEpochTruth:
    label: str
    event_onsets_seconds: tuple[float, ...]
    anomalous_epoch_indices: tuple[int, ...]
    expected_kept_indices: tuple[int, ...]
    tmin: float
    tmax: float


def build_quality_selection_record(anomalous_epoch_indices=(1,)):
    """Build three non-overlapping trials with explicitly injected high amplitude.

    The injection truth is returned separately and is never inferred from the
    quality tool. This record is synthetic and has no clinical interpretation.
    """

    sfreq = 128.0
    duration = 10.0
    sample_count = int(round(duration * sfreq))
    times = np.arange(sample_count) / sfreq
    data = np.vstack([
        5e-6 * np.sin(2 * np.pi * 3 * times),
        4e-6 * np.sin(2 * np.pi * 4 * times),
    ]).astype(np.float32)
    onsets = (1.0, 4.0, 7.0)
    anomalous = tuple(sorted({int(index) for index in anomalous_epoch_indices}))
    if any(index < 0 or index >= len(onsets) for index in anomalous):
        raise ValueError("Anomalous epoch index is outside the synthetic trial set")

    local_time = np.arange(int(sfreq)) / sfreq
    for index, onset in enumerate(onsets):
        start = int(round(onset * sfreq))
        end = start + len(local_time)
        if index in anomalous:
            data[0, start:end] = 420e-6 * np.sin(2 * np.pi * 20 * local_time)
            data[1, start:end] = 320e-6 * np.sin(2 * np.pi * 18 * local_time)
        else:
            data[0, start:end] = 20e-6 * np.sin(2 * np.pi * 10 * local_time)
            data[1, start:end] = 15e-6 * np.sin(2 * np.pi * 6 * local_time)

    label = "target"
    events = EventSet(
        tuple(EEGEvent(label, onset, source_index=index) for index, onset in enumerate(onsets)),
        source="synthetic://ccep-evidence-phase-events",
    )
    kept = tuple(index for index in range(len(onsets)) if index not in anomalous)
    record = EEGRecord(
        data=data,
        sfreq=sfreq,
        channel_names=("SYNTH-C1", "SYNTH-C2"),
        reference="synthetic native reference",
        montage="synthetic two-channel layout",
        source="synthetic://ccep-evidence-phase-quality-selection",
        processing_metadata=({"operation": "deterministic_synthetic_generation"},),
        metadata={
            "profile_id": "edf_native",
            "is_synthetic": True,
            "scientific_interpretation": "none",
        },
        events=events,
    )
    truth = SyntheticEpochTruth(label, onsets, anomalous, kept, 0.0, 1.0)
    return record, truth
