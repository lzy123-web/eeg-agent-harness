import json
import unittest

import numpy as np

from eeg_harness.context import ExecutionContext
from eeg_harness.executor import Executor
from eeg_harness.pipeline import load_config
from eeg_harness.profiles import EDF_NATIVE
from eeg_harness.planning import StateAwareConstrainedPlanner
from eeg_harness.research.evidence_phase import (
    build_quality_selection_record,
    oracle_epoch_data,
    oracle_event_bandpower,
)
from eeg_harness.research.integrated_method.fake import Point1FakeLLM
from eeg_harness.research.integrated_method.contracts import compile_intent
from eeg_harness.research.integrated_method.intent import IntentSpec
from eeg_harness.research.integrated_method.v1 import ConstraintCarryingEEGAgentV1
from eeg_harness.research.integrated_method.v1 import ResidualScientificPlanner
from eeg_harness.research.integrated_method.v1_evaluation import run_suite
from eeg_harness.tooling import ToolRequest, ToolResult
from eeg_harness.tools import build_default_registry


CONFIG = load_config("config/baseline.json")


def make_context(anomalous=(1,), task_id="point1-v1"):
    record, truth = build_quality_selection_record(anomalous)
    context = ExecutionContext(
        record, EDF_NATIVE, Executor(build_default_registry(), CONFIG), task_id,
    )
    return context, truth


def run_request(context):
    return ConstraintCarryingEEGAgentV1(Point1FakeLLM(), context).run(
        "检查 target 事件后 0 秒到 1 秒的质量，允许筛除异常试次，"
        "随后计算筛选后试次的绝对频带功率"
    )


class TransientBandpowerExecutor:
    """One declared transient fault; every non-fault call uses the real Executor."""

    def __init__(self, base):
        self.base = base
        self.registry = base.registry
        self.config = base.config
        self.resources = base.resources
        self.injected = False

    def execute(self, record, profile, request, session_resources=None):
        if request.name == "event_bandpower" and not self.injected:
            self.injected = True
            return ToolResult(
                request.request_id, request.name, False,
                error_code="INJECTED_TRANSIENT_FAILURE",
                error_message="declared deterministic research fault",
            )
        return self.base.execute(record, profile, request, session_resources)


