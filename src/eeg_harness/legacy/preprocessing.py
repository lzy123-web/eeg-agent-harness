"""Preprocessing order migrated from EEGAgent ``tools/preprocessing.py``."""


def preprocessing(raw, config):
    fs = config["fs"]
    l_freq = config["l_freq"]
    h_freq = config["h_freq"]
    notch_freq = config["notch_freq"]

    raw.filter(l_freq=l_freq, h_freq=h_freq)
    if notch_freq is not None:
        raw.notch_filter(freqs=notch_freq)
    if raw.info["sfreq"] != fs:
        raw = raw.resample(sfreq=fs, npad="auto")
    return raw
