"""Clearly labelled synthetic records for reproducible demonstrations."""

import mne
import numpy as np

from .events import events_from_mne_raw
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

