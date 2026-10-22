import unittest
from pathlib import Path

from eeg_harness.llm import DemoFakeLLM
from eeg_harness.real_llm_evaluation import run_real_llm_suite


ROOT = Path(__file__).resolve().parents[1]


class RealLLMEvaluationTest(unittest.TestCase):
    def test_suite_protocol_with_deterministic_double(self):
        report = run_real_llm_suite(
            DemoFakeLLM, ROOT / "config" / "baseline.json"
        )
        self.assertEqual(report["summary"]["case_count"], 4)
        self.assertTrue(report["summary"]["all_accepted"])
        self.assertTrue(report["privacy"]["synthetic_only"])
        self.assertFalse(report["privacy"]["raw_eeg_sent_to_llm"])
        event_case = next(
            item for item in report["cases"]
            if item["case_id"] == "event_bandpower_chain"
        )
        self.assertTrue(event_case["acceptance_checks"]["artifact_id_propagated"])


if __name__ == "__main__":
    unittest.main()
