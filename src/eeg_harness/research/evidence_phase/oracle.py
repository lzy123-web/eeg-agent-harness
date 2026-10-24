"""Independent NumPy/SciPy oracle; it does not call Harness EEG tools."""

import numpy as np
from scipy.signal import welch


def oracle_epoch_data(record, truth, indices=None):
    """Extract expected event windows directly from record samples and injection truth."""

    selected = truth.expected_kept_indices if indices is None else tuple(indices)
    epoch_samples = int(round((truth.tmax - truth.tmin) * record.sfreq))
    epochs = []
    for index in selected:
        onset = truth.event_onsets_seconds[index]
        start = int(round((onset + truth.tmin) * record.sfreq))
        epochs.append(record.data[:, start:start + epoch_samples].copy())
    return np.stack(epochs).astype(np.float32, copy=False)


def oracle_event_bandpower(epoch_data, sfreq, channel_names, freq_bands):
    """Compute the expected arithmetic mean of per-Epoch Welch band powers."""

    result = {}
    for channel_index, channel_name in enumerate(channel_names):
        per_epoch = []
        for epoch in epoch_data[:, channel_index, :]:
            frequencies, density = welch(
                epoch, fs=sfreq, nperseg=min(len(epoch), max(1, int(round(sfreq))))
            )
            powers = []
            for low, high in freq_bands.values():
                mask = np.logical_and(frequencies >= low, frequencies <= high)
                powers.append(float(np.trapz(density[mask], frequencies[mask])))
            per_epoch.append(powers)
        means = np.asarray(per_epoch, dtype=float).mean(axis=0)
        result[channel_name] = {
            name: float(value) for name, value in zip(freq_bands, means)
        }
    return result
