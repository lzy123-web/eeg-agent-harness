import json
import unittest

import mne
import numpy as np

from eeg_harness.context import ExecutionContext
from eeg_harness.events import events_from_mne_raw
from eeg_harness.executor import Executor
from eeg_harness.pipeline import load_config
from eeg_harness.profiles import EDF_NATIVE
from eeg_harness.quality import record_quality
from eeg_harness.record import EEGRecord
from eeg_harness.tooling import ToolRequest
from eeg_harness.tools import build_default_registry


def make_record(data, sfreq=256, processing=(), events=False):
    channels = tuple(f"C{i + 1}" for i in range(data.shape[0]))
    event_set = None
    if events:
        raw = mne.io.RawArray(data, mne.create_info(channels, sfreq, "eeg"), verbose=False)
        raw.set_annotations(mne.Annotations([0.1, 1.0, 1.9], [0, 0, 0], ["A"] * 3))
        event_set = events_from_mne_raw(raw, "synthetic://quality")
    return EEGRecord(
        data.astype(np.float32), sfreq, channels, "native", "native",
        "synthetic://quality", tuple(processing), {"profile_id": "edf_native"}, event_set,
    )


class RecordQualityTest(unittest.TestCase):
    def test_controlled_flatline_spike_and_clean_false_positive(self):
        sfreq = 256
        time = np.arange(sfreq * 2) / sfreq
        clean = 20e-6 * np.sin(2 * np.pi * 10 * time)
        flat = np.zeros_like(clean)
        spike = clean.copy()
        spike[::20] = 500e-6
        evidence = record_quality(make_record(np.vstack([clean, flat, spike])), "edf_native")
        self.assertFalse(evidence["channel_metrics"]["C1"]["flatline_fraction"]["flagged"])
        self.assertFalse(evidence["channel_metrics"]["C1"]["high_amplitude_fraction"]["flagged"])
        self.assertTrue(evidence["channel_metrics"]["C2"]["flatline_fraction"]["flagged"])
        self.assertTrue(evidence["channel_metrics"]["C3"]["high_amplitude_fraction"]["flagged"])
        json.dumps(evidence, allow_nan=False)

    def test_line_noise_detects_injection_but_respects_processing_validity(self):
        sfreq = 256
        time = np.arange(sfreq * 4) / sfreq
        clean = 20e-6 * np.sin(2 * np.pi * 10 * time)
        noisy = clean + 80e-6 * np.sin(2 * np.pi * 50 * time)
        evidence = record_quality(make_record(np.vstack([clean, noisy])), "edf_native")
        self.assertFalse(evidence["channel_metrics"]["C1"]["line_noise_ratio"]["flagged"])
        self.assertTrue(evidence["channel_metrics"]["C2"]["line_noise_ratio"]["flagged"])
        filtered = make_record(
            np.vstack([clean]), processing=({"operation": "bandpass_filter", "l_freq": 1, "h_freq": 40},)
        )
        metric = record_quality(filtered, "filtered")["channel_metrics"]["C1"]["line_noise_ratio"]
        self.assertEqual(metric["validity"], "not_observable")
        self.assertIsNone(metric["value"])

    def test_epoch_quality_reports_impact_without_waveform(self):
        sfreq = 256
        time = np.arange(sfreq * 2) / sfreq
        data = np.vstack([20e-6 * np.sin(2 * np.pi * 10 * time)])
        record = make_record(data, events=True)
        context = ExecutionContext(
            record, EDF_NATIVE, Executor(build_default_registry(), load_config("config/baseline.json"))
        )
        created = context.execute(ToolRequest(
            "create_epochs", {"labels": ["A"], "tmin": -0.1, "tmax": 0.2}
        ))
        quality = context.execute(ToolRequest(
            "epoch_quality", {"artifact_id": created.data["artifact_id"]}
        ))
        self.assertTrue(quality.success)
        self.assertNotIn("data", quality.data)
        self.assertGreater(quality.data["epoch_counts"]["boundary_rejected"], 0)
        json.dumps(quality.to_dict(), allow_nan=False)


if __name__ == "__main__":
    unittest.main()
