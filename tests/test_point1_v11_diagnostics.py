import json
import unittest

from eeg_harness.context import ExecutionContext
from eeg_harness.executor import Executor
from eeg_harness.pipeline import load_config
from eeg_harness.profiles import EDF_NATIVE
from eeg_harness.research.evidence_phase import build_quality_selection_record
from eeg_harness.research.integrated_method.fake import Point1FakeLLM
from eeg_harness.research.integrated_method.v11 import ConstraintCarryingEEGAgentV11
from eeg_harness.research.integrated_method.v11_diagnostics import (
    benchmark_epoch_fingerprint,
    run_guarded_epoch_expert,
)
from eeg_harness.tools import build_default_registry


CONFIG = load_config("config/baseline.json")
REQUEST = (
    "检查 target 事件后 0 秒到 1 秒的质量，允许筛除异常试次，"
    "汇总筛选后的试次数，并计算筛选后试次的绝对频带功率"
)


def make_context(task_id):
    record, _ = build_quality_selection_record((1,))
    return ExecutionContext(
        record, EDF_NATIVE, Executor(build_default_registry(), CONFIG), task_id,
    )


class LRSPV11DiagnosticsTest(unittest.TestCase):
    def test_no_fault_candidate_and_strong_expert_have_matched_scientific_outputs(self):
        candidate = ConstraintCarryingEEGAgentV11(
            Point1FakeLLM(), make_context("candidate"),
        ).run(REQUEST)
        expert = run_guarded_epoch_expert(
            make_context("expert"), labels=("target",), tmin=0.0, tmax=1.0,
            objectives=(
                "epoch_quality", "trial_selection", "epoch_summary", "event_bandpower",
            ), selection_authorized=True,
        )
        self.assertEqual("completed", candidate.stop_reason)
        self.assertEqual("completed", expert["status"])
        candidate_tools = candidate.execution["tool_results"]
        self.assertEqual(len(candidate_tools), len(expert["tool_results"]))
        candidate_summary = next(
            item["data"] for item in candidate_tools
            if item["tool_name"] == "epoch_summary"
        )
        expert_summary = next(
            item["data"] for item in expert["tool_results"]
            if item["tool_name"] == "epoch_summary"
        )
        for field in (
            "valid_epoch_count", "shape", "channel_names", "sfreq", "tmin", "tmax",
            "event_labels", "event_onsets_seconds",
        ):
            self.assertEqual(candidate_summary[field], expert_summary[field])
        candidate_power = next(
            item["data"] for item in candidate_tools
            if item["tool_name"] == "event_bandpower"
        )
        expert_power = next(
            item["data"] for item in expert["tool_results"]
            if item["tool_name"] == "event_bandpower"
        )
        self.assertEqual(candidate_power["conditions"], expert_power["conditions"])

    def test_fingerprint_benchmark_is_deterministic_and_serializable(self):
        report = benchmark_epoch_fingerprint(shapes=((3, 2, 128),), repeats=3)
        self.assertTrue(report[0]["deterministic"])
        self.assertGreater(report[0]["bytes"], 0)
        self.assertGreaterEqual(report[0]["median_ms"], 0.0)
        json.dumps(report, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
