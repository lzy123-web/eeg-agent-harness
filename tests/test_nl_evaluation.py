import json
import unittest

from eeg_harness.nl_evaluation import run_fake_nl_comparison


class NaturalLanguageEvaluationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_fake_nl_comparison()

    def test_comparison_is_serializable_and_separates_intent(self):
        json.dumps(self.result, ensure_ascii=False, allow_nan=False)
        self.assertEqual(self.result["case_count"], 9)
        self.assertEqual(len(self.result["outcomes"]), 27)
        self.assertTrue(all("intent_correct" in row for row in self.result["outcomes"]))

    def test_fake_templates_are_explicitly_labeled(self):
        self.assertEqual(
            self.result["backend"], "deterministic human-authored template simulator"
        )
        self.assertTrue(all(
            item["input_kind"] == "human_authored_template"
            for item in self.result["outcomes"]
        ))

    def test_planner_and_strong_expert_use_same_single_parse_call(self):
        summary = self.result["summary"]
        self.assertEqual(summary["strong_expert"]["llm_calls"], 9)
        self.assertEqual(summary["constrained_planner"]["llm_calls"], 9)


if __name__ == "__main__":
    unittest.main()
