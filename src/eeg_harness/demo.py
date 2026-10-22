"""Clearly labelled synthetic records for reproducible demonstrations."""

import mne
import numpy as np

from .events import events_from_mne_raw
from .profiles import BIPOLAR_22_CHANNELS
from .record import EEGRecord


def build_synthetic_event_record():
    sfreq = 128.0
    times = np.arange(0, 8, 1 / sfreq)
    data = np.vstack([
        20e-6 * np.sin(2 * np.pi * 10 * times),
        15e-6 * np.sin(2 * np.pi * 6 * times),
    ]).astype(np.float32)
    raw = mne.io.RawArray(
        data, mne.create_info(["SYNTH-C1", "SYNTH-C2"], sfreq, "eeg"), verbose=False
    )
    raw.set_annotations(
        mne.Annotations(
            onset=[1.0, 3.0, 5.0, 7.8],
            duration=[0, 0, 0, 0],
            description=["stimulus", "stimulus", "control", "stimulus"],
        )
    )
    return EEGRecord(
        data=data,
        sfreq=sfreq,
        channel_names=("SYNTH-C1", "SYNTH-C2"),
        reference="synthetic native reference",
        montage="synthetic two-channel layout",
        source="synthetic://mne-rawarray-event-demo",
        processing_metadata=({"operation": "synthetic_signal_generation"},),
        metadata={"profile_id": "edf_native", "is_synthetic": True},
        events=events_from_mne_raw(raw, "synthetic://mne-rawarray-event-demo"),
    )


def build_synthetic_no_event_record():
    """Return the same deterministic signal without annotations."""
    record = build_synthetic_event_record()
    return EEGRecord(
        data=record.data.copy(),
        sfreq=record.sfreq,
        channel_names=record.channel_names,
        reference=record.reference,
        montage=record.montage,
        source="synthetic://mne-rawarray-no-event-demo",
        processing_metadata=record.processing_metadata,
        metadata=dict(record.metadata),
        events=None,
    )


def build_synthetic_tuev_record():
    """Create contract-compatible synthetic input with no scientific label."""
    sfreq = 256.0
    times = np.arange(0, 12, 1 / sfreq)
    data = np.vstack([
        (5e-6 + index * 0.05e-6) * np.sin(2 * np.pi * (6 + index % 8) * times)
        for index in range(len(BIPOLAR_22_CHANNELS))
    ]).astype(np.float32)
    return EEGRecord(
        data=data,
        sfreq=sfreq,
        channel_names=BIPOLAR_22_CHANNELS,
        reference="synthetic pairwise subtraction",
        montage="synthetic 22-channel longitudinal bipolar montage",
        source="synthetic://tuev-compatible-baseline-v1",
        processing_metadata=({"operation": "synthetic_signal_generation"},),
        metadata={
            "profile_id": "tuev_bipolar_22",
            "is_synthetic": True,
            "scientific_interpretation": "none",
        },
    )

