import json
import os
from pathlib import Path
import unittest

import numpy as np

from eeg_harness.edf import load_edf
from eeg_harness.executor import Executor
from eeg_harness.legacy.seizure import load_seizure_model
from eeg_harness.pipeline import load_config
from eeg_harness.profiles import EDF_NATIVE, TUEV_BIPOLAR_22
from eeg_harness.record import EEGRecord
from eeg_harness.tooling import ToolRequest
from eeg_harness.tools import build_default_registry


ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config(ROOT / "config" / "baseline.json")


def native_record():
    return EEGRecord(
        data=np.ones((2, 512), dtype=np.float32),
        sfreq=256.0,
        channel_names=("C1", "C2"),
        reference="native",
        montage="native",
        source="memory://executor",
        metadata={"profile_id": "edf_native"},
    )


class RegistryExecutorTest(unittest.TestCase):
    def setUp(self):
        self.registry = build_default_registry()
        self.executor = Executor(self.registry, CONFIG)
        self.record = native_record()

    def test_registry_lists_profile_tools_without_model_resource(self):
        load_seizure_model.cache_clear()
        names = [spec.name for spec in self.registry.list_specs("edf_native")]
        self.assertEqual(names, [
            "record_info", "amplitude", "psd", "list_events",
            "create_epochs", "epoch_summary", "event_bandpower",
            "record_quality", "epoch_quality", "select_quality_epochs",
        ])
        definitions = self.registry.public_definitions("tuev_bipolar_22")
        self.assertEqual(len(definitions), 11)
        self.assertEqual(load_seizure_model.cache_info().misses, 0)
        json.dumps(definitions, allow_nan=False)

    def test_basic_tools_execute_and_serialize(self):
        requests = [
            ToolRequest("record_info", {}),
            ToolRequest("amplitude", {"channels": ["C1"], "start": 0, "end": 1}),
            ToolRequest("psd", {"channels": ["C1"], "start": 0, "end": 1}),
        ]
        for request in requests:
            result = self.executor.execute(self.record, EDF_NATIVE, request)
            self.assertTrue(result.success, result.to_dict())
            json.dumps(result.to_dict(), allow_nan=False)

    def test_unknown_tool_is_structured_error(self):
        result = self.executor.execute(self.record, EDF_NATIVE, ToolRequest("missing", {}))
        self.assertEqual(result.error_code, "TOOL_NOT_FOUND")
        self.assertNotIn("Traceback", result.error_message)

    def test_invalid_channel_and_window_are_structured_errors(self):
        bad_channel = ToolRequest(
            "amplitude", {"channels": ["missing"], "start": 0, "end": 1}
        )
        out_of_range = ToolRequest(
            "psd", {"channels": ["C1"], "start": 0, "end": 3}
        )
        self.assertEqual(
            self.executor.execute(self.record, EDF_NATIVE, bad_channel).error_code,
            "INVALID_CHANNEL",
        )
        self.assertEqual(
            self.executor.execute(self.record, EDF_NATIVE, out_of_range).error_code,
            "INVALID_WINDOW",
        )

    def test_schema_boundaries_are_structured_errors(self):
        cases = [
            {"channels": [1], "start": 0, "end": 1},
            {"channels": ["C1"], "start": float("nan"), "end": 1},
            {"channels": ["C1"], "start": 1, "end": 1},
            {"channels": ["C1"], "start": 0, "end": 1, "unexpected": True},
        ]
        expected = ["INVALID_ARGUMENT", "INVALID_ARGUMENT", "INVALID_WINDOW", "INVALID_ARGUMENT"]
        actual = [
            self.executor.execute(self.record, EDF_NATIVE, ToolRequest("amplitude", args)).error_code
            for args in cases
        ]
        self.assertEqual(actual, expected)

    def test_record_and_declared_profile_mismatch_is_rejected(self):
        mismatched = EEGRecord(
            data=self.record.data,
            sfreq=self.record.sfreq,
            channel_names=self.record.channel_names,
            reference=self.record.reference,
            montage=self.record.montage,
            source=self.record.source,
            metadata={"profile_id": "another_profile"},
        )
        result = self.executor.execute(
            mismatched, EDF_NATIVE, ToolRequest("record_info", {})
        )
        self.assertEqual(result.error_code, "INCOMPATIBLE_PROFILE")

    def test_profile_incompatibility_precedes_model_resource_check(self):
        request = ToolRequest(
            "seizure_detection", {"channels": ["C1"], "start": 0, "end": 1}
        )
        result = self.executor.execute(self.record, EDF_NATIVE, request)
        self.assertEqual(result.error_code, "INCOMPATIBLE_PROFILE")

    def test_missing_model_is_structured_error(self):
        record = EEGRecord(
            data=np.zeros((22, 256), dtype=np.float32),
            sfreq=256,
            channel_names=TUEV_BIPOLAR_22.required_channels,
            reference=TUEV_BIPOLAR_22.reference,
            montage=TUEV_BIPOLAR_22.montage,
            source="memory://model",
            metadata={"profile_id": TUEV_BIPOLAR_22.profile_id},
        )
        result = self.executor.execute(
            record,
            TUEV_BIPOLAR_22,
            ToolRequest(
                "seizure_detection",
                {"channels": ["FP1-F7"], "start": 0, "end": 1},
            ),
        )
        self.assertEqual(result.error_code, "MODEL_RESOURCE_MISSING")


@unittest.skipUnless(
    os.environ.get("EEG_HARNESS_TEST_EDF") and os.environ.get("EEG_HARNESS_MODEL_PATH"),
    "Set EEG_HARNESS_TEST_EDF and EEG_HARNESS_MODEL_PATH for executor model test",
)
class RealExecutorModelTest(unittest.TestCase):
    def test_model_tool_runs_through_executor(self):
        record = load_edf(os.environ["EEG_HARNESS_TEST_EDF"], TUEV_BIPOLAR_22)
        executor = Executor(
            build_default_registry(),
            CONFIG,
            resources={"seizure_model": os.environ["EEG_HARNESS_MODEL_PATH"]},
        )
        result = executor.execute(
            record,
            TUEV_BIPOLAR_22,
            ToolRequest(
                "seizure_detection",
                {"channels": ["FP1-F7"], "start": 0, "end": 1},
            ),
        )
        self.assertTrue(result.success, result.to_dict())
        self.assertEqual(result.data[0]["FP1-F7"], {"Non-seiz": 0.0, "seiz": 1.0})
        json.dumps(result.to_dict(), allow_nan=False)


if __name__ == "__main__":
    unittest.main()
