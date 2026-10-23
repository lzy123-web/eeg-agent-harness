import json
import unittest

import numpy as np

from eeg_harness.context import ExecutionContext
from eeg_harness.executor import Executor
from eeg_harness.pipeline import load_config
from eeg_harness.profiles import EDF_NATIVE
from eeg_harness.research.evidence_phase import (
    build_quality_selection_record,
    oracle_epoch_data,
    oracle_event_bandpower,
)
from eeg_harness.tooling import ToolRequest
from eeg_harness.tools import build_default_registry


CONFIG = load_config("config/baseline.json")


def make_context(anomalous=(1,)):
    record, truth = build_quality_selection_record(anomalous)
    context = ExecutionContext(
        record, EDF_NATIVE, Executor(build_default_registry(), CONFIG), "evidence-phase"
    )
    return context, truth


class ActualEpochSelectionOracleTest(unittest.TestCase):
    def test_real_executor_selection_changes_data_count_and_bandpower(self):
        context, truth = make_context()
        created = context.execute(ToolRequest(
            "create_epochs",
            {"labels": [truth.label], "tmin": truth.tmin, "tmax": truth.tmax},
            "create",
        ))
        self.assertTrue(created.success)
        original_id = created.data["artifact_id"]
        original_copy = context.artifacts[original_id].data.copy()

        quality = context.execute(ToolRequest(
            "epoch_quality", {"artifact_id": original_id}, "quality"
        ))
        before = context.execute(ToolRequest(
            "event_bandpower", {"artifact_id": original_id}, "before"
        ))
        selected = context.execute(ToolRequest(
            "select_quality_epochs", {"artifact_id": original_id}, "select"
        ))
        self.assertTrue(all(item.success for item in (quality, before, selected)))
        selected_id = selected.data["artifact_id"]
        after = context.execute(ToolRequest(
            "event_bandpower", {"artifact_id": selected_id}, "after"
        ))
        self.assertTrue(after.success)

        self.assertEqual(list(truth.anomalous_epoch_indices), quality.data["flagged_epoch_indices"])
        self.assertEqual(3, selected.data["selection"]["input_epoch_count"])
        self.assertEqual(1, selected.data["selection"]["excluded_epoch_count"])
        self.assertEqual(2, selected.data["selection"]["output_epoch_count"])
        self.assertNotEqual(original_id, selected_id)
        np.testing.assert_array_equal(original_copy, context.artifacts[original_id].data)

        expected_selected = oracle_epoch_data(context.record, truth)
        np.testing.assert_allclose(
            context.artifacts[selected_id].data, expected_selected, rtol=0, atol=0
        )
        expected_before = oracle_event_bandpower(
            oracle_epoch_data(context.record, truth, range(3)),
            context.record.sfreq, context.record.channel_names, CONFIG["freq_bands"],
        )
        expected_after = oracle_event_bandpower(
            expected_selected, context.record.sfreq, context.record.channel_names,
            CONFIG["freq_bands"],
        )
        for channel in context.record.channel_names:
            for band in CONFIG["freq_bands"]:
                self.assertAlmostEqual(
                    expected_before[channel][band],
                    before.data["conditions"][truth.label]["channels"][channel][band],
                    places=18,
                )
                self.assertAlmostEqual(
                    expected_after[channel][band],
                    after.data["conditions"][truth.label]["channels"][channel][band],
                    places=18,
                )
        changed = [
            not np.isclose(expected_before[channel][band], expected_after[channel][band], rtol=1e-6, atol=1e-30)
            for channel in context.record.channel_names for band in CONFIG["freq_bands"]
        ]
        self.assertTrue(any(changed))
        self.assertEqual(3, before.data["conditions"][truth.label]["epoch_count"])
        self.assertEqual(2, after.data["conditions"][truth.label]["epoch_count"])
        json.dumps(context.reproducibility_bundle(), ensure_ascii=False, allow_nan=False)

    def test_all_flagged_epochs_stop_without_creating_derived_artifact(self):
        context, truth = make_context((0, 1, 2))
        created = context.execute(ToolRequest(
            "create_epochs",
            {"labels": [truth.label], "tmin": truth.tmin, "tmax": truth.tmax},
            "create",
        ))
        original_ids = set(context.artifacts)
        selected = context.execute(ToolRequest(
            "select_quality_epochs", {"artifact_id": created.data["artifact_id"]}, "select"
        ))
        self.assertFalse(selected.success)
        self.assertEqual("TOOL_EXECUTION_FAILED", selected.error_code)
        self.assertIn("No Epochs remain", selected.error_message)
        self.assertEqual(original_ids, set(context.artifacts))


if __name__ == "__main__":
    unittest.main()
