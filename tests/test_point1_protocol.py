import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "config" / "point1_semantic_planning_v1.json"


class Point1ProtocolFreezeTest(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads(SUITE.read_text(encoding="utf-8"))

    def test_case_count_split_and_scenarios(self):
        cases = self.payload["cases"]
        self.assertEqual(18, len(cases))
        self.assertEqual(12, sum(case["split"] == "development" for case in cases))
        self.assertEqual(6, sum(case["split"] == "holdout" for case in cases))
        self.assertEqual(
            {"frequency_branch", "event_alignment", "epoch_lineage", "combined", "extension"},
            {case["scenario"] for case in cases},
        )
        self.assertEqual(len(cases), len({case["id"] for case in cases}))

    def test_three_fair_methods_and_equal_budget_are_frozen(self):
        self.assertEqual(
            ["expert_dag", "generic_semantic", "candidate_eeg_semantic"],
            self.payload["methods"],
        )
        self.assertEqual(
            {"max_tool_calls": 8, "max_state_queries": 8, "max_recoveries": 1},
            self.payload["budgets"],
        )

    def test_suite_has_stable_canonical_hash(self):
        canonical = json.dumps(self.payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        self.assertEqual(
            "1e2de202eb91b76e3df32e133ad4bf37578be74d506f15b302b1a39d4ffb5d47",
            digest,
        )


if __name__ == "__main__":
    unittest.main()
