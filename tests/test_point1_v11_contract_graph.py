import json
import unittest
from dataclasses import replace

import numpy as np

from eeg_harness.context import ExecutionContext
from eeg_harness.executor import Executor
from eeg_harness.events import EEGEvent, EventSet
from eeg_harness.pipeline import load_config
from eeg_harness.profiles import EDF_NATIVE
from eeg_harness.research.evidence_phase import (
    build_quality_selection_record,
    oracle_epoch_data,
    oracle_event_bandpower,
)
from eeg_harness.research.integrated_method.fake import Point1FakeLLM
from eeg_harness.research.integrated_method.v11 import ConstraintCarryingEEGAgentV11
from eeg_harness.tools import build_default_registry


CONFIG = load_config("config/baseline.json")
REQUEST = (
    "检查 target 事件后 0 秒到 1 秒的质量，允许筛除异常试次，"
    "汇总筛选后的试次数，并计算筛选后试次的绝对频带功率"
)


def make_context(anomalous=(1,), task_id="point1-v11"):
    record, truth = build_quality_selection_record(anomalous)
    return ExecutionContext(
        record, EDF_NATIVE, Executor(build_default_registry(), CONFIG), task_id,
    ), truth


class ExpireEffectiveBeforeBandpower:
    """Remove only the requested effective artifact once at the tool boundary."""

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
                request.arguments["artifact_id"], None
            )
        return self.base.execute(record, profile, request, session_resources)


class ChangeRecordAndExpireArtifactsBeforeBandpower(ExpireEffectiveBeforeBandpower):
    """Force repair from changed source content so cached evidence is illegal."""

    def execute(self, record, profile, request, session_resources=None):
        if request.name == "event_bandpower" and not self.applied:
            self.applied = True
            record.data[0] += np.float32(1e-6)
            (session_resources or {}).get("artifact_store", {}).clear()
        return self.base.execute(record, profile, request, session_resources)


