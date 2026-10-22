import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = ROOT / "config" / "point1_intent_alignment_cases.json"


class IntentAlignmentProtocolTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(CASE_PATH.read_text(encoding="utf-8"))

    def test_case_count_splits_and_ids_are_frozen(self):
        cases = self.payload["cases"]
        self.assertEqual(24, len(cases))
        self.assertEqual(12, sum(case["split"] == "development" for case in cases))
        self.assertEqual(12, sum(case["split"] == "holdout" for case in cases))
        self.assertEqual(12, sum(case["real_llm"] for case in cases))
        self.assertEqual(len(cases), len({case["id"] for case in cases}))

    def test_contracts_are_independent_and_complete(self):
        required = {
            "outcome", "analysis_type", "channels", "window", "source_stage",
            "event_labels", "allowed_tools", "forbidden_tools", "explicit_slots",
            "unknown_slots",
        }
        for case in self.payload["cases"]:
            self.assertEqual(required, set(case["contract"]), case["id"])
            self.assertNotIn("contract", case["request"].lower())

    def test_budget_and_injections_are_fixed(self):
        self.assertEqual(36, self.payload["budgets"]["max_provider_requests"])
        self.assertEqual(80000, self.payload["budgets"]["max_total_tokens"])
        self.assertEqual(5, len(self.payload["controlled_injections"]))

    def test_canonical_hash_is_visible_for_freeze_commit(self):
        canonical = json.dumps(
            self.payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        print(f"Issue #9 frozen case hash: {digest}")


if __name__ == "__main__":
    unittest.main()
