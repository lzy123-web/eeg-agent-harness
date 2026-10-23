import json
import unittest

from eeg_harness.context import ExecutionContext
from eeg_harness.executor import Executor
from eeg_harness.pipeline import load_config
from eeg_harness.profiles import EDF_NATIVE
from eeg_harness.research.evidence_phase import build_quality_selection_record
from eeg_harness.research.integrated_method.fake import Point1FakeLLM
from eeg_harness.research.integrated_method.transfer import ConstraintCarryingEEGAgentTransfer
from eeg_harness.research.integrated_method.transfer_diagnostics import (
    ExpireRereferencedArtifactBeforeBandpower,
    run_guarded_transfer_expert,
)
from eeg_harness.tools import build_default_registry

from tests.test_point1_transfer import REQUEST


CONFIG = load_config("config/baseline.json")


def make_context(task_id, fault=False):
    record, _ = build_quality_selection_record((1,))
    context = ExecutionContext(
        record, EDF_NATIVE, Executor(build_default_registry(), CONFIG), task_id,
    )
    if fault:
        context.executor = ExpireRereferencedArtifactBeforeBandpower(context.executor)
    return context


def expert(context):
    return run_guarded_transfer_expert(
        context, labels=("target",), tmin=0.0, tmax=1.0,
        reference_channels=("SYNTH-C2",), rereference_authorized=True,
    )


class TransferExpertFairnessTest(unittest.TestCase):
    def assert_science_equal(self, candidate, baseline):
        candidate_release = candidate.execution["release_results"]
        expert_release = baseline["release_results"]
        for tool_name in ("epoch_quality", "epoch_summary", "event_bandpower"):
            left = next(row["data"] for row in candidate_release if row["tool_name"] == tool_name)
            right = next(row["data"] for row in expert_release if row["tool_name"] == tool_name)
            if tool_name == "event_bandpower":
                self.assertEqual(left["conditions"], right["conditions"])
            elif tool_name == "epoch_summary":
                for key in ("shape", "sfreq", "reference", "valid_epoch_count"):
                    self.assertEqual(left[key], right[key])
            else:
                self.assertEqual(left["epoch_counts"], right["epoch_counts"])

    def test_no_fault_has_matched_science_and_budget(self):
        candidate = ConstraintCarryingEEGAgentTransfer(
            Point1FakeLLM(), make_context("candidate-normal"),
        ).run(REQUEST)
        baseline = expert(make_context("expert-normal"))
        self.assertEqual("completed", candidate.stop_reason)
        self.assertEqual("completed", baseline["status"])
        self.assertEqual(
            len(candidate.execution["tool_results"]), len(baseline["tool_results"]),
        )
        self.assert_science_equal(candidate, baseline)

    def test_fault_gives_both_methods_same_repair_and_provenance_rules(self):
        candidate = ConstraintCarryingEEGAgentTransfer(
            Point1FakeLLM(), make_context("candidate-fault", fault=True),
        ).run(REQUEST)
        baseline = expert(make_context("expert-fault", fault=True))
        self.assertEqual("completed", candidate.stop_reason)
        self.assertEqual("completed", baseline["status"])
        candidate_tools = [row["tool_name"] for row in candidate.execution["tool_results"]]
        expert_tools = [row["tool_name"] for row in baseline["tool_results"]]
        self.assertEqual(candidate_tools, expert_tools)
        self.assertEqual(1, baseline["repair_count"])
        self.assert_science_equal(candidate, baseline)
        for released in (candidate.execution["release_results"], baseline["release_results"]):
            summary = next(row for row in released if row["tool_name"] == "epoch_summary")
            self.assertEqual("semantic_evidence_reuse", summary["execution_kind"])
            self.assertEqual(
                baseline["effective_artifact_fingerprint"],
                summary["data"]["artifact_fingerprint"],
            )
        json.dumps(baseline, ensure_ascii=False, allow_nan=False)

    def test_expert_enforces_authorization_and_channel_requirements(self):
        denied = run_guarded_transfer_expert(
            make_context("expert-denied"), labels=("target",), tmin=0.0, tmax=1.0,
            reference_channels=("SYNTH-C2",), rereference_authorized=False,
        )
        self.assertEqual("REREFERENCE_NOT_AUTHORIZED", denied["reason"]["code"])
        missing = run_guarded_transfer_expert(
            make_context("expert-missing"), labels=("target",), tmin=0.0, tmax=1.0,
            reference_channels=(), rereference_authorized=True,
        )
        self.assertEqual("REFERENCE_CHANNELS_REQUIRED", missing["reason"]["code"])


if __name__ == "__main__":
    unittest.main()
