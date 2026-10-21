"""EDF loading and 22-channel derivation migrated from EEGAgent.

The numerical operations intentionally match ``tools/dataLoad.py``. The only
baseline addition is an explicit missing-channel error so a malformed model
input is not produced silently.
"""

from pathlib import Path

import mne
import numpy as np

from .polar import BIPOLAR_PAIRS
from .preprocessing import preprocessing

mne.set_log_level("WARNING")


def match_channel(prefix, channel_list):
    for channel in channel_list:
        if channel.startswith(prefix):
            return channel
    return None


def get_data(raw):
    data = []
    missing = []
    raw_channels = raw.ch_names
    for left_prefix, right_prefix in BIPOLAR_PAIRS:
        left = match_channel("EEG " + left_prefix, raw_channels)
        right = match_channel("EEG " + right_prefix, raw_channels)
        if left and right:
            data.append(raw[left][0][0] - raw[right][0][0])
        else:
            missing.append(f"{left_prefix}-{right_prefix}")

    if missing:
        raise ValueError(
            "EDF cannot produce the required 22-channel bipolar montage; "
            f"missing pairs: {', '.join(missing)}"
        )
    return np.asarray(data, dtype=np.float32)


def dataLoad(file_path, config):
    path = Path(file_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"EDF resource not found: {path}")
    raw = mne.io.read_raw_edf(str(path), preload=True)
    raw = preprocessing(raw, config)
    data = get_data(raw)
    return data


def inspect_edf(file_path):
    path = Path(file_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"EDF resource not found: {path}")
    raw = mne.io.read_raw_edf(str(path), preload=False, verbose=False)
    return {
        "original_sfreq": float(raw.info["sfreq"]),
        "original_channel_count": len(raw.ch_names),
        "original_sample_count": int(raw.n_times),
        "original_duration_seconds": float(raw.n_times / raw.info["sfreq"]),
        "original_channel_names": list(raw.ch_names),
    }
