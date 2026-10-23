import unittest

from eeg_harness.research.evidence_phase.real_evaluation import (
    REAL_HOLDOUT_CASE_IDS, _normalise_for_score,
)


class EvidencePhaseRealEvaluationTest(unittest.TestCase):
    def test_holdout_pair_is_fixed_and_covers_selection_contrast(self):
        self.assertEqual(
            ("hold-q-power-no-select-en", "hold-q-select-power-en"),
            REAL_HOLDOUT_CASE_IDS,
        )

    def test_native_and_ccep_results_normalise_without_answer_text(self):
        native = _normalise_for_score("native", {
            "stop_reason": "completed", "tool_results": [{"tool_name": "x"}],
        })
        ccep = _normalise_for_score("ccep", {
            "stop_reason": "completed", "execution": {
                "status": "completed", "tool_results": [{"tool_name": "y"}],
            },
        })
        self.assertEqual("completed", native["status"])
        self.assertEqual("x", native["tool_results"][0]["tool_name"])
        self.assertEqual("y", ccep["tool_results"][0]["tool_name"])


if __name__ == "__main__":
    unittest.main()
