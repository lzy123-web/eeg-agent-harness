import json
import unittest

from eeg_harness.planning_evaluation import load_frozen_suite, run_benchmark
from eeg_harness.evaluation_protocol import (
    COMPLETED, FAILED, RECOVERED_TRANSIENT, REJECTED_EXECUTOR,
    REJECTED_PREFLIGHT, classify_outcome,
)


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
        self.assertEqual(len(result["outcomes"]), 16 * 7)
        json.dumps(result, allow_nan=False)

    def test_candidate_is_not_assumed_to_dominate_expert(self):
        summary = run_benchmark(SUITE)["summary"]
        self.assertGreaterEqual(
            summary["expert_dag"]["valid_task_completion_rate"],
            summary["constrained_planner"]["valid_task_completion_rate"] - 0.2,
        )
        self.assertLessEqual(summary["expert_dag"]["tool_calls"], summary["constrained_planner"]["tool_calls"])

    def test_strong_expert_has_same_recovery_budget_as_planner(self):
        result = run_benchmark(SUITE)
        by_policy = {
            policy: [row for row in result["outcomes"] if row["policy"] == policy]
            for policy in result["policies"]
        }
        dynamic = "holdout_dynamic_artifact_loss"
        strong = next(row for row in by_policy["expert_dag"] if row["case_id"] == dynamic)
        weak = next(row for row in by_policy["expert_dag_no_recovery"] if row["case_id"] == dynamic)
        planner = next(row for row in by_policy["constrained_planner"] if row["case_id"] == dynamic)
        self.assertEqual(strong["outcome_class"], RECOVERED_TRANSIENT)
        self.assertEqual(planner["outcome_class"], RECOVERED_TRANSIENT)
        self.assertEqual(weak["outcome_class"], FAILED)
        self.assertEqual(strong["budget"], planner["budget"])

    def test_outcome_taxonomy_separates_rejection_locations(self):
        self.assertEqual(classify_outcome("complete", "completed"), COMPLETED)
        self.assertEqual(
            classify_outcome("complete", "completed", recoveries=1), RECOVERED_TRANSIENT
        )
        self.assertEqual(
            classify_outcome("reject", "rejected", preflight_rejected=True),
            REJECTED_PREFLIGHT,
        )
        self.assertEqual(
            classify_outcome("reject", "execution_failed"), REJECTED_EXECUTOR
        )
        self.assertEqual(classify_outcome("complete", "execution_failed"), FAILED)


if __name__ == "__main__":
    unittest.main()
