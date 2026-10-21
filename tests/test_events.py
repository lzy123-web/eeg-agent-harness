import unittest

import mne
import numpy as np

from eeg_harness.edf import LoadedEDF, adapt_edf
from eeg_harness.events import EventError, EpochError, create_epoch_set, events_from_mne_raw
from eeg_harness.profiles import EDF_NATIVE
from eeg_harness.record import EEGRecord


def synthetic_record(events=True):
    sfreq = 10.0
    data = np.vstack([
        np.arange(100, dtype=np.float32),
        np.arange(100, dtype=np.float32) * 2,
    ])
    raw = mne.io.RawArray(data, mne.create_info(["C1", "C2"], sfreq, "eeg"), verbose=False)
    if events:
        raw.set_annotations(
            mne.Annotations(
                onset=[0.2, 2.0, 5.0, 9.8],
                duration=[0, 0, 0, 0],
                description=["edge", "target", "other", "target"],
            )
        )
    event_set = events_from_mne_raw(raw, "memory://events")
    return EEGRecord(
        data=data,
        sfreq=sfreq,
        channel_names=("C1", "C2"),
        reference="native",
        montage="native",
        source="memory://events",
        metadata={"profile_id": "edf_native"},
        events=event_set,
    )


class EventEpochTest(unittest.TestCase):
    def test_mne_annotations_preserve_relative_times(self):
        record = synthetic_record()
        self.assertEqual(record.events.labels, ("edge", "other", "target"))
        self.assertEqual([event.onset_seconds for event in record.events.events], [0.2, 2.0, 5.0, 9.8])

    def test_epoch_alignment_shape_and_boundary_rejection(self):
        epochs = create_epoch_set(synthetic_record(), "target", -0.5, 1.0)
        self.assertEqual(epochs.data.shape, (1, 2, 15))
        self.assertEqual(epochs.event_onsets_seconds, (2.0,))
        self.assertEqual(len(epochs.rejected), 1)
        self.assertEqual(epochs.rejected[0].reason, "OUT_OF_RECORD_BOUNDS")
        np.testing.assert_array_equal(epochs.data[0, 0], np.arange(15, 30, dtype=np.float32))

    def test_baseline_is_applied_inside_epoch(self):
        epochs = create_epoch_set(synthetic_record(), "target", -1.0, 1.0, baseline=(-1.0, 0.0))
        self.assertAlmostEqual(float(epochs.data[0, 0, :10].mean()), 0.0, places=6)

    def test_no_events_and_missing_label_are_explicit(self):
        with self.assertRaisesRegex(EventError, "no events"):
            create_epoch_set(synthetic_record(events=False), "target", 0, 1)
        with self.assertRaisesRegex(EventError, "No events match"):
            create_epoch_set(synthetic_record(), "missing", 0, 1)

    def test_invalid_baseline_and_zero_valid_trials_are_explicit(self):
        with self.assertRaisesRegex(EpochError, "inside the Epoch window"):
            create_epoch_set(synthetic_record(), "target", -0.5, 1, baseline=(-1, 0))
        with self.assertRaisesRegex(EpochError, "No valid Epochs"):
            create_epoch_set(synthetic_record(), "edge", -1, -0.5)

    def test_profile_adaptation_keeps_events_without_embedding_waveforms(self):
        raw = mne.io.RawArray(
            np.zeros((1, 20)), mne.create_info(["C1"], 10, "eeg"), verbose=False
        )
        raw.set_annotations(mne.Annotations([1.0], [0], ["stimulus"]))
        loaded = LoadedEDF(
            raw=raw,
            source="memory://loaded",
            metadata={"original_sfreq": 10.0},
            events=events_from_mne_raw(raw, "memory://loaded"),
        )
        record = adapt_edf(loaded, EDF_NATIVE, selected_channels=["C1"])
        self.assertEqual(record.events.summary()["labels"], {"stimulus": 1})


if __name__ == "__main__":
    unittest.main()
