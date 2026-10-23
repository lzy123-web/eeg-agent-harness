import json
import unittest

import mne
import numpy as np

from eeg_harness.context import ExecutionContext
from eeg_harness.executor import Executor
from eeg_harness.pipeline import load_config
from eeg_harness.profiles import EDF_NATIVE, TUEV_BIPOLAR_22
from eeg_harness.research.evidence_phase import build_quality_selection_record
from eeg_harness.research.integrated_method.fake import Point1FakeLLM
from eeg_harness.research.integrated_method.transfer import (
    ConstraintCarryingEEGAgentTransfer,
)
from eeg_harness.tooling import ToolRequest
from eeg_harness.tools import build_default_registry


CONFIG = load_config("config/baseline.json")
REQUEST = (
    "对 target 事件后 0 秒到 1 秒的 Epoch，允许以 SYNTH-C2 作为参考通道重参考，"
    "检查转换后质量，汇总试次数并计算绝对频带功率"
)


def make_context(task_id="point1-transfer"):
    record, truth = build_quality_selection_record((1,))
    return ExecutionContext(
        record, EDF_NATIVE, Executor(build_default_registry(), CONFIG), task_id,
    ), truth


def execute(context, name, arguments, request_id):
    result = context.execute(ToolRequest(name, arguments, request_id=request_id))
    if not result.success:
        raise AssertionError(result.to_dict())
    return result.data


class ExpireRereferencedArtifactBeforeBandpower:
    def __init__(self, base):
        self.base = base
        self.registry = base.registry
        self.config = base.config
        self.resources = base.resources
        self.applied = False

    def execute(self, record, profile, request, session_resources=None):
        if request.name == "event_bandpower" and not self.applied:
            self.applied = True
            (session_resources or {}).get("artifact_store", {}).pop(
                request.arguments["artifact_id"], None,
            )
        return self.base.execute(record, profile, request, session_resources)


class EpochRereferenceToolTest(unittest.TestCase):
    def test_real_tool_matches_numpy_and_mne_oracles(self):
        context, _ = make_context("tool-oracle")
        execute(context, "list_events", {}, "events")
        created = execute(context, "create_epochs", {
            "labels": ["target"], "tmin": 0.0, "tmax": 1.0,
        }, "create")
        source = context.artifacts[created["artifact_id"]]
        transformed = execute(context, "rereference_epochs", {
            "artifact_id": source.artifact_id,
            "expected_artifact_fingerprint": source.content_fingerprint(),
            "reference_channels": ["SYNTH-C2"],
        }, "reref")
        derived = context.artifacts[transformed["artifact_id"]]

        numpy_oracle = source.data - source.data[:, [1], :]
        np.testing.assert_allclose(derived.data, numpy_oracle, rtol=0, atol=0)
        info = mne.create_info(
            list(source.channel_names), source.sfreq, ch_types="eeg", verbose=False,
        )
        mne_epochs = mne.EpochsArray(
            source.data.copy(), info, tmin=source.tmin, verbose=False,
        )
        mne_epochs.set_eeg_reference(
            ref_channels=["SYNTH-C2"], projection=False, verbose=False,
        )
        np.testing.assert_allclose(
            derived.data, mne_epochs.get_data(copy=True), rtol=0, atol=5e-11,
        )
        self.assertEqual(source.data.shape, derived.data.shape)
        self.assertEqual(source.sfreq, derived.sfreq)
        self.assertEqual(source.event_labels, derived.event_labels)
        self.assertEqual(source.event_onsets_seconds, derived.event_onsets_seconds)
        self.assertEqual("explicit average of SYNTH-C2", derived.reference)
        self.assertNotEqual(source.content_fingerprint(), derived.content_fingerprint())
        self.assertTrue(np.all(derived.data[:, 1, :] == 0))
        json.dumps(transformed, allow_nan=False)

    def test_missing_channel_and_profile_are_structured_rejections(self):
        context, _ = make_context("tool-negative")
        created = execute(context, "create_epochs", {
            "labels": ["target"], "tmin": 0.0, "tmax": 1.0,
        }, "create")
        missing = context.execute(ToolRequest("rereference_epochs", {
            "artifact_id": created["artifact_id"],
            "reference_channels": ["ABSENT"],
        }, request_id="missing"))
        self.assertFalse(missing.success)
        self.assertEqual("TOOL_EXECUTION_FAILED", missing.error_code)
        stale = context.execute(ToolRequest("rereference_epochs", {
            "artifact_id": created["artifact_id"],
            "expected_artifact_fingerprint": "sha256:stale",
            "reference_channels": ["SYNTH-C2"],
        }, request_id="stale"))
        self.assertFalse(stale.success)
        self.assertEqual("ARTIFACT_STATE_CONFLICT", stale.error_code)
        self.assertNotIn(
            "rereference_epochs",
            [spec.name for spec in build_default_registry().list_specs(
                TUEV_BIPOLAR_22.profile_id
            )],
        )


