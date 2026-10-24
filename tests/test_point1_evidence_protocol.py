import unittest

from eeg_harness.research.evidence_phase.protocol import load_protocol


class EvidencePhaseProtocolFreezeTest(unittest.TestCase):
    def test_frozen_case_count_splits_and_budget(self):
        protocol = load_protocol()
        self.assertEqual(24, len(protocol["cases"]))
        self.assertEqual(12, sum(item["split"] == "development" for item in protocol["cases"]))
        self.assertEqual(12, sum(item["split"] == "holdout" for item in protocol["cases"]))
        self.assertEqual({"max_requests": 36, "max_tokens": 80000}, protocol["provider_budget"])

    def test_gold_is_independent_and_planning_scope_is_explicit(self):
        protocol = load_protocol()
        self.assertTrue(any(item["shared_intent"] is None for item in protocol["cases"]))
        self.assertTrue(any(item["oracle"]["disposition"] == "execution_failure" for item in protocol["cases"]))
        self.assertTrue(any("select_quality_epochs" in item["oracle"]["forbidden_tools"] for item in protocol["cases"]))


if __name__ == "__main__":
    unittest.main()
