import json
from pathlib import Path
import unittest

from eeg_harness.research.semantic_planning.evaluation import run_evaluation


ROOT = Path(__file__).resolve().parents[1]


class SemanticPlanningEvaluationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_evaluation(ROOT / "config" / "point1_semantic_planning_v1.json")

    def test_three_methods_use_same_cases_and_budget(self):
        self.assertEqual(54, len(self.result["cases"]))
        self.assertEqual({"max_tool_calls": 8, "max_state_queries": 8, "max_recoveries": 1}, self.result["budgets"])
        for method in self.result["aggregate"].values():
            self.assertEqual(18, method["case_count"])

    def test_results_are_json_serializable_and_oracle_is_separate(self):
        json.dumps(self.result, allow_nan=False)
        self.assertTrue(all("oracle_errors" in row for row in self.result["cases"]))

    def test_no_method_is_assumed_to_win(self):
        aggregates = self.result["aggregate"]
        self.assertEqual(
            aggregates["generic_semantic"]["overall_correct_rate"],
            aggregates["candidate_eeg_semantic"]["overall_correct_rate"],
        )

    def test_budget_and_holdout_are_reported(self):
        for row in self.result["cases"]:
            self.assertLessEqual(row["tool_calls"], 8)
            self.assertLessEqual(row["state_queries"], 8)
        self.assertTrue(any(row["split"] == "holdout" for row in self.result["cases"]))


if __name__ == "__main__":
    unittest.main()
