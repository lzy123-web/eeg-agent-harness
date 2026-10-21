import json
import unittest

from eeg_harness.planning_evaluation import load_frozen_suite, run_benchmark


SUITE = "config/planning_benchmark_v2.json"


class PlanningEvaluationV2Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_benchmark(SUITE)

    def test_frozen_split_and_dynamic_cases(self):
        version, cases = load_frozen_suite(SUITE)
        self.assertEqual(version, "2.0")
        self.assertEqual(len(cases), 22)
        self.assertEqual({item.split for item in cases}, {"development", "holdout"})
        self.assertEqual(len([item for item in cases if item.fault]), 5)

    def test_all_results_are_serializable_and_within_budget(self):
        json.dumps(self.result, ensure_ascii=False, allow_nan=False)
        self.assertEqual(len(self.result["outcomes"]), 22 * 7)
        self.assertTrue(all(
            item["tool_calls"] <= item["budget"]["max_tool_calls"]
            for item in self.result["outcomes"]
        ))

    def test_strong_expert_and_planner_receive_equal_recovery_limits(self):
        rows = self.result["outcomes"]
        for case_id in {item["case_id"] for item in rows}:
            expert = next(item for item in rows if item["policy"] == "expert_dag" and item["case_id"] == case_id)
            planner = next(item for item in rows if item["policy"] == "constrained_planner" and item["case_id"] == case_id)
            self.assertEqual(expert["budget"], planner["budget"])

    def test_dynamic_faults_are_not_all_forced_to_recover(self):
        planner = [
            item for item in self.result["outcomes"]
            if item["policy"] == "constrained_planner" and item["fault"]
        ]
        classes = {item["outcome_class"] for item in planner}
        self.assertIn("recovered_transient", classes)
        self.assertTrue(classes.intersection({"rejected_preflight", "rejected_executor"}))


if __name__ == "__main__":
    unittest.main()
