import json
from pathlib import Path
import unittest

import mne
import numpy as np

from eeg_harness.context import ExecutionContext
from eeg_harness.event_workflow import run_event_workflow
from eeg_harness.events import events_from_mne_raw
from eeg_harness.executor import Executor
from eeg_harness.pipeline import load_config
from eeg_harness.profiles import EDF_NATIVE
from eeg_harness.record import EEGRecord
from eeg_harness.tooling import ToolRequest
from eeg_harness.tools import build_default_registry


ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config(ROOT / "config" / "baseline.json")


def event_record():
    sfreq = 64.0
    times = np.arange(0, 8, 1 / sfreq)
    data = np.vstack([
        np.sin(2 * np.pi * 10 * times),
        np.sin(2 * np.pi * 6 * times),
    ]).astype(np.float32)
    raw = mne.io.RawArray(data, mne.create_info(["C1", "C2"], sfreq, "eeg"), verbose=False)
    raw.set_annotations(mne.Annotations([1.0, 3.0, 7.8], [0, 0, 0], ["A", "A", "A"]))
    return EEGRecord(
        data=data,
        sfreq=sfreq,
        channel_names=("C1", "C2"),
        reference="native",
        montage="native",
        source="memory://event-tools",
        metadata={"profile_id": "edf_native"},
        events=events_from_mne_raw(raw, "memory://event-tools"),
    )


class EventToolTest(unittest.TestCase):
    def setUp(self):
        self.context = ExecutionContext(
            event_record(), EDF_NATIVE, Executor(build_default_registry(), CONFIG)
        )

    def test_event_tool_chain_keeps_waveforms_in_artifact_store(self):
        listed = self.context.execute(ToolRequest("list_events", {}, "list"))
        created = self.context.execute(ToolRequest(
            "create_epochs",
            {"labels": ["A"], "tmin": -0.25, "tmax": 0.75, "baseline": [-0.25, 0]},
            "create",
        ))
        artifact_id = created.data["artifact_id"]
        summary = self.context.execute(ToolRequest("epoch_summary", {"artifact_id": artifact_id}))
        power = self.context.execute(ToolRequest("event_bandpower", {"artifact_id": artifact_id}))
        self.assertEqual(listed.data["labels"], {"A": 3})
        self.assertEqual(created.data["valid_epoch_count"], 2)
        self.assertEqual(created.data["rejected_epoch_count"], 1)
        self.assertEqual(summary.data["shape"], [2, 2, 64])
        self.assertIn("alpha", power.data["conditions"]["A"]["channels"]["C1"])
        self.assertNotIn("data", created.data)
        self.assertEqual(self.context.artifacts[artifact_id].data.shape, (2, 2, 64))
        json.dumps([listed.to_dict(), created.to_dict(), summary.to_dict(), power.to_dict()], allow_nan=False)

    def test_invalid_artifact_and_no_events_are_structured(self):
        missing = self.context.execute(ToolRequest("epoch_summary", {"artifact_id": "missing"}))
        self.assertEqual(missing.error_code, "ARTIFACT_NOT_FOUND")
        record = event_record()
        record = EEGRecord(
            data=record.data,
            sfreq=record.sfreq,
            channel_names=record.channel_names,
            reference=record.reference,
            montage=record.montage,
            source=record.source,
            metadata=record.metadata,
        )
        context = ExecutionContext(record, EDF_NATIVE, Executor(build_default_registry(), CONFIG))
        result = context.execute(ToolRequest(
            "create_epochs", {"labels": ["A"], "tmin": 0, "tmax": 1}
        ))
        self.assertEqual(result.error_code, "EVENT_DATA_ERROR")

    def test_deterministic_event_workflow(self):
        bundle = run_event_workflow(
            event_record(), EDF_NATIVE, CONFIG, ["A"], -0.25, 0.75, (-0.25, 0)
        )
        self.assertEqual(len(bundle["results"]), 4)
        self.assertTrue(all(item["success"] for item in bundle["results"]))
        self.assertEqual(bundle["trace"]["termination_reason"], "completed")
        self.assertNotIn("data", bundle["artifacts"][0])
        json.dumps(bundle, ensure_ascii=False, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
