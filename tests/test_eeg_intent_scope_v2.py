import json
from pathlib import Path
import unittest

from eeg_harness.context import ExecutionContext
from eeg_harness.executor import Executor
from eeg_harness.pipeline import load_config
from eeg_harness.profiles import EDF_NATIVE
from eeg_harness.research.evidence_phase import build_quality_selection_record
from eeg_harness.research.intent_compiler.agent import IntentScopeTransferAgentV2
from eeg_harness.research.intent_compiler.scope import (
    GoalScope, GoalScopeGraph, IntentScopeCompilerV2Interpreter, ScopeRelation,
    SCOPE_TOOL, validate_scope_graph,
)
from eeg_harness.research.intent_compiler.scope_protocol import (
    FROZEN_SCOPE_SHA256, load_scope_protocol,
)
from eeg_harness.research.intent_compiler.scoring import intent_from_dict
from eeg_harness.research.integrated_method.fake import Point1FakeLLM
from eeg_harness.research.integrated_method.intent import INTENT_TOOL, IntentSpec
from eeg_harness.tools import build_default_registry


def context():
    record, _ = build_quality_selection_record((1,))
    return ExecutionContext(
        record, EDF_NATIVE, Executor(build_default_registry(), load_config("config/baseline.json")),
        "intent-scope-v2-test",
    )


def tool_message(tool_name, payload):
    return {
        "role": "assistant", "content": None,
        "tool_calls": [{
            "id": "scope-test", "type": "function",
            "function": {"name": tool_name, "arguments": json.dumps(payload, ensure_ascii=False)},
        }],
    }


class QueueScopeLLM:
    model = "scope-protocol-double"

    def __init__(self, intent_payload, scope_payload):
        self.intent_payload = intent_payload
        self.scope_payload = scope_payload
        self.calls = []
        self.request_count = 0
        self.total_usage = {}
        self.finish_reasons = []

    def complete(self, messages, tools, tool_choice="auto"):
        self.calls.append({"messages": messages, "tools": tools, "tool_choice": tool_choice})
        self.request_count += 1
        self.finish_reasons.append("tool_calls")
        name = tools[0]["function"]["name"]
        if name == INTENT_TOOL[0]["function"]["name"]:
            return tool_message(name, self.intent_payload)
        if name == SCOPE_TOOL[0]["function"]["name"]:
            return tool_message(name, self.scope_payload)
        return Point1FakeLLM._answer_call(messages)


def legal_request_and_intent():
    request = (
        "对 target 事件后 0 到 1 秒 Epoch，允许将这些 Epoch 重参考到 SYNTH-C2，"
        "并仅在转换后检查质量和计算绝对频带功率。"
    )
    intent = IntentSpec(
        "event_workflow",
        ("epoch_rereference", "epoch_quality", "event_bandpower"),
        {"labels": ["target"], "tmin": 0, "tmax": 1,
         "reference_channels": ["SYNTH-C2"], "rereference_authorized": True},
        {"labels": "target", "tmin": "0", "tmax": "1",
         "reference_channels": "SYNTH-C2",
         "rereference_authorized": "允许将这些 Epoch 重参考到 SYNTH-C2"},
        {"event_locked": "target 事件后 0 到 1 秒 Epoch",
         "epoch_rereference": "重参考到 SYNTH-C2",
         "quality_measurement": "检查质量",
         "spectral_power": "绝对频带功率"},
    )
    return request, intent


