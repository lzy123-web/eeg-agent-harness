"""Amplitude and PSD algorithms migrated from EEGAgent ``tools/windowInfo.py``."""

import numpy as np
from scipy.signal import welch

from ..record import EEGRecord


def _ordered_channels(record, names):
    requested = (names,) if isinstance(names, str) else tuple(names)
    missing = [name for name in requested if name not in record.channel_names]
    if missing:
        raise ValueError(f"Unknown EEG channel(s): {', '.join(missing)}")
    return sorted(requested, key=record.channel_names.index)


def compute_amplitude(record: EEGRecord, name, start, end, config):
    if not 0 <= start < end:
        raise ValueError("Expected 0 <= start < end")
    if end - start > 60:
        raise ValueError("The time interval must not exceed 60 seconds")
    channels = _ordered_channels(record, name)
    selected = record.slice(start, end, channels)
    amplitude_features = {}
    for channel, channel_data in zip(channels, selected):
        amplitude_features[channel] = {
            "mean_abs": "{:.2e}".format(np.mean(np.abs(channel_data))),
            "rms": "{:.2e}".format(np.sqrt(np.mean(np.square(channel_data)))),
            "max_val": "{:.2e}".format(np.max(channel_data)),
            "min_val": "{:.2e}".format(np.min(channel_data)),
        }
    return amplitude_features


def compute_psd(record: EEGRecord, name, start, end, config):
    if not 0 <= start < end:
        raise ValueError("Expected 0 <= start < end")
    if end - start > 60:
        raise ValueError("The time interval must not exceed 60 seconds")
    channels = _ordered_channels(record, name)
    selected = record.slice(start, end, channels)
    fs = record.sfreq
    freq_bands = config["freq_bands"]
    psds = {}
    for channel, channel_data in zip(channels, selected):
        frequencies, density = welch(channel_data, fs=fs, nperseg=fs)
        band_power = {}
        for band_name, (low, high) in freq_bands.items():
            indices = np.logical_and(frequencies >= low, frequencies <= high)
            band_power[band_name] = "{:.2e}".format(
                np.trapz(density[indices], frequencies[indices])
            )
        psds[channel] = band_power
    return psds
