import json
from pathlib import Path
import unittest

from eeg_harness.context import ExecutionContext
from eeg_harness.executor import Executor
from eeg_harness.pipeline import load_config
from eeg_harness.profiles import EDF_NATIVE
from eeg_harness.research.evidence_phase import build_quality_selection_record
from eeg_harness.research.intent_compiler.compiler import validate_intent_v1
from eeg_harness.research.intent_compiler.agent import IntentCompilerAgentV1
from eeg_harness.research.intent_compiler.protocol import FROZEN_SHA256, load_protocol
from eeg_harness.research.intent_compiler.scoring import intent_from_dict
from eeg_harness.research.integrated_method.fake import Point1FakeLLM
from eeg_harness.tools import build_default_registry


def context():
    record, _ = build_quality_selection_record((1,))
    return ExecutionContext(
        record, EDF_NATIVE, Executor(build_default_registry(), load_config("config/baseline.json")),
        "intent-v1-test",
    )


class IntentCompilerProtocolTest(unittest.TestCase):
    def test_manifest_is_frozen_balanced_and_single_reviewer_is_disclosed(self):
        protocol, digest = load_protocol()
        self.assertEqual(FROZEN_SHA256, digest)
        self.assertEqual(30, len(protocol["cases"]))
        self.assertEqual(14, sum(c["split"] == "development" for c in protocol["cases"]))
        self.assertEqual(16, sum(c["split"] == "holdout" for c in protocol["cases"]))
        self.assertFalse(protocol["annotation"]["second_independent_reviewer"])

    def test_legacy_model_payloads_separate_overstrict_rejection_from_real_missing_slot(self):
        report = json.loads(Path(
            "docs/research/results/point1_formal_real_llm_v1.json"
        ).read_text(encoding="utf-8"))
        protocol, _ = load_protocol()
        mapping = {case.get("legacy_case"): case for case in protocol["cases"]}
        rows = {row["case_id"]: row for row in report["rows"] if row["method"] == "CIEDG"}
        expected = {
            "S02": ("execute", ()), "S06": ("execute", ()),
            "R05": ("clarify", ("reference_channels",)), "R11": ("execute", ()),
        }
        for legacy, (disposition, missing) in expected.items():
            payload = rows[legacy]["result"]["interpretation"]["intent"]
            decision, diagnostics = validate_intent_v1(
                intent_from_dict(payload), mapping[legacy]["request"], context())
            self.assertEqual(disposition, decision.disposition, legacy)
            self.assertEqual(set(missing), set(decision.missing_slots), legacy)
            self.assertNotIn("channels", diagnostics["required_unknown_slots"])

    def test_unscoped_or_forbidden_transform_never_executes(self):
        base = {
            "analysis_type": "event_workflow",
            "objectives": ["epoch_quality", "trial_selection"],
            "parameters": {"labels": ["target"], "tmin": 0, "tmax": 1,
                           "selection_authorized": True},
            "explicit_evidence": {"labels": "target", "tmin": "0", "tmax": "1",
                                  "selection_authorized": "do not remove"},
            "semantic_evidence": {"event_locked": "target epochs",
                                  "quality_measurement": "quality",
                                  "trial_selection": "remove trials"},
            "unknown_slots": [], "forbidden_operations": [],
        }
        request = "Check quality for target epochs 0 to 1; do not remove trials."
        decision, _ = validate_intent_v1(intent_from_dict(base), request, context())
        self.assertNotEqual("execute", decision.disposition)

    def test_fake_llm_runs_through_real_agent_executor_and_answer_gate(self):
        run = IntentCompilerAgentV1(Point1FakeLLM(), context()).run(
            "检查 target 事件后 0 到 1 秒的质量，允许筛除异常试次，"
            "报告保留试次数并计算绝对频带功率"
        )
        rendered = run.to_dict()
        self.assertEqual("completed", rendered["stop_reason"])
        self.assertTrue(rendered["evidence_check"]["closed"])
        self.assertTrue(rendered["answer_check"]["valid"])
        tools = [item["tool_name"] for item in rendered["execution"]["tool_results"]]
        self.assertEqual([
            "list_events", "create_epochs", "epoch_quality",
            "select_quality_epochs", "epoch_summary", "event_bandpower",
        ], tools)


if __name__ == "__main__":
    unittest.main()
