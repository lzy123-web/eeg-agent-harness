import json
import os
from pathlib import Path
import unittest

from eeg_harness.applications.r3.aggregation import (
    RecordFeature, aggregate_participants, public_group_description,
)
from eeg_harness.applications.r3.workflow import public_workflow_summary, run_r3_event_workflow
from eeg_harness.pipeline import load_config


ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config(ROOT / "config" / "baseline.json")


class ParticipantAggregationTest(unittest.TestCase):
    def test_records_are_averaged_within_participant_before_group(self):
        records = [
            RecordFeature("r1", "p1", {"alpha": 0.0}, "g1"),
            RecordFeature("r2", "p1", {"alpha": 2.0}, "g1"),
            RecordFeature("r3", "p2", {"alpha": 9.0}, "g1"),
            RecordFeature("r4", "p3", {"alpha": 5.0}, "g2"),
        ]
        participants = aggregate_participants(records)
        self.assertEqual(participants["p1"]["features"]["alpha"], 1.0)
        public = public_group_description(participants)
        self.assertEqual(public["groups"]["g1"]["feature_means"]["alpha"], 5.0)
        self.assertNotIn("p1", json.dumps(public))

    def test_group_description_requires_explicit_mapping(self):
        participants = aggregate_participants([
            RecordFeature("r1", "p1", {"alpha": 1.0})
        ])
        with self.assertRaisesRegex(ValueError, "Explicit participant-to-group"):
            public_group_description(participants)

    def test_duplicate_record_or_conflicting_group_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            aggregate_participants([
                RecordFeature("r", "p1", {"alpha": 1.0}, "g1"),
                RecordFeature("r", "p2", {"alpha": 2.0}, "g1"),
            ])
        with self.assertRaisesRegex(ValueError, "conflicting"):
            aggregate_participants([
                RecordFeature("r1", "p1", {"alpha": 1.0}, "g1"),
                RecordFeature("r2", "p1", {"alpha": 2.0}, "g2"),
            ])


@unittest.skipUnless(os.environ.get("EEG_HARNESS_R3_SAMPLE"), "Set EEG_HARNESS_R3_SAMPLE")
class RealR3WorkflowTest(unittest.TestCase):
    def test_real_file_uses_shared_runtime_and_public_summary_is_deidentified(self):
        bundle = run_r3_event_workflow(os.environ["EEG_HARNESS_R3_SAMPLE"], CONFIG)
        self.assertTrue(all(item["success"] for item in bundle["results"]))
        self.assertEqual(bundle["trace"]["termination_reason"], "completed")
        bandpower = next(
            item["data"] for item in bundle["results"]
            if item["tool_name"] == "event_bandpower"
        )
        self.assertIn("not baseline-normalized ERD/ERS", bandpower["interpretation"])
        public = public_workflow_summary(bundle)
        self.assertFalse(public["contains_record_level_features"])
        self.assertNotIn(str(Path(os.environ["EEG_HARNESS_R3_SAMPLE"])), json.dumps(public))
        json.dumps(bundle, ensure_ascii=False, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
