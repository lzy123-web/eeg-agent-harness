import json
import unittest

from eeg_harness.planning_evaluation import load_frozen_suite, run_benchmark


SUITE = "config/planning_benchmark_v1.json"


class PlanningEvaluationTest(unittest.TestCase):
    def test_suite_is_frozen_and_has_holdout_and_heterogeneous_cases(self):
        version, cases = load_frozen_suite(SUITE)
        self.assertEqual(version, "1.0")
        self.assertEqual(len(cases), 16)
        self.assertEqual({item.split for item in cases}, {"development", "holdout"})
        self.assertTrue(any(item.task.goal == "sequence" for item in cases))

    def test_three_strategies_and_ablations_run_on_identical_suite(self):
        result = run_benchmark(SUITE)
        self.assertEqual(result["case_count"], 16)
        self.assertIn("execution_only", result["summary"])
        self.assertIn("expert_dag", result["summary"])
        self.assertIn("constrained_planner", result["summary"])
        self.assertEqual(set(result["summary_by_split"]), {"development", "holdout"})
        self.assertEqual(len(result["outcomes"]), 16 * 6)
        json.dumps(result, allow_nan=False)

    def test_candidate_is_not_assumed_to_dominate_expert(self):
        summary = run_benchmark(SUITE)["summary"]
        self.assertGreaterEqual(
            summary["expert_dag"]["valid_task_completion_rate"],
            summary["constrained_planner"]["valid_task_completion_rate"] - 0.2,
        )
        self.assertLessEqual(summary["expert_dag"]["tool_calls"], summary["constrained_planner"]["tool_calls"])


if __name__ == "__main__":
    unittest.main()