class IntentScopeProtocolTest(unittest.TestCase):
    def test_scope_manifest_is_frozen_and_independent(self):
        protocol, digest = load_scope_protocol()
        self.assertEqual(FROZEN_SCOPE_SHA256, digest)
        self.assertEqual(20, len(protocol["cases"]))
        self.assertEqual(8, sum(c["split"] == "development" for c in protocol["cases"]))
        self.assertEqual(12, sum(c["split"] == "holdout" for c in protocol["cases"]))
        self.assertFalse(protocol["annotation"]["second_independent_reviewer"])
        self.assertNotIn("H14", {case["id"] for case in protocol["cases"]})

    def test_h14_frozen_raw_intent_is_stopped_by_scope_graph(self):
        report = json.loads(Path(
            "docs/research/results/eeg_intent_compiler_v1_holdout_flash.json"
        ).read_text(encoding="utf-8"))
        row = next(item for item in report["cases"] if item["case_id"] == "H14")
        intent = intent_from_dict(row["raw_intent"])
        graph = GoalScopeGraph(
            (GoalScope("epoch_quality", "source_epochs", "Report quality before re-referencing"),
             GoalScope("epoch_rereference", "source_epochs", "I authorize re-referencing to SYNTH-C2"),
             GoalScope("event_bandpower", "effective_epochs", "post-reference absolute power")),
            (ScopeRelation("epoch_quality", "epoch_rereference", row["request"]),
             ScopeRelation("epoch_rereference", "event_bandpower", row["request"])),
        )
        decision, diagnostics = validate_scope_graph(intent, graph, row["request"])
        self.assertEqual("clarify", decision.disposition)
        self.assertEqual(("analysis_stage",), decision.missing_slots)
        self.assertIn(
            "unsupported_input_state:epoch_quality:source_epochs:effective_epochs",
            diagnostics["violations"],
        )

    def test_legal_post_rereference_chain_accepts_transitive_precedence(self):
        request, intent = legal_request_and_intent()
        graph = GoalScopeGraph(
            (GoalScope("epoch_rereference", "source_epochs", "重参考到 SYNTH-C2"),
             GoalScope("epoch_quality", "effective_epochs", "转换后检查质量"),
             GoalScope("event_bandpower", "effective_epochs", "计算绝对频带功率")),
            (ScopeRelation("epoch_rereference", "epoch_quality", request),
             ScopeRelation("epoch_quality", "event_bandpower", request)),
        )
        decision, diagnostics = validate_scope_graph(intent, graph, request)
        self.assertEqual("execute", decision.disposition)
        self.assertEqual([], diagnostics["violations"])

    def test_missing_edge_cycle_nonexact_evidence_and_unknown_fail_closed(self):
        request, intent = legal_request_and_intent()
        base_scopes = (
            GoalScope("epoch_rereference", "source_epochs", "重参考到 SYNTH-C2"),
            GoalScope("epoch_quality", "effective_epochs", "转换后检查质量"),
            GoalScope("event_bandpower", "effective_epochs", "计算绝对频带功率"),
        )
        cases = (
            GoalScopeGraph(base_scopes, ()),
            GoalScopeGraph(base_scopes, (
                ScopeRelation("epoch_rereference", "epoch_quality", request),
                ScopeRelation("epoch_quality", "epoch_rereference", request))),
            GoalScopeGraph((base_scopes[0], base_scopes[1],
                            GoalScope("event_bandpower", "effective_epochs", "fabricated")),
                           (ScopeRelation("epoch_rereference", "epoch_quality", request),
                            ScopeRelation("epoch_quality", "event_bandpower", request))),
            GoalScopeGraph(base_scopes,
                           (ScopeRelation("epoch_rereference", "epoch_quality", request),
                            ScopeRelation("epoch_quality", "event_bandpower", request)),
                           ("epoch_quality",)),
        )
        for graph in cases:
            with self.subTest(graph=graph):
                decision, diagnostics = validate_scope_graph(intent, graph, request)
                self.assertEqual("clarify", decision.disposition)
                self.assertTrue(diagnostics["violations"])

    def test_selection_chain_preserves_source_quality_and_effective_consumers(self):
        request = "检查 target Epoch 质量，允许筛除异常试次，再报告保留数量和绝对频带功率。"
        intent = IntentSpec(
            "event_workflow",
            ("epoch_quality", "trial_selection", "epoch_summary", "event_bandpower"),
        )
        graph = GoalScopeGraph(
            (GoalScope("epoch_quality", "source_epochs", "检查 target Epoch 质量"),
             GoalScope("trial_selection", "source_epochs", "允许筛除异常试次"),
             GoalScope("epoch_summary", "effective_epochs", "报告保留数量"),
             GoalScope("event_bandpower", "effective_epochs", "绝对频带功率")),
            (ScopeRelation("epoch_quality", "trial_selection", request),
             ScopeRelation("trial_selection", "epoch_summary", request),
             ScopeRelation("epoch_summary", "event_bandpower", request)),
        )
        decision, _ = validate_scope_graph(intent, graph, request)
        self.assertEqual("execute", decision.disposition)

    def test_transition_composition_is_unsupported(self):
        request = "允许筛除异常试次并重参考到 SYNTH-C2。"
        intent = IntentSpec(
            "event_workflow", ("epoch_quality", "trial_selection", "epoch_rereference"),
        )
        graph = GoalScopeGraph(
            (GoalScope("epoch_quality", "source_epochs", "异常试次"),
             GoalScope("trial_selection", "source_epochs", "允许筛除异常试次"),
             GoalScope("epoch_rereference", "source_epochs", "重参考到 SYNTH-C2")),
            (),
        )
        decision, diagnostics = validate_scope_graph(intent, graph, request)
        self.assertEqual("clarify", decision.disposition)
        self.assertIn("unsupported_transition_composition", diagnostics["violations"])

    def test_diagnostics_are_json_serializable(self):
        request, intent = legal_request_and_intent()
        graph = GoalScopeGraph(
            (GoalScope("epoch_rereference", "source_epochs", "重参考到 SYNTH-C2"),
             GoalScope("epoch_quality", "effective_epochs", "转换后检查质量"),
             GoalScope("event_bandpower", "effective_epochs", "计算绝对频带功率")),
            (ScopeRelation("epoch_rereference", "epoch_quality", request),
             ScopeRelation("epoch_quality", "event_bandpower", request)),
        )
        _, diagnostics = validate_scope_graph(intent, graph, request)
        json.dumps(diagnostics, ensure_ascii=False, allow_nan=False)


