import json
import unittest

import mne
import numpy as np

from eeg_harness.adaptive import EvidenceGoal, EvidencePolicy, EvidenceRequirement
from eeg_harness.context import ExecutionContext
from eeg_harness.events import events_from_mne_raw
from eeg_harness.executor import Executor
from eeg_harness.pipeline import load_config
from eeg_harness.profiles import EDF_NATIVE
from eeg_harness.record import EEGRecord
from eeg_harness.tools import build_default_registry


def context(flat_requested=False, bad_epoch=False):
    sfreq = 256
    time = np.arange(sfreq * 4) / sfreq
    clean = 20e-6 * np.sin(2 * np.pi * 10 * time)
    first = np.zeros_like(clean) if flat_requested else clean
    if bad_epoch:
        first[int(1.0 * sfreq):int(1.3 * sfreq)] = 500e-6
    data = np.vstack([first, clean]).astype(np.float32)
    raw = mne.io.RawArray(data, mne.create_info(["C1", "C2"], sfreq, "eeg"), verbose=False)
    raw.set_annotations(mne.Annotations([1.0, 2.0], [0, 0], ["A", "A"]))
    record = EEGRecord(
        data, sfreq, ("C1", "C2"), "native", "native", "synthetic://adaptive",
        metadata={"profile_id": "edf_native"},
        events=events_from_mne_raw(raw, "synthetic://adaptive"),
    )
    return ExecutionContext(record, EDF_NATIVE, Executor(build_default_registry(), load_config("config/baseline.json")))


class AdaptivePolicyTest(unittest.TestCase):
    def test_candidate_uses_only_explicit_clean_alternative(self):
        goal = EvidenceGoal(
            "window_psd", {"channels": ["C1"], "start": 0, "end": 1},
            legal_alternatives=({"channels": ["C2"], "start": 0, "end": 1},),
        )
        result = EvidencePolicy(context(flat_requested=True), "candidate").run(goal)
        self.assertEqual(result.status, "completed")
        self.assertTrue(result.evidence_satisfied)
        self.assertEqual(result.decision_trace[1]["selected_candidate_index"], 1)
        json.dumps(result.to_dict(), allow_nan=False)

    def test_no_authorized_alternative_returns_insufficient(self):
        goal = EvidenceGoal("window_psd", {"channels": ["C1"], "start": 0, "end": 1})
        result = EvidencePolicy(context(flat_requested=True), "candidate").run(goal)
        self.assertEqual(result.reason_code, "INSUFFICIENT_EVIDENCE")
        self.assertEqual(len(result.tool_results), 1)

    def test_fixed_and_candidate_receive_same_quality_evidence(self):
        goal = EvidenceGoal(
            "window_psd", {"channels": ["C1"], "start": 0, "end": 1},
            legal_alternatives=({"channels": ["C2"], "start": 0, "end": 1},),
        )
        fixed = EvidencePolicy(context(flat_requested=True), "fixed").run(goal)
        candidate = EvidencePolicy(context(flat_requested=True), "candidate").run(goal)
        self.assertEqual(
            fixed.tool_results[0]["data"]["channel_metrics"],
            candidate.tool_results[0]["data"]["channel_metrics"],
        )
        self.assertFalse(fixed.evidence_satisfied)
        self.assertTrue(candidate.evidence_satisfied)

    def test_event_policy_records_quality_selection_impact(self):
        goal = EvidenceGoal(
            "event_bandpower", {"labels": ["A"], "tmin": -0.1, "tmax": 0.9},
            requirement=EvidenceRequirement(min_usable_epochs_per_condition=1),
        )
        result = EvidencePolicy(context(bad_epoch=True), "candidate").run(goal)
        self.assertEqual(result.status, "completed")
        names = [item["tool_name"] for item in result.tool_results]
        self.assertIn("epoch_quality", names)
        self.assertIn("select_quality_epochs", names)


if __name__ == "__main__":
    unittest.main()
