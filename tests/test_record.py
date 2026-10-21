import unittest

import numpy as np

from eeg_harness.legacy.features import compute_amplitude
from eeg_harness.record import EEGRecord


def make_record(value, source):
    return EEGRecord(
        data=np.full((2, 20), value, dtype=np.float32),
        sfreq=10.0,
        channel_names=("C1", "C2"),
        reference="synthetic reference",
        montage="synthetic montage",
        source=source,
        processing_metadata=({"operation": "test_fixture"},),
    )


class EEGRecordSliceTest(unittest.TestCase):
    def setUp(self):
        self.record = EEGRecord(
            data=np.arange(40, dtype=np.float32).reshape(2, 20),
            sfreq=10.0,
            channel_names=("C1", "C2"),
            reference="synthetic reference",
            montage="synthetic montage",
            source="memory://slice-test",
        )

    def test_normal_slice(self):
        window = self.record.slice(0.5, 1.0, ["C2"])
        np.testing.assert_array_equal(window, self.record.data[1:2, 5:10])
        self.assertEqual(window.shape, (1, 5))

    def test_invalid_channel(self):
        with self.assertRaisesRegex(ValueError, "Unknown EEG channel"):
            self.record.slice(0, 1, ["missing"])

    def test_time_out_of_range(self):
        with self.assertRaisesRegex(ValueError, "beyond record duration"):
            self.record.slice(0, 2.1, ["C1"])

    def test_empty_time_window(self):
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            self.record.slice(1, 1, ["C1"])

    def test_two_records_remain_isolated_when_alternated(self):
        first = make_record(1.0, "memory://first")
        second = make_record(2.0, "memory://second")
        config = {"freq_bands": {}}

        first_before = compute_amplitude(first, ["C1"], 0, 1, config)
        second_result = compute_amplitude(second, ["C1"], 0, 1, config)
        first_after = compute_amplitude(first, ["C1"], 0, 1, config)

        self.assertEqual(first_before, first_after)
        self.assertEqual(first_before["C1"]["mean_abs"], "1.00e+00")
        self.assertEqual(second_result["C1"]["mean_abs"], "2.00e+00")


if __name__ == "__main__":
    unittest.main()
