import json
from pathlib import Path
import tempfile
import unittest

from eeg_harness.agent_cli import main as agent_main
from eeg_harness.context import ExecutionContext
from eeg_harness.demo import build_synthetic_event_record
from eeg_harness.executor import Executor
from eeg_harness.evaluation_faults import FaultInjectingExecutor
from eeg_harness.pipeline import load_config
from eeg_harness.profiles import EDF_NATIVE
from eeg_harness.research.integrated_method.agent import ConstraintCarryingEEGAgent
from eeg_harness.research.integrated_method.fake import Point1FakeLLM
from eeg_harness.research.integrated_method.intent import INTENT_TOOL
from eeg_harness.tools import build_default_registry
from eeg_harness.record import EEGRecord


CONFIG = load_config("config/baseline.json")


def make_context(task_id="point1-test"):
    return ExecutionContext(
        build_synthetic_event_record(), EDF_NATIVE,
        Executor(build_default_registry(), CONFIG, {}), task_id,
    )


class ScriptedIntentLLM:
    model = "scripted-intent-double"

    def __init__(self, payload):
        self.payload = payload
        self.request_count = 0
        self.total_usage = {}
        self.finish_reasons = []

    def complete(self, messages, tools, tool_choice="auto"):
        self.request_count += 1
        self.finish_reasons.append("tool_calls" if tools else "stop")
        if not tools:
            return {"role": "assistant", "content": "已依据闭合证据回答。"}
        return {
            "role": "assistant", "content": None,
            "tool_calls": [{
                "id": "scripted-intent", "type": "function",
                "function": {
                    "name": "submit_eeg_intent",
                    "arguments": json.dumps(self.payload, ensure_ascii=False),
                },
            }],
        }


class Point1IntentSchemaTest(unittest.TestCase):
    def test_schema_exposes_only_canonical_scientific_slots(self):
        schema = INTENT_TOOL[0]["function"]["parameters"]["properties"]["parameters"]
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            set(schema["properties"]),
            {"channels", "start", "end", "labels", "tmin", "tmax", "selection_authorized"},
        )


def intent_payload(analysis, parameters, evidence, **overrides):
    payload = {
        "analysis_type": analysis, "parameters": parameters,
        "explicit_evidence": evidence, "unknown_slots": [],
        "forbidden_operations": [], "source_stage": "current",
        "output_boundary": "research_only", "rationale": "test",
    }
    payload.update(overrides)
    return payload


