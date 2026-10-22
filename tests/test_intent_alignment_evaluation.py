import json
from pathlib import Path
import unittest

from eeg_harness.agent import EEGAgent
from eeg_harness.llm import DemoFakeLLM
from eeg_harness.pipeline import load_config
from eeg_harness.research.intent_alignment.evaluation import (
    build_context, load_suite, run_controlled_injections, score_result,
)


ROOT = Path(__file__).resolve().parents[1]


class IntentAlignmentEvaluationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = load_suite(ROOT / "config" / "point1_intent_alignment_cases.json")
        cls.config = load_config(ROOT / "config" / "baseline.json")

    def test_controlled_legal_substitutions_are_detected_offline(self):
        results = run_controlled_injections(self.payload, self.config)
        self.assertEqual(5, len(results))
        self.assertTrue(all(item["executor_accepted"] for item in results))
        self.assertTrue(all(item["offline_intent_mismatch"] for item in results))
        json.dumps(results, ensure_ascii=False, allow_nan=False)

    def test_gold_is_not_in_agent_runtime_prompt(self):
        case = next(item for item in self.payload["cases"] if item["id"] == "dev-psd-zh-01")
        client = DemoFakeLLM()
        agent = EEGAgent(client, build_context(case, self.config))
        prompt = agent._system_message()
        self.assertNotIn("expected_contract", prompt)
        self.assertNotIn("forbidden_tools", prompt)
        self.assertNotIn(case["id"], prompt)

    def test_matching_psd_route_passes_frozen_slots(self):
        case = next(item for item in self.payload["cases"] if item["id"] == "dev-psd-zh-01")
        result = EEGAgent(DemoFakeLLM(), build_context(case, self.config)).run(case["request"])
        # DemoFakeLLM uses C1 and 0..2; this intentionally demonstrates that the
        # offline scorer checks values, not merely the legal tool name.
        score = score_result(case, result)
        self.assertFalse(score["semantic_match"])
        self.assertTrue(score["actual_intent_error"])


if __name__ == "__main__":
    unittest.main()
