"""Dataset-neutral EDF reading and profile-based record adaptation."""

from dataclasses import dataclass
from pathlib import Path

import mne
import numpy as np

from .events import EventSet, events_from_mne_raw
from .legacy.data_load import get_data
from .legacy.preprocessing import preprocessing
from .record import EEGRecord

mne.set_log_level("WARNING")


@dataclass(frozen=True)
class LoadedEDF:
    raw: object
    source: str
    metadata: dict
    events: EventSet


def read_edf(file_path):
    path = Path(file_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"EDF resource not found: {path}")
    raw = mne.io.read_raw_edf(str(path), preload=True)
    metadata = {
        "original_sfreq": float(raw.info["sfreq"]),
        "original_channel_count": len(raw.ch_names),
        "original_sample_count": int(raw.n_times),
        "original_duration_seconds": float(raw.n_times / raw.info["sfreq"]),
        "original_channel_names": list(raw.ch_names),
    }
    return LoadedEDF(
        raw=raw,
        source=str(path),
        metadata=metadata,
        events=events_from_mne_raw(raw, path),
    )


def adapt_edf(loaded, profile, selected_channels=None):
    if profile.adapter == "native":
        eeg_channels = [
            name
            for name, channel_type in zip(loaded.raw.ch_names, loaded.raw.get_channel_types())
            if channel_type == "eeg"
        ]
        channels = tuple(selected_channels) if selected_channels is not None else tuple(eeg_channels)
        if not channels:
            raise ValueError("No EEG channels were selected from the EDF")
        missing = [name for name in channels if name not in eeg_channels]
        if missing:
            raise ValueError(f"Selected EDF EEG channel(s) not found: {', '.join(missing)}")
        data = loaded.raw.get_data(picks=list(channels)).astype(np.float32, copy=False)
        processing = ({"operation": "select_native_eeg_channels", "channels": list(channels)},)
        sfreq = float(loaded.raw.info["sfreq"])
    elif profile.adapter == "bipolar_22":
        config = {
            "fs": int(profile.target_sfreq),
            "l_freq": profile.l_freq,
            "h_freq": profile.h_freq,
            "notch_freq": profile.notch_freq,
        }
        processed = preprocessing(loaded.raw.copy(), config)
        data = get_data(processed)
        channels = profile.required_channels
        sfreq = float(processed.info["sfreq"])
        processing = (
            {"operation": "bandpass_filter", "l_freq": profile.l_freq, "h_freq": profile.h_freq},
            {"operation": "notch_filter", "frequency": profile.notch_freq},
            {"operation": "resample", "sfreq": profile.target_sfreq},
            {"operation": "bipolar_derivation", "channel_count": len(channels)},
        )
    else:
        raise ValueError(f"Unsupported EEG profile adapter: {profile.adapter}")

    record = EEGRecord(
        data=data,
        sfreq=sfreq,
        channel_names=channels,
        reference=profile.reference,
        montage=profile.montage,
        source=loaded.source,
        processing_metadata=processing,
        metadata={"source_edf": loaded.metadata, "profile_id": profile.profile_id},
        events=loaded.events,
    )
    profile.validate_record(record)
    return record


def load_edf(file_path, profile, selected_channels=None):
    return adapt_edf(read_edf(file_path), profile, selected_channels=selected_channels)

