"""Amplitude and PSD algorithms migrated from EEGAgent ``tools/windowInfo.py``."""

import numpy as np
from scipy.signal import welch

from .polar import INDEX_TO_NAME, NAME_TO_INDEX
from .register_data import getRegisteredData


def _select_channels(name, data):
    try:
        ids = sorted(NAME_TO_INDEX[channel] for channel in name)
    except KeyError as exc:
        raise ValueError(f"Unknown bipolar channel: {exc.args[0]}") from exc
    return ids, [INDEX_TO_NAME[index] for index in ids], data[ids]


def compute_amplitude(name, start, end, config):
    if not 0 <= start < end:
        raise ValueError("Expected 0 <= start < end")
    if end - start > 60:
        raise ValueError("The time interval must not exceed 60 seconds")
    data = getRegisteredData(start, end, config)
    _, channels, selected = _select_channels(name, data)
    amplitude_features = {}
    for channel, channel_data in zip(channels, selected):
        amplitude_features[channel] = {
            "mean_abs": "{:.2e}".format(np.mean(np.abs(channel_data))),
            "rms": "{:.2e}".format(np.sqrt(np.mean(np.square(channel_data)))),
            "max_val": "{:.2e}".format(np.max(channel_data)),
            "min_val": "{:.2e}".format(np.min(channel_data)),
        }
    return amplitude_features


def compute_psd(name, start, end, config):
    if not 0 <= start < end:
        raise ValueError("Expected 0 <= start < end")
    if end - start > 60:
        raise ValueError("The time interval must not exceed 60 seconds")
    data = getRegisteredData(start, end, config)
    _, channels, selected = _select_channels(name, data)
    fs = config["fs"]
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
