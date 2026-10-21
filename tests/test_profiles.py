import os
from pathlib import Path
import unittest

import numpy as np

from eeg_harness.edf import adapt_edf, load_edf, read_edf
from eeg_harness.profiles import EDF_NATIVE, TUEV_BIPOLAR_22, ProfileValidationError
from eeg_harness.record import EEGRecord


def record_for(profile, sfreq=None, channels=None):
    names = channels if channels is not None else profile.required_channels
    return EEGRecord(
        data=np.zeros((len(names), 512), dtype=np.float32),
        sfreq=sfreq if sfreq is not None else profile.target_sfreq,
        channel_names=tuple(names),
        reference=profile.reference,
        montage=profile.montage,
        source="memory://profile-test",
    )


class TaskProfileTest(unittest.TestCase):
    def test_missing_required_channel_is_rejected(self):
        record = record_for(TUEV_BIPOLAR_22, channels=TUEV_BIPOLAR_22.required_channels[:-1])
        with self.assertRaisesRegex(ProfileValidationError, "missing required channels"):
            TUEV_BIPOLAR_22.validate_record(record)

    def test_wrong_sampling_rate_is_rejected(self):
        record = record_for(TUEV_BIPOLAR_22, sfreq=128.0)
        with self.assertRaisesRegex(ProfileValidationError, "requires 256 Hz"):
            TUEV_BIPOLAR_22.validate_record(record)

    def test_model_is_not_compatible_with_native_profile(self):
        self.assertFalse(EDF_NATIVE.supports_tool("seizure_detection"))
        self.assertTrue(TUEV_BIPOLAR_22.supports_tool("seizure_detection"))


@unittest.skipUnless(
    os.environ.get("EEG_HARNESS_TEST_EDF"),
    "Set EEG_HARNESS_TEST_EDF for EDF profile integration tests",
)
class EDFProfileIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = Path(os.environ["EEG_HARNESS_TEST_EDF"])

    def test_bipolar_profile_preserves_verified_output(self):
        record = load_edf(self.path, TUEV_BIPOLAR_22)
        self.assertEqual(record.data.shape, (22, 61696))
        self.assertEqual(record.sfreq, 256.0)
        self.assertEqual(record.metadata["profile_id"], "tuev_bipolar_22")

    def test_native_profile_preserves_selected_edf_channels_and_rate(self):
        loaded = read_edf(self.path)
        eeg_channels = [
            name
            for name, kind in zip(loaded.raw.ch_names, loaded.raw.get_channel_types())
            if kind == "eeg"
        ]
        selected = eeg_channels[:2]
        record = adapt_edf(loaded, EDF_NATIVE, selected_channels=selected)
        self.assertEqual(record.channel_names, tuple(selected))
        self.assertEqual(record.sfreq, loaded.metadata["original_sfreq"])
        self.assertEqual(record.data.shape[0], 2)
        self.assertEqual(record.metadata["profile_id"], "edf_native")


if __name__ == "__main__":
    unittest.main()
