import json
import unittest

from eeg_harness.research.evidence_phase.evaluation import run_shared_planning


class EvidencePhaseFairComparisonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_shared_planning()

    def test_methods_receive_same_cases_and_no_runtime_gold(self):
        self.assertFalse(self.result["gold_visible_to_runtime"])
        self.assertEqual(
            {"strong_route_preflight", "ccep"}, set(self.result["summary"])
        )
        self.assertEqual(24, len(self.result["cases"]))
        json.dumps(self.result, ensure_ascii=False, allow_nan=False)

    def test_no_method_is_assumed_to_win(self):
        strong = self.result["summary"]["strong_route_preflight"]
        ccep = self.result["summary"]["ccep"]
        self.assertEqual(strong["evaluable_cases"], ccep["evaluable_cases"])
        self.assertEqual(strong["correct_cases"], ccep["correct_cases"])
        self.assertEqual(strong["scientific_completion_count"], ccep["scientific_completion_count"])

    def test_selection_and_no_selection_lineage_are_scored(self):
        rows = {item["case_id"]: item for item in self.result["cases"]}
        for case_id in ("dev-q-power-no-select-zh", "dev-q-select-power-zh"):
            for method in ("strong_route_preflight", "ccep"):
                self.assertTrue(rows[case_id]["methods"][method]["score"]["correct"])

    def test_all_bad_epochs_are_scored_as_an_explicit_empty_failure(self):
        rows = {item["case_id"]: item for item in self.result["cases"]}
        for case_id in ("dev-all-bad-stop", "hold-all-bad-stop-en"):
            for method in ("strong_route_preflight", "ccep"):
                score = rows[case_id]["methods"][method]["score"]
                self.assertTrue(score["correct"])
                self.assertEqual(0, score["output_epoch_count"])
                self.assertEqual(
                    "execution_failed", rows[case_id]["methods"][method]["run"]["status"]
                )


if __name__ == "__main__":
    unittest.main()
