import json
import unittest

import mne
import numpy as np

from eeg_harness.context import ExecutionContext
from eeg_harness.events import events_from_mne_raw
from eeg_harness.executor import Executor
from eeg_harness.pipeline import load_config
from eeg_harness.planning import EEGStateSnapshot, TaskSpec, build_operation_contracts
from eeg_harness.profiles import EDF_NATIVE
from eeg_harness.record import EEGRecord
from eeg_harness.tooling import ToolRequest
from eeg_harness.tools import build_default_registry


CONFIG = load_config("config/baseline.json")


def planning_context(task_id="planning-state"):
    data = np.zeros((2, 256), dtype=np.float32)
    raw = mne.io.RawArray(data, mne.create_info(["C1", "C2"], 128, "eeg"), verbose=False)
    raw.set_annotations(mne.Annotations([0.5], [0], ["A"]))
    record = EEGRecord(
        data=data,
        sfreq=128,
        channel_names=("C1", "C2"),
        reference="native",
        montage="native",
        source="synthetic://planning-state",
        metadata={"profile_id": "edf_native"},
        events=events_from_mne_raw(raw, "synthetic://planning-state"),
    )
    return ExecutionContext(record, EDF_NATIVE, Executor(build_default_registry(), CONFIG), task_id)


class PlanningModelTest(unittest.TestCase):
    def test_contracts_cover_current_ten_tools_without_loading_model(self):
        registry = build_default_registry()
        contracts = build_operation_contracts(registry)
        self.assertEqual(len(contracts), 10)
        self.assertEqual(contracts["create_epochs"].produces_artifact, "epochs")
        self.assertEqual(contracts["event_bandpower"].consumes_artifact, "epochs")
        self.assertEqual(contracts["epoch_summary"].consumes_artifact, "epochs")
        self.assertEqual(contracts["list_events"].observes_state, ("events",))
        self.assertEqual(
            contracts["event_bandpower"].preconditions["min_artifact_duration_seconds"],
            1.0,
        )
        self.assertEqual(contracts["seizure_detection"].required_resources, ("seizure_model",))

    def test_snapshot_contains_verified_facts_but_no_raw_array(self):
        snapshot = EEGStateSnapshot.from_context(planning_context())
        payload = snapshot.to_dict()
        self.assertEqual(payload["event_labels"], {"A": 1})
        self.assertEqual(payload["verified_quality_facts"], [])
        rendered = json.dumps(payload, allow_nan=False)
        self.assertNotIn("data", payload)
        self.assertNotIn("[[", rendered)

    def test_artifact_snapshot_is_bound_to_context_profile_and_record(self):
        context = planning_context("owner")
        created = context.execute(ToolRequest(
            "create_epochs", {"labels": ["A"], "tmin": -0.25, "tmax": 0.75}
        ))
        artifact = EEGStateSnapshot.from_context(context).artifact(created.data["artifact_id"])
        self.assertEqual(artifact.context_id, "owner")
        self.assertEqual(artifact.profile_id, "edf_native")
        self.assertEqual(artifact.artifact_type, "epochs")

    def test_task_spec_is_structured_and_serializable(self):
        task = TaskSpec("tool", {"tool_name": "psd", "channels": ["C1"]}, task_id="x")
        json.dumps(task.to_dict(), allow_nan=False)


if __name__ == "__main__":
    unittest.main()
