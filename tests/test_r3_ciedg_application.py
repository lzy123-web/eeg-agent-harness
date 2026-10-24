"""Synthetic checks for the R3 application bridge, without private EEG input."""

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from eeg_harness.applications.r3.adapter import R3DatasetRules, R3_EEG_CHANNELS, R3_PROFILE
from eeg_harness.applications.r3.ciedg import load_application_config, run_r3_ciedg_record
from eeg_harness.applications.r3.ciedg_validation import (
    _manual_bandpower, _manual_epochs, _power_comparison, select_fixed_subset,
)
from eeg_harness.applications.r3.ciedg_cli import _private_destination, PRIVATE_OUTPUT_ROOT
from eeg_harness.events import EEGEvent, EventSet
from eeg_harness.pipeline import load_config
from eeg_harness.record import EEGRecord


ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config(ROOT / "config" / "baseline.json")
RULES = R3DatasetRules(("1", "2"), ("9",), "synthetic-only", (-0.2, 0.8), (-0.2, 0.0))


def synthetic_record():
    sfreq = 300.0
    times = np.arange(3600) / sfreq
    data = np.stack([
        (index + 1) * 1e-6 * np.sin(2 * np.pi * 10 * times)
        for index in range(len(R3_EEG_CHANNELS))
    ]).astype(np.float32)
    events = EventSet((
        EEGEvent("1", 1.0), EEGEvent("2", 3.0), EEGEvent("9", 5.0),
    ), "synthetic://issue24")
    return EEGRecord(
        data, sfreq, R3_EEG_CHANNELS, R3_PROFILE.reference, R3_PROFILE.montage,
        "synthetic://issue24", metadata={"profile_id": R3_PROFILE.profile_id},
        events=events,
    )


class R3CIEDGApplicationTest(unittest.TestCase):
    def test_two_tasks_run_through_existing_executor_without_selection(self):
        record = synthetic_record()
        outputs, contexts = run_r3_ciedg_record(record, CONFIG, RULES)
        self.assertEqual(set(outputs), {"event_summary", "quality_bandpower"})
        for task, output in outputs.items():
            self.assertEqual(output["status"], "completed", task)
            self.assertTrue(output["preflight"]["valid"])
            self.assertTrue(output["execution"]["evidence_check"]["closed"])
            self.assertNotIn(
                "select_quality_epochs",
                [item["tool_name"] for item in output["execution"]["tool_results"]],
            )
            self.assertIs(contexts[task].record, record)
        json.dumps(outputs, allow_nan=False)
        power = next(item["data"] for item in outputs["quality_bandpower"]["execution"]["tool_results"]
                     if item["tool_name"] == "event_bandpower")
        manual_data, manual_labels, rejected = _manual_epochs(record, RULES)
        self.assertEqual(rejected, 0)
        expected = _manual_bandpower(manual_data, manual_labels, record.sfreq,
                                     record.channel_names, CONFIG["freq_bands"])
        self.assertTrue(_power_comparison(power["conditions"], expected)[0])

    def test_missing_event_label_is_rejected_before_tools(self):
        rules = R3DatasetRules(("1", "8"), ("9",), "synthetic-only", (-0.2, 0.8), (-0.2, 0.0))
        outputs, contexts = run_r3_ciedg_record(synthetic_record(), CONFIG, rules,
                                                tasks=("event_summary",))
        self.assertNotEqual(outputs["event_summary"]["status"], "completed")
        self.assertEqual(contexts["event_summary"].history, [])

    def test_unsupported_task_is_explicit_and_does_not_execute(self):
        outputs, contexts = run_r3_ciedg_record(synthetic_record(), CONFIG, RULES,
                                                tasks=("diagnosis",))
        self.assertEqual(outputs["diagnosis"]["status"], "unsupported")
        self.assertFalse(contexts)

    def test_config_is_explicit_and_validated(self):
        rules, tasks = load_application_config(ROOT / "config" / "r3_ciedg.example.json")
        self.assertEqual(tasks, ("event_summary", "quality_bandpower"))
        self.assertEqual(rules.analysis_labels, tuple("12345678"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps({
                "analysis_labels": ["1"], "boundary_labels": ["1"],
                "boundary_rule_status": "unverified", "epoch_window": [-0.2, 0.8],
                "baseline": [-0.2, 0.0], "tasks": ["event_summary"],
            }), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_application_config(path)

    def test_subset_is_fixed_by_storage_order_not_outcome(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for partition in ("storage-b", "storage-a"):
                folder = root / partition
                folder.mkdir()
                for name in ("c.edf", "a.edf", "b.edf"):
                    (folder / name).touch()
            selected, inventory = select_fixed_subset(root)
            self.assertEqual([path.parent.name for path in selected],
                             ["storage-a", "storage-a", "storage-b", "storage-b"])
            self.assertEqual([path.name for path in selected], ["a.edf", "b.edf", "a.edf", "b.edf"])
            self.assertEqual(inventory["edf_count"], 6)

    def test_private_output_directory_enforced(self):
        with self.assertRaises(ValueError):
            _private_destination(ROOT / "docs" / "research" / "forbidden.json")
        self.assertEqual(_private_destination(PRIVATE_OUTPUT_ROOT / "local.json"),
                         (PRIVATE_OUTPUT_ROOT / "local.json").resolve())


if __name__ == "__main__":
    unittest.main()