class Point1IntegratedAgentTest(unittest.TestCase):
    def test_explicit_psd_runs_planner_executor_and_closes_evidence(self):
        context = make_context()
        result = ConstraintCarryingEEGAgent(Point1FakeLLM(), context).run(
            "计算 SYNTH-C1 从 1 秒到 3 秒的绝对频带功率"
        )
        self.assertEqual("completed", result.stop_reason)
        self.assertTrue(result.plan_check["valid"])
        self.assertTrue(result.evidence_check["closed"])
        self.assertEqual(["psd"], result.evidence_check["successful_tools"])
        event = result.execution["execution_trace"]["events"][0]
        self.assertEqual({"channels": ["SYNTH-C1"], "start": 1.0, "end": 3.0}, event["arguments"])
        json.dumps(result.to_dict(), ensure_ascii=False, allow_nan=False)

    def test_cli_point1_is_opt_in_and_serializable(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "point1.json"
            code = agent_main([
                "--demo-synthetic", "--fake", "--agent-mode", "point1",
                "--request", "计算 SYNTH-C2 从 0 秒到 2 秒的绝对频带功率",
                "--output", str(output),
            ])
            self.assertEqual(0, code)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("constraint_carrying_eeg_plan_v0", payload["method"])
            self.assertEqual("completed", payload["stop_reason"])

    def test_event_chain_uses_real_artifact_lineage(self):
        result = ConstraintCarryingEEGAgent(Point1FakeLLM(), make_context()).run(
            "计算 stimulus 事件前 -0.2 秒到后 0.8 秒的绝对频带功率"
        )
        self.assertEqual("completed", result.stop_reason)
        self.assertEqual(
            ["list_events", "create_epochs", "event_bandpower"],
            result.evidence_check["successful_tools"],
        )
        self.assertTrue(result.evidence_check["closed"])

    def test_missing_event_label_requires_clarification_without_tools(self):
        context = make_context()
        result = ConstraintCarryingEEGAgent(Point1FakeLLM(), context).run(
            "计算某个事件条件前 -0.2 秒到后 0.8 秒的绝对频带功率"
        )
        self.assertEqual("clarification_required", result.stop_reason)
        self.assertIn("labels", result.interpretation["missing_slots"])
        self.assertEqual([], context.trace.to_dict()["events"])

    def test_guessed_record_label_without_user_span_is_blocked(self):
        request = "计算某个事件条件前 -0.2 秒到后 0.8 秒的绝对频带功率"
        payload = intent_payload(
            "event_bandpower",
            {"labels": ["stimulus"], "tmin": -0.2, "tmax": 0.8},
            {"analysis_type": "频带功率", "labels": "某个事件条件", "tmin": request, "tmax": request},
        )
        result = ConstraintCarryingEEGAgent(ScriptedIntentLLM(payload), make_context()).run(request)
        self.assertEqual("clarification_required", result.stop_reason)
        self.assertIn("labels", result.interpretation["missing_slots"])

    def test_short_epoch_and_unknown_label_are_rejected_before_execution(self):
        short_request = "计算 stimulus 事件前 -0.1 秒到后 0.5 秒的绝对频带功率"
        short = intent_payload(
            "event_bandpower", {"labels": ["stimulus"], "tmin": -0.1, "tmax": 0.5},
            {"analysis_type": "频带功率", "labels": "stimulus", "tmin": short_request, "tmax": short_request},
        )
        result = ConstraintCarryingEEGAgent(ScriptedIntentLLM(short), make_context()).run(short_request)
        self.assertEqual("plan_rejected", result.stop_reason)
        self.assertEqual([], result.execution or [])

        missing_request = "计算 target 事件前 -0.2 秒到后 0.8 秒的绝对频带功率"
        missing = intent_payload(
            "event_bandpower", {"labels": ["target"], "tmin": -0.2, "tmax": 0.8},
            {"analysis_type": "频带功率", "labels": "target", "tmin": missing_request, "tmax": missing_request},
        )
        result = ConstraintCarryingEEGAgent(ScriptedIntentLLM(missing), make_context()).run(missing_request)
        self.assertEqual("plan_rejected", result.stop_reason)

    def test_processed_only_record_rejects_raw_source_evidence(self):
        base = build_synthetic_event_record()
        record = EEGRecord(
            base.data.copy(), base.sfreq, base.channel_names,
            "processed-only", base.montage, "synthetic://processed-only",
            processing_metadata=base.processing_metadata + ({"operation": "notch_filter", "frequency": 50.0},),
            metadata={**dict(base.metadata), "source_stage": "processed_only"}, events=base.events,
        )
        context = ExecutionContext(
            record, EDF_NATIVE, Executor(build_default_registry(), CONFIG, {}), "processed-only"
        )
        request = "检查原始信号的质量证据"
        payload = intent_payload(
            "record_quality", {}, {"analysis_type": "质量证据", "source_stage": "原始信号"},
            source_stage="raw",
        )
        result = ConstraintCarryingEEGAgent(ScriptedIntentLLM(payload), context).run(request)
        self.assertEqual("unsupported_or_unobservable", result.stop_reason)
        self.assertEqual([], context.trace.to_dict()["events"])

    def test_quality_selection_measures_before_authorized_selection(self):
        request = "请对 stimulus 事件前 -0.2 秒到后 0.8 秒先检查质量并允许筛选异常试次"
        payload = intent_payload(
            "quality_selection",
            {"labels": ["stimulus"], "tmin": -0.2, "tmax": 0.8, "selection_authorized": True},
            {"analysis_type": "检查质量", "labels": "stimulus", "tmin": request, "tmax": request, "selection_authorized": "允许筛选异常试次"},
        )
        result = ConstraintCarryingEEGAgent(ScriptedIntentLLM(payload), make_context()).run(request)
        self.assertEqual("completed", result.stop_reason)
        self.assertEqual(
            ["list_events", "create_epochs", "epoch_quality", "select_quality_epochs"],
            result.evidence_check["successful_tools"],
        )

    def test_transient_failure_replans_once_without_changing_obligations(self):
        context = make_context()
        context.executor = FaultInjectingExecutor(context.executor, "transient_tool_failure")
        result = ConstraintCarryingEEGAgent(Point1FakeLLM(), context, max_replans=1).run(
            "计算 SYNTH-C1 从 0 秒到 1 秒的幅值"
        )
        self.assertEqual("completed", result.stop_reason)
        self.assertEqual(1, result.execution["replans"])
        replans = [item for item in result.execution["planning_trace"] if item["event"] == "replanned"]
        self.assertEqual([True], [item["obligations_valid"] for item in replans])
        args = [event["arguments"] for event in result.execution["execution_trace"]["events"]]
        self.assertTrue(all(item == {"channels": ["SYNTH-C1"], "start": 0.0, "end": 1.0} for item in args))

    def test_expired_artifact_is_rebuilt_once_with_same_event_scope(self):
        context = make_context()
        context.executor = FaultInjectingExecutor(context.executor, "artifact_expired")
        result = ConstraintCarryingEEGAgent(Point1FakeLLM(), context, max_replans=1).run(
            "计算 stimulus 事件前 -0.2 秒到后 0.8 秒的绝对频带功率"
        )
        self.assertEqual("completed", result.stop_reason)
        self.assertEqual(1, result.execution["replans"])
        create_events = [
            event for event in result.execution["execution_trace"]["events"]
            if event["tool_name"] == "create_epochs"
        ]
        self.assertEqual(2, len(create_events))
        self.assertTrue(all(event["arguments"]["labels"] == ["stimulus"] for event in create_events))
        self.assertTrue(result.evidence_check["closed"])


if __name__ == "__main__":
    unittest.main()
