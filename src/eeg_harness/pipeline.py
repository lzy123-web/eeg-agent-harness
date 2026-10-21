"""End-to-end deterministic baseline orchestration."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

import mne
import numpy as np
import scipy
import torch

from .legacy.data_load import dataLoad, inspect_edf
from .legacy.features import compute_amplitude, compute_psd
from .legacy.polar import INDEX_TO_NAME
from .legacy.register_data import clearRegisteredData, registerData
from .legacy.seizure import seizureNormalModel_OneSecond


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as resource:
        for chunk in iter(lambda: resource.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_config(config_path):
    path = Path(config_path).expanduser().resolve()
    with path.open("r", encoding="utf-8") as stream:
        config = json.load(stream)
    required = {"fs", "l_freq", "h_freq", "notch_freq", "freq_bands"}
    missing = required.difference(config)
    if missing:
        raise ValueError(f"Baseline config is missing keys: {sorted(missing)}")
    return config


def run_baseline(edf_path, model_path, config_path, channel="FP1-F7", start=0, end=1):
    edf = Path(edf_path).expanduser().resolve()
    model = Path(model_path).expanduser().resolve()
    config_file = Path(config_path).expanduser().resolve()
    config = load_config(config_file)
    source_info = inspect_edf(edf)

    started = time.perf_counter()
    data = dataLoad(edf, config)
    load_seconds = time.perf_counter() - started
    if data.shape[0] != 22:
        raise ValueError(f"Expected 22 bipolar channels, got {data.shape[0]}")
    if data.dtype != np.float32:
        raise ValueError(f"Expected float32 data, got {data.dtype}")

    registerData(data)
    try:
        feature_started = time.perf_counter()
        amplitude = compute_amplitude([channel], start, end, config)
        psd = compute_psd([channel], start, end, config)
        feature_seconds = time.perf_counter() - feature_started

        inference_started = time.perf_counter()
        seizure = seizureNormalModel_OneSecond(
            [channel], start, end, config, model_path=model
        )
        inference_seconds = time.perf_counter() - inference_started
    finally:
        clearRegisteredData()

    result = {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input": {
            "edf_path": str(edf),
            "edf_sha256": _sha256(edf),
            "selected_channel": channel,
            "window_seconds": [start, end],
            **source_info,
        },
        "preprocessing": {
            "l_freq": config["l_freq"],
            "h_freq": config["h_freq"],
            "notch_freq": config["notch_freq"],
            "target_sfreq": config["fs"],
            "output_shape": list(data.shape),
            "output_dtype": str(data.dtype),
            "output_channel_names": [INDEX_TO_NAME[index] for index in range(22)],
        },
        "features": {"amplitude": amplitude, "band_power": psd},
        "model_inference": {
            "tool": "seizureNormalModel_OneSecond",
            "model_path": str(model),
            "model_sha256": _sha256(model),
            "model_input_shape_per_second": [1, config["fs"]],
            "result": seizure,
            "training_data_source": "源码未提供",
        },
        "runtime": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "mne": mne.__version__,
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "torch": torch.__version__,
            "device": "cpu",
            "load_and_preprocess_seconds": round(load_seconds, 6),
            "feature_seconds": round(feature_seconds, 6),
            "inference_seconds": round(inference_seconds, 6),
        },
        "legacy": {
            "uses_process_global_data_store": True,
            "replacement_required": "Replace legacy.register_data before concurrent or multi-record execution",
        },
    }
    json.dumps(result, ensure_ascii=False, allow_nan=False)
    return result
