import json
import unittest

from eeg_harness.evidence_evaluation import load_evidence_suite, run_evidence_benchmark


class EvidenceEvaluationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_evidence_benchmark()

    def test_suite_is_frozen_and_has_dev_holdout_profiles_and_cost(self):
        suite = load_evidence_suite("config/evidence_benchmark_v1.json")
        self.assertEqual(len(suite["cases"]), 16)
        self.assertEqual({item["split"] for item in suite["cases"]}, {"development", "holdout"})
        self.assertEqual({item["profile"] for item in suite["cases"]}, {"native", "tuev", "r3"})
        self.assertTrue(any(item.get("max_tool_calls") == 1 for item in suite["cases"]))

    def test_results_are_serializable_and_fair(self):
        json.dumps(self.result, ensure_ascii=False, allow_nan=False)
        self.assertEqual(len(self.result["outcomes"]), 48)
        for case_id in {item["case_id"] for item in self.result["outcomes"]}:
            rows = [item for item in self.result["outcomes"] if item["case_id"] == case_id]
            detections = [item["detection"] for item in rows]
            self.assertEqual(detections[0], detections[1])
            self.assertEqual(detections[1], detections[2])

    def test_candidate_is_not_assumed_to_beat_strong_expert(self):
        summary = self.result["summary"]
        self.assertEqual(
            summary["candidate"]["overall_case_accuracy"],
            summary["expert"]["overall_case_accuracy"],
        )
        self.assertEqual(summary["candidate"]["tool_calls"], summary["expert"]["tool_calls"])


if __name__ == "__main__":
    unittest.main()