class IntentScopeAgentTest(unittest.TestCase):
    def test_no_transform_reuses_v1_without_second_model_call(self):
        request = "分析 SYNTH-C1 从 0 到 1 秒的频带功率"
        fake = Point1FakeLLM()
        decision = IntentScopeCompilerV2Interpreter(fake).interpret(request, context())
        self.assertEqual("execute", decision.disposition)
        self.assertEqual(1, fake.request_count)

    def test_h14_agent_clarifies_before_any_eeg_tool(self):
        report = json.loads(Path(
            "docs/research/results/eeg_intent_compiler_v1_holdout_flash.json"
        ).read_text(encoding="utf-8"))
        row = next(item for item in report["cases"] if item["case_id"] == "H14")
        scope = {
            "scopes": [
                {"goal": "epoch_quality", "input_state": "source_epochs",
                 "evidence_quote": "Report quality before re-referencing"},
                {"goal": "epoch_rereference", "input_state": "source_epochs",
                 "evidence_quote": "I authorize re-referencing to SYNTH-C2"},
                {"goal": "event_bandpower", "input_state": "effective_epochs",
                 "evidence_quote": "post-reference absolute power"},
            ],
            "relations": [
                {"predecessor": "epoch_quality", "successor": "epoch_rereference",
                 "evidence_quote": row["request"]},
                {"predecessor": "epoch_rereference", "successor": "event_bandpower",
                 "evidence_quote": row["request"]},
            ],
            "unknown_scopes": [],
        }
        ctx = context()
        run = IntentScopeTransferAgentV2(
            QueueScopeLLM(row["raw_intent"], scope), ctx,
        ).run(row["request"]).to_dict()
        self.assertEqual("clarification_required", run["stop_reason"])
        self.assertEqual("analysis_stage", run["interpretation"]["missing_slots"][0])
        self.assertEqual([], ctx.trace.to_dict()["events"])

    def test_legal_post_rereference_runs_existing_agent_and_closes_evidence(self):
        request, intent = legal_request_and_intent()
        scope = {
            "scopes": [
                {"goal": "epoch_rereference", "input_state": "source_epochs",
                 "evidence_quote": "重参考到 SYNTH-C2"},
                {"goal": "epoch_quality", "input_state": "effective_epochs",
                 "evidence_quote": "转换后检查质量"},
                {"goal": "event_bandpower", "input_state": "effective_epochs",
                 "evidence_quote": "计算绝对频带功率"},
            ],
            "relations": [
                {"predecessor": "epoch_rereference", "successor": "epoch_quality",
                 "evidence_quote": request},
                {"predecessor": "epoch_quality", "successor": "event_bandpower",
                 "evidence_quote": request},
            ],
            "unknown_scopes": [],
        }
        run = IntentScopeTransferAgentV2(
            QueueScopeLLM(intent.to_dict(), scope), context(),
        ).run(request).to_dict()
        self.assertEqual("completed", run["stop_reason"])
        self.assertTrue(run["evidence_check"]["closed"])
        self.assertTrue(run["answer_check"]["valid"])
        tools = [item["tool_name"] for item in run["execution"]["tool_results"]]
        self.assertIn("rereference_epochs", tools)
        self.assertIn("event_bandpower", tools)


if __name__ == "__main__":
    unittest.main()