class LRSPV11ContractGraphTest(unittest.TestCase):
    def test_two_consumers_share_selected_artifact_and_match_oracles(self):
        context, truth = make_context()
        result = ConstraintCarryingEEGAgentV11(Point1FakeLLM(), context).run(REQUEST)
        self.assertEqual("completed", result.stop_reason)
        self.assertEqual("constraint_carrying_eeg_plan_v11_ciedg", result.method)
        tools = [item["tool_name"] for item in result.execution["tool_results"]]
        self.assertEqual(
            ["list_events", "create_epochs", "epoch_quality",
             "select_quality_epochs", "epoch_summary", "event_bandpower"],
            tools,
        )
        state = result.execution["scientific_state"]
        effective_id = state["artifacts"]["effective"]
        effective_fp = state["artifacts"]["effective_fingerprint"]
        summary = next(
            item["data"] for item in result.execution["tool_results"]
            if item["tool_name"] == "epoch_summary"
        )
        power = next(
            item["data"] for item in result.execution["tool_results"]
            if item["tool_name"] == "event_bandpower"
        )
        self.assertEqual((effective_id, effective_fp), (
            summary["artifact_id"], summary["artifact_fingerprint"],
        ))
        self.assertEqual((effective_id, effective_fp), (
            power["artifact_id"], power["artifact_fingerprint"],
        ))
        self.assertEqual(2, summary["valid_epoch_count"])
        expected_epochs = oracle_epoch_data(context.record, truth)
        np.testing.assert_allclose(
            context.artifacts[effective_id].data, expected_epochs, rtol=0, atol=0,
        )
        expected_power = oracle_event_bandpower(
            expected_epochs, context.record.sfreq, context.record.channel_names,
            CONFIG["freq_bands"],
        )
        actual = power["conditions"][truth.label]
        for channel in context.record.channel_names:
            for band in CONFIG["freq_bands"]:
                self.assertAlmostEqual(
                    expected_power[channel][band], actual["channels"][channel][band],
                    places=18,
                )
        dependencies = state["graph"]["dependencies"]
        self.assertEqual(["trial_selection"], dependencies["epoch_summary"])
        self.assertEqual(["trial_selection"], dependencies["event_bandpower"])
        json.dumps(result.to_dict(), ensure_ascii=False, allow_nan=False)

    def test_summary_and_power_use_original_when_selection_forbidden(self):
        context, _ = make_context()
        request = (
            "检查 target 事件后 0 秒到 1 秒的质量，不要筛选或剔除试次，"
            "汇总未筛选的试次数，并计算未筛选试次的绝对频带功率"
        )
        result = ConstraintCarryingEEGAgentV11(Point1FakeLLM(), context).run(request)
        self.assertEqual("completed", result.stop_reason)
        self.assertIsNone(result.execution["scientific_state"]["selection_mode"])
        tools = [item["tool_name"] for item in result.execution["tool_results"]]
        self.assertEqual(
            ["list_events", "create_epochs", "epoch_quality",
             "epoch_summary", "event_bandpower"], tools,
        )
        summary = result.execution["tool_results"][-2]["data"]
        power = result.execution["tool_results"][-1]["data"]
        self.assertEqual(3, summary["valid_epoch_count"])
        self.assertEqual(summary["artifact_id"], power["artifact_id"])

    def test_clean_identity_is_shared_by_both_consumers(self):
        context, _ = make_context(())
        result = ConstraintCarryingEEGAgentV11(Point1FakeLLM(), context).run(REQUEST)
        self.assertEqual("completed", result.stop_reason)
        state = result.execution["scientific_state"]
        self.assertEqual("identity", state["selection_mode"])
        self.assertEqual(state["artifacts"]["created"], state["artifacts"]["effective"])
        tools = [item["tool_name"] for item in result.execution["tool_results"]]
        self.assertNotIn("select_quality_epochs", tools)
        self.assertIn("epoch_summary", tools)
        self.assertIn("event_bandpower", tools)

    def test_content_equivalent_repair_reuses_completed_summary(self):
        context, _ = make_context()
        context.executor = ExpireEffectiveBeforeBandpower(context.executor)
        result = ConstraintCarryingEEGAgentV11(Point1FakeLLM(), context).run(REQUEST)
        self.assertEqual("completed", result.stop_reason)
        tools = [item["tool_name"] for item in result.execution["tool_results"]]
        self.assertEqual(1, tools.count("create_epochs"))
        self.assertEqual(1, tools.count("epoch_quality"))
        self.assertEqual(2, tools.count("select_quality_epochs"))
        self.assertEqual(1, tools.count("epoch_summary"))
        self.assertEqual(2, tools.count("event_bandpower"))
        self.assertEqual(1, result.execution["scientific_state"]["repairs"])
        self.assertTrue(any(
            item["event"] == "evidence_graph_invalidated"
            for item in result.execution["planning_trace"]
        ))
        self.assertTrue(any(
            item["event"] == "goal_evidence_reused"
            for item in result.execution["planning_trace"]
        ))

    def test_changed_content_does_not_reuse_cached_summary(self):
        context, _ = make_context()
        context.executor = ChangeRecordAndExpireArtifactsBeforeBandpower(context.executor)
        result = ConstraintCarryingEEGAgentV11(Point1FakeLLM(), context).run(REQUEST)
        self.assertEqual("completed", result.stop_reason)
        tools = [item["tool_name"] for item in result.execution["tool_results"]]
        self.assertEqual(2, tools.count("create_epochs"))
        self.assertEqual(2, tools.count("epoch_summary"))
        self.assertFalse(any(
            item["event"] == "goal_evidence_reused"
            for item in result.execution["planning_trace"]
        ))

    def test_one_requested_condition_without_usable_epochs_stops_all_consumers(self):
        record, _ = build_quality_selection_record((1,))
        labels = ("target", "control", "target")
        events = EventSet(tuple(
            EEGEvent(label, event.onset_seconds, source_index=event.source_index)
            for label, event in zip(labels, record.events.events)
        ), source=record.events.source)
        record = replace(record, events=events)
        context = ExecutionContext(
            record, EDF_NATIVE, Executor(build_default_registry(), CONFIG),
            "point1-v11-multicondition",
        )
        request = (
            "检查 target 和 control 事件后 0 秒到 1 秒的质量，允许筛除异常试次，"
            "汇总筛选后的试次数，并计算筛选后试次的绝对频带功率"
        )
        result = ConstraintCarryingEEGAgentV11(Point1FakeLLM(), context).run(request)
        state = result.execution["scientific_state"]
        self.assertEqual("NO_USABLE_EPOCHS_FOR_CONDITION", state["blocked"]["code"])
        self.assertEqual(["control"], state["blocked"]["labels"])
        tools = [item["tool_name"] for item in result.execution["tool_results"]]
        self.assertEqual(["list_events", "create_epochs", "epoch_quality"], tools)
        self.assertNotEqual("completed", result.stop_reason)


if __name__ == "__main__":
    unittest.main()
