import json
import os
from pathlib import Path
import unittest

import numpy as np

from eeg_harness.context import ExecutionContext
from eeg_harness.edf import load_edf
from eeg_harness.executor import Executor
from eeg_harness.pipeline import load_config
from eeg_harness.profiles import EDF_NATIVE, TUEV_BIPOLAR_22
from eeg_harness.record import EEGRecord
from eeg_harness.tooling import ToolRequest
from eeg_harness.tools import build_default_registry
from eeg_harness.workflow import run_workflow


ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config(ROOT / "config" / "baseline.json")


def context_with(value, task_id):
    record = EEGRecord(
        data=np.full((1, 512), value, dtype=np.float32),
        sfreq=256,
        channel_names=("C1",),
        reference="native",
        montage="native",
        source=f"memory://{task_id}",
        metadata={"profile_id": "edf_native"},
    )
    return ExecutionContext(record, EDF_NATIVE, Executor(build_default_registry(), CONFIG), task_id)


class ExecutionContextTest(unittest.TestCase):
    def test_shared_executor_keeps_artifacts_request_scoped(self):
        shared = Executor(build_default_registry(), CONFIG)
        def make_event_record(source):
            import mne
            from eeg_harness.events import events_from_mne_raw

            sfreq = 64.0
            data = np.zeros((1, 256), dtype=np.float32)
            raw = mne.io.RawArray(data, mne.create_info(["C1"], sfreq, "eeg"), verbose=False)
            raw.set_annotations(mne.Annotations([1.0], [0], ["A"]))
            return EEGRecord(
                data=data,
                sfreq=sfreq,
                channel_names=("C1",),
                reference="native",
                montage="native",
                source=source,
                metadata={"profile_id": "edf_native"},
                events=events_from_mne_raw(raw, source),
            )

        first = ExecutionContext(make_event_record("memory://first"), EDF_NATIVE, shared, "first-events")
        second = ExecutionContext(make_event_record("memory://second"), EDF_NATIVE, shared, "second-events")
        arguments = {"labels": ["A"], "tmin": -0.25, "tmax": 0.75}
        first_created = first.execute(ToolRequest("create_epochs", arguments, "first-create"))
        second_created = second.execute(ToolRequest("create_epochs", arguments, "second-create"))
        first_id = first_created.data["artifact_id"]
        second_id = second_created.data["artifact_id"]

        self.assertTrue(first.execute(ToolRequest("epoch_summary", {"artifact_id": first_id})).success)
        self.assertTrue(second.execute(ToolRequest("epoch_summary", {"artifact_id": second_id})).success)
        cross = first.execute(ToolRequest("epoch_summary", {"artifact_id": second_id}))
        self.assertEqual(cross.error_code, "ARTIFACT_NOT_FOUND")
        self.assertNotIn("artifact_store", shared.resources)
    def test_contexts_are_isolated(self):
        first = context_with(1, "first")
        second = context_with(2, "second")
        request = ToolRequest("amplitude", {"channels": ["C1"], "start": 0, "end": 1})
        first_result = first.execute(request)
        second_result = second.execute(
            ToolRequest("amplitude", {"channels": ["C1"], "start": 0, "end": 1})
        )
        self.assertEqual(first_result.data["C1"]["mean_abs"], "1.00e+00")
        self.assertEqual(second_result.data["C1"]["mean_abs"], "2.00e+00")
        self.assertEqual(len(first.history), 1)
        self.assertEqual(len(second.history), 1)

    def test_previous_result_can_be_referenced(self):
        context = context_with(1, "references")
        info = context.execute(ToolRequest("record_info", {}, request_id="info"))
        self.assertTrue(info.success)
        result = context.execute(
            ToolRequest(
                "amplitude",
                {
                    "channels": [{"$result": "info", "path": ["channel_names", 0]}],
                    "start": 0,
                    "end": 1,
                },
            )
        )
        self.assertTrue(result.success, result.to_dict())

    def test_illegal_tool_does_not_prevent_recovery(self):
        context = context_with(1, "recovery")
        results = context.execute_many(
            [
                ToolRequest("does_not_exist", {}),
                ToolRequest("record_info", {}),
            ],
            continue_on_error=True,
        )
        self.assertFalse(results[0].success)
        self.assertTrue(results[1].success)
        self.assertEqual(context.trace.termination_reason, "completed_with_errors")

    def test_trace_and_bundle_are_json_serializable(self):
        context = context_with(1, "trace")
        context.execute_many(
            [
                ToolRequest("record_info", {}, request_id="one"),
                ToolRequest(
                    "psd",
                    {"channels": ["C1"], "start": 0, "end": 1},
                    request_id="two",
                ),
            ]
        )
        bundle = context.reproducibility_bundle()
        self.assertEqual(len(bundle["trace"]["events"]), 2)
        self.assertEqual(bundle["trace"]["termination_reason"], "completed")
        json.dumps(bundle, ensure_ascii=False, allow_nan=False)


@unittest.skipUnless(
    os.environ.get("EEG_HARNESS_TEST_EDF") and os.environ.get("EEG_HARNESS_MODEL_PATH"),
    "Set EEG_HARNESS_TEST_EDF and EEG_HARNESS_MODEL_PATH for workflow test",
)
class RealWorkflowTest(unittest.TestCase):
    def test_deterministic_multi_tool_workflow(self):
        bundle = run_workflow(
            os.environ["EEG_HARNESS_TEST_EDF"],
            TUEV_BIPOLAR_22,
            CONFIG,
            "FP1-F7",
            model_path=os.environ["EEG_HARNESS_MODEL_PATH"],
        )
        self.assertEqual([item["tool_name"] for item in bundle["results"]], [
            "record_info", "psd", "seizure_detection"
        ])
        self.assertTrue(all(item["success"] for item in bundle["results"]))
        self.assertEqual(bundle["trace"]["termination_reason"], "completed")
        json.dumps(bundle, ensure_ascii=False, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