class CCEPV1DynamicPlanningTest(unittest.TestCase):
    def test_quality_changes_branch_and_matches_independent_oracle(self):
        context, truth = make_context()
        result = run_request(context)
        self.assertEqual("completed", result.stop_reason)
        self.assertEqual("constraint_carrying_eeg_plan_v1_lrsp", result.method)
        execution = result.execution
        tools = [item["tool_name"] for item in execution["tool_results"]]
        self.assertEqual(
            ["list_events", "create_epochs", "epoch_quality",
             "select_quality_epochs", "event_bandpower"], tools,
        )
        state = execution["scientific_state"]
        self.assertEqual("derived", state["selection_mode"])
        selected = context.artifacts[state["artifacts"]["selected"]]
        expected = oracle_epoch_data(context.record, truth)
        np.testing.assert_allclose(selected.data, expected, rtol=0, atol=0)
        expected_power = oracle_event_bandpower(
            expected, context.record.sfreq, context.record.channel_names,
            CONFIG["freq_bands"],
        )
        actual = execution["tool_results"][-1]["data"]["conditions"][truth.label]
        self.assertEqual(2, actual["epoch_count"])
        for channel in context.record.channel_names:
            for band in CONFIG["freq_bands"]:
                self.assertAlmostEqual(
                    expected_power[channel][band], actual["channels"][channel][band],
                    places=18,
                )
        json.dumps(result.to_dict(), ensure_ascii=False, allow_nan=False)

    def test_clean_quality_uses_identity_transition_without_fake_artifact(self):
        context, _ = make_context(())
        result = run_request(context)
        self.assertEqual("completed", result.stop_reason)
        tools = [item["tool_name"] for item in result.execution["tool_results"]]
        self.assertEqual(
            ["list_events", "create_epochs", "epoch_quality", "event_bandpower"],
            tools,
        )
        state = result.execution["scientific_state"]
        self.assertEqual("identity", state["selection_mode"])
        self.assertIsNone(state["artifacts"]["selected"])
        self.assertEqual(state["artifacts"]["created"], state["artifacts"]["effective"])
        self.assertIn("未创建筛选派生数据", result.final_answer)
        self.assertIn("未临床校准", result.final_answer)

    def test_all_bad_stops_before_destructive_selection_and_analysis(self):
        context, _ = make_context((0, 1, 2))
        result = run_request(context)
        self.assertEqual("safe_stop_without_evidence", result.stop_reason)
        self.assertEqual("scientifically_blocked", result.execution["status"])
        self.assertEqual(
            "NO_USABLE_EPOCHS_FOR_CONDITION",
            result.execution["scientific_state"]["blocked"]["code"],
        )
        tools = [item["tool_name"] for item in result.execution["tool_results"]]
        self.assertEqual(["list_events", "create_epochs", "epoch_quality"], tools)

    def test_measure_without_selection_analyzes_original_artifact(self):
        context, _ = make_context()
        result = ConstraintCarryingEEGAgentV1(Point1FakeLLM(), context).run(
            "检查 target 事件后 0 秒到 1 秒的质量，不要筛选或剔除试次，"
            "随后计算未筛选试次的绝对频带功率"
        )
        self.assertEqual("completed", result.stop_reason)
        tools = [item["tool_name"] for item in result.execution["tool_results"]]
        self.assertEqual(
            ["list_events", "create_epochs", "epoch_quality", "event_bandpower"],
            tools,
        )
        self.assertIsNone(result.execution["scientific_state"]["selection_mode"])
        self.assertEqual(
            3,
            result.execution["tool_results"][-1]["data"]["conditions"]["target"]["epoch_count"],
        )

    def test_transient_frontier_retry_preserves_prior_completed_work(self):
        context, _ = make_context()
        context.executor = TransientBandpowerExecutor(context.executor)
        result = run_request(context)
        self.assertEqual("completed", result.stop_reason)
        tools = [item["tool_name"] for item in result.execution["tool_results"]]
        self.assertEqual(1, tools.count("list_events"))
        self.assertEqual(1, tools.count("create_epochs"))
        self.assertEqual(1, tools.count("epoch_quality"))
        self.assertEqual(1, tools.count("select_quality_epochs"))
        self.assertEqual(2, tools.count("event_bandpower"))
        self.assertEqual(1, result.execution["replans"])
        failed, recovered = result.execution["tool_results"][-2:]
        self.assertFalse(failed["success"])
        self.assertTrue(recovered["success"])
        self.assertEqual(
            failed["request_id"].split("-a")[0],
            recovered["request_id"].split("-a")[0],
        )

    def test_same_id_content_change_invalidates_quality_and_remeasures(self):
        context, _ = make_context()
        intent = IntentSpec(
            "event_workflow",
            ("epoch_quality", "trial_selection", "event_bandpower"),
            {
                "labels": ["target"], "tmin": 0.0, "tmax": 1.0,
                "selection_authorized": True,
            },
        )
        task, ledger = compile_intent(intent, context)
        initial = StateAwareConstrainedPlanner(context).plan(task)
        runner = ResidualScientificPlanner(context, task, ledger)
        for _ in range(3):
            action = runner.next_action()
            result = context.execute(ToolRequest(
                action.tool_name, action.arguments, runner._request_id(action),
            ))
            runner.results.append(result.to_dict())
            runner.apply_result(action, result.to_dict())
        old_evidence_id = runner.quality_result["data"]["evidence_id"]
        artifact = context.artifacts[runner.created_artifact_id]
        old_fingerprint = artifact.content_fingerprint()
        artifact.data[0, :, :] = 0.0
        self.assertNotEqual(old_fingerprint, artifact.content_fingerprint())
        action = runner.next_action()
        self.assertEqual("measure_quality", action.kind)
        self.assertIsNone(runner.selection_mode)
        self.assertTrue(any(
            item["event"] == "lineage_invalidated"
            and item["reason"] == "source_artifact_content_changed"
            for item in runner.transitions
        ))
        measured = context.execute(ToolRequest(
            action.tool_name, action.arguments, runner._request_id(action),
        ))
        self.assertTrue(measured.success)
        self.assertNotEqual(old_evidence_id, measured.data["evidence_id"])

    def test_selection_rejects_stale_quality_evidence_binding(self):
        context, _ = make_context()
        created = context.execute(ToolRequest(
            "create_epochs", {"labels": ["target"], "tmin": 0.0, "tmax": 1.0}, "create",
        ))
        quality = context.execute(ToolRequest(
            "epoch_quality", {"artifact_id": created.data["artifact_id"]}, "quality",
        ))
        result = context.execute(ToolRequest(
            "select_quality_epochs",
            {
                "artifact_id": created.data["artifact_id"],
                "expected_artifact_fingerprint": quality.data["artifact_fingerprint"],
                "expected_quality_evidence_id": "quality:deliberately-stale",
            },
            "stale-select",
        ))
        self.assertFalse(result.success)
        self.assertEqual("ARTIFACT_STATE_CONFLICT", result.error_code)
        self.assertIn("expected_quality_evidence_id", result.error_message)

    def test_two_dynamic_contexts_are_isolated(self):
        first, _ = make_context((1,), "v1-first")
        second, _ = make_context((), "v1-second")
        first_result = run_request(first)
        second_result = run_request(second)
        self.assertEqual("derived", first_result.execution["scientific_state"]["selection_mode"])
        self.assertEqual("identity", second_result.execution["scientific_state"]["selection_mode"])
        self.assertTrue(set(first.artifacts).isdisjoint(second.artifacts))

    def test_non_event_task_does_not_interpret_twice(self):
        context, _ = make_context()
        llm = Point1FakeLLM()
        result = ConstraintCarryingEEGAgentV1(llm, context).run(
            "计算 SYNTH-C1 从 0 秒到 1 秒的频带功率"
        )
        self.assertEqual("completed", result.stop_reason)
        self.assertEqual(2, llm.request_count)  # one intent call and one answer call

    def test_frozen_bounded_suite_is_json_serializable(self):
        report = run_suite(Point1FakeLLM())
        self.assertEqual("ccep-v1-bounded-integration-v1", report["protocol_id"])
        self.assertEqual(3, len(report["cases"]))
        self.assertTrue(all(
            item["result"]["stop_reason"] == "completed" for item in report["cases"]
        ))
        json.dumps(report, ensure_ascii=False, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