class CIEDGTransferAgentTest(unittest.TestCase):
    def test_end_to_end_reference_state_and_consumers(self):
        context, _ = make_context("agent-normal")
        result = ConstraintCarryingEEGAgentTransfer(Point1FakeLLM(), context).run(REQUEST)
        self.assertEqual("completed", result.stop_reason)
        self.assertEqual("constraint_carrying_eeg_plan_transfer_ciedg", result.method)
        tools = [item["tool_name"] for item in result.execution["tool_results"]]
        self.assertEqual([
            "list_events", "create_epochs", "rereference_epochs", "epoch_quality",
            "epoch_summary", "event_bandpower",
        ], tools)
        state = result.execution["scientific_state"]
        self.assertEqual("explicit average of SYNTH-C2", state[
            "reference_transition"
        ]["effective_reference"])
        effective_id = state["artifacts"]["effective"]
        for name in ("epoch_quality", "epoch_summary", "event_bandpower"):
            item = next(
                row for row in result.execution["tool_results"]
                if row["tool_name"] == name
            )
            self.assertEqual(effective_id, item["data"]["artifact_id"])
        self.assertTrue(result.execution["evidence_check"]["closed"])
        self.assertTrue(result.answer_check["valid"])

    def test_missing_authorization_or_reference_requires_clarification(self):
        context, _ = make_context("agent-no-auth")
        no_auth = ConstraintCarryingEEGAgentTransfer(Point1FakeLLM(), context).run(
            "对 target 事件后 0 秒到 1 秒的 Epoch，把 SYNTH-C2 记录为候选参考通道，"
            "评估重参考可能性并计算绝对频带功率"
        )
        self.assertEqual("clarification_required", no_auth.stop_reason)
        self.assertIn("rereference_authorized", no_auth.interpretation["missing_slots"])

        context, _ = make_context("agent-no-channel")
        no_channel = ConstraintCarryingEEGAgentTransfer(Point1FakeLLM(), context).run(
            "对 target 事件后 0 秒到 1 秒的 Epoch，允许重参考并计算绝对频带功率"
        )
        self.assertEqual("clarification_required", no_channel.stop_reason)
        self.assertIn("reference_channels", no_channel.interpretation["missing_slots"])

    def test_forbidden_transform_uses_source_and_mixed_scope_does_not_substitute(self):
        context, _ = make_context("agent-forbid")
        forbidden = ConstraintCarryingEEGAgentTransfer(Point1FakeLLM(), context).run(
            "检查 target 事件后 0 秒到 1 秒的质量，不要重参考，"
            "汇总原始试次数并计算绝对频带功率"
        )
        self.assertEqual("completed", forbidden.stop_reason)
        tools = [item["tool_name"] for item in forbidden.execution["tool_results"]]
        self.assertNotIn("rereference_epochs", tools)
        self.assertIsNone(forbidden.execution["scientific_state"][
            "reference_transition"
        ]["effective_reference"])

        context, _ = make_context("agent-mixed-scope")
        mixed = ConstraintCarryingEEGAgentTransfer(Point1FakeLLM(), context).run(
            "检查 target 事件后 0 秒到 1 秒在重参考前的质量，"
            "然后允许以 SYNTH-C2 作为参考通道重参考并计算重参考后的绝对频带功率"
        )
        self.assertEqual("clarification_required", mixed.stop_reason)
        self.assertIn("analysis_stage", mixed.interpretation["missing_slots"])
        self.assertIsNone(mixed.execution)

    def test_different_identity_same_content_reuses_summary_with_current_provenance(self):
        context, _ = make_context("agent-rebuild")
        context.executor = ExpireRereferencedArtifactBeforeBandpower(context.executor)
        result = ConstraintCarryingEEGAgentTransfer(Point1FakeLLM(), context).run(REQUEST)
        self.assertEqual("completed", result.stop_reason)
        execution = result.execution
        tools = [item["tool_name"] for item in execution["tool_results"]]
        self.assertEqual(1, tools.count("create_epochs"))
        self.assertEqual(2, tools.count("rereference_epochs"))
        self.assertEqual(2, tools.count("epoch_quality"))
        self.assertEqual(1, tools.count("epoch_summary"))
        self.assertEqual(2, tools.count("event_bandpower"))
        historical_summary = next(
            item for item in execution["tool_results"]
            if item["tool_name"] == "epoch_summary"
        )
        release_summary = next(
            item for item in execution["release_results"]
            if item["tool_name"] == "epoch_summary"
        )
        current_id = execution["scientific_state"]["artifacts"]["effective"]
        self.assertNotEqual(historical_summary["data"]["artifact_id"], current_id)
        self.assertEqual(current_id, release_summary["data"]["artifact_id"])
        self.assertEqual("semantic_evidence_reuse", release_summary["execution_kind"])
        self.assertEqual(
            historical_summary["request_id"], release_summary["reused_from_request_id"],
        )
        self.assertTrue(result.answer_check["valid"])
        cited_summary = next(
            item for item in result.answer_check["references"]
            if item["tool_name"] == "epoch_summary"
        )
        self.assertEqual(release_summary["request_id"], cited_summary["request_id"])
        self.assertTrue(any(
            item["event"] == "goal_evidence_reused"
            for item in execution["planning_trace"]
        ))


if __name__ == "__main__":
    unittest.main()
