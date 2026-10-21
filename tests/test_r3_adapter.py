import json
import os
from pathlib import Path
import tempfile
import unittest

import mne
import numpy as np

from eeg_harness.applications.r3 import (
    R3DatasetRules, R3_PROFILE, attach_external_event_table, load_r3_edf,
)
from eeg_harness.applications.r3.adapter import R3_EEG_CHANNELS
from eeg_harness.edf import LoadedEDF, adapt_edf
from eeg_harness.events import events_from_mne_raw
from eeg_harness.executor import Executor
from eeg_harness.pipeline import load_config
from eeg_harness.tools import build_default_registry


ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config(ROOT / "config" / "baseline.json")


class R3AdapterTest(unittest.TestCase):
    def test_external_event_table_has_explicit_alignment_and_provenance(self):
        from eeg_harness.record import EEGRecord

        record = EEGRecord(
            np.zeros((len(R3_EEG_CHANNELS), 600), dtype=np.float32),
            300.0,
            R3_EEG_CHANNELS,
            "native",
            "test",
            "synthetic://external",
            metadata={"profile_id": R3_PROFILE.profile_id},
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.csv"
            path.write_text(
                "onset_seconds,label,duration_seconds\n0.5,1,0\n", encoding="utf-8"
            )
            updated = attach_external_event_table(record, path, onset_offset_seconds=0.1)
        self.assertAlmostEqual(updated.events.events[0].onset_seconds, 0.6)
        self.assertTrue(updated.events.source.startswith("external-table-sha256:"))
    def test_dataset_specific_boundary_rule_stays_in_application_layer(self):
        rules = R3DatasetRules()
        self.assertEqual(rules.analysis_labels, tuple("12345678"))
        self.assertEqual(rules.boundary_labels, ("9",))
        self.assertIn("unverified", rules.boundary_rule_status)

    def test_registry_exposes_generic_tools_but_not_seizure_model(self):
        names = {item.name for item in build_default_registry().list_specs(R3_PROFILE.profile_id)}
        self.assertTrue({"record_info", "amplitude", "psd", "create_epochs"}.issubset(names))
        self.assertNotIn("seizure_detection", names)

    def test_r3_like_synthetic_edf_adapter(self):
        sfreq = 300.0
        data = np.zeros((len(R3_EEG_CHANNELS), 3600), dtype=np.float64)
        data[0] = np.sin(2 * np.pi * 10 * np.arange(3600) / sfreq) * 1e-6
        raw = mne.io.RawArray(data, mne.create_info(R3_EEG_CHANNELS, sfreq, "eeg"), verbose=False)
        raw.set_annotations(mne.Annotations([0.5, 1.5], [0, 0], ["1", "9"]))
        loaded = LoadedEDF(
            raw=raw,
            source="synthetic://r3-like",
            metadata={"original_sfreq": sfreq},
            events=events_from_mne_raw(raw, "synthetic://r3-like"),
        )
        record = adapt_edf(loaded, R3_PROFILE, selected_channels=R3_EEG_CHANNELS)
        self.assertEqual(record.data.shape, (21, 3600))
        self.assertEqual(record.sfreq, 300.0)
        self.assertEqual(record.events.labels, ("1", "9"))
        self.assertEqual([step["operation"] for step in record.processing_metadata], [
            "select_native_eeg_channels", "bandpass_filter", "notch_filter", "average_reference"
        ])
        json.dumps(record.events.summary(), allow_nan=False)


@unittest.skipUnless(os.environ.get("EEG_HARNESS_R3_SAMPLE"), "Set EEG_HARNESS_R3_SAMPLE")
class RealR3AdapterTest(unittest.TestCase):
    def test_real_sample_matches_profile_and_has_events(self):
        record = load_r3_edf(os.environ["EEG_HARNESS_R3_SAMPLE"])
        self.assertEqual(record.data.shape[0], 21)
        self.assertEqual(record.sfreq, 300.0)
        self.assertTrue(record.events.events)
        self.assertTrue(set(record.events.labels).issubset(set("123456789")))


if __name__ == "__main__":
    unittest.main()
