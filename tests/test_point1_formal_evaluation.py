import json
import unittest

from eeg_harness.research.formal_evaluation.fixtures import (
    build_fixture, oracle_effective,
)
from eeg_harness.research.formal_evaluation.protocol import load_cases
from eeg_harness.research.formal_evaluation.runner import ABLATIONS, run_suite
from eeg_harness.research.formal_evaluation.scoring import wilson_interval


class FormalEvaluationInfrastructureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol, _ = load_cases()

    def test_independent_oracle_uses_fixture_not_tool_results(self):
        case = next(row for row in self.protocol["cases"] if row["id"] == "R01")
        context, _, config = build_fixture(case)
        oracle = oracle_effective(case, context.record, config)
        self.assertEqual((3, 2, 128), oracle["data"].shape)
        self.assertTrue((oracle["data"][:, 1, :] == 0).all())
        self.assertIn("SYNTH-C1", oracle["bandpower"])

    def test_development_candidate_and_expert_pass_same_scorer(self):
        report = run_suite("development")
        self.assertEqual(16, len(report["rows"]))
        self.assertTrue(all(row["score"]["passed"] for row in report["rows"]))
        json.dumps(report, ensure_ascii=False, allow_nan=False)

    def test_guard_ablation_is_penalized_for_unauthorized_transform(self):
        report = run_suite(
            "development", methods=("without_eeg_scientific_guards",),
        )
        failures = [row for row in report["rows"] if not row["score"]["passed"]]
        self.assertEqual({"S04", "R04"}, {row["case_id"] for row in failures})
        self.assertTrue(all(
            row["score"]["error_type"] == "unsafe_or_unauthorized_transform"
            for row in failures
        ))

    def test_ablations_are_exactly_preregistered(self):
        self.assertEqual({
            "without_dependency_invalidation", "without_semantic_evidence_reuse",
            "whole_plan_replay", "without_eeg_scientific_guards",
        }, set(ABLATIONS))

    def test_wilson_interval_is_bounded(self):
        low, high = wilson_interval(4, 4)
        self.assertGreater(low, 0.0)
        self.assertEqual(1.0, high)


if __name__ == "__main__":
    unittest.main()
