import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "config" / "agent_baseline_v1_cases.json"


class BaselineV1CaseFreezeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(CASES_PATH.read_text(encoding="utf-8"))
        cls.cases = cls.payload["cases"]

    def test_case_count_splits_and_unique_ids_are_frozen(self):
        self.assertEqual(len(self.cases), 30)
        self.assertEqual(sum(item["split"] == "development" for item in self.cases), 18)
        self.assertEqual(sum(item["split"] == "holdout" for item in self.cases), 12)
        self.assertEqual(len({item["id"] for item in self.cases}), 30)
        self.assertEqual(sum(item["real_llm"] for item in self.cases), 15)

    def test_requests_do_not_reveal_registry_names_or_call_order(self):
        registry_names = {
            "record_info", "amplitude", "psd", "seizure_detection", "list_events",
            "create_epochs", "epoch_summary", "event_bandpower", "record_quality",
            "epoch_quality", "select_quality_epochs",
        }
        for case in self.cases:
            lowered = case["request"].lower()
            self.assertFalse(registry_names.intersection(lowered.split()), case["id"])
            self.assertNotIn("→", case["request"], case["id"])
            self.assertNotIn("artifact_id", lowered, case["id"])

    def test_every_case_has_independent_acceptance_contract(self):
        for case in self.cases:
            expected = case["expected"]
            self.assertIn(case["family"], {"basic", "event", "quality", "model", "unsupported"})
            self.assertIn(expected["outcome"], {"complete", "reject", "clarify"})
            self.assertIsInstance(expected["required_tools"], list)
            self.assertIsInstance(expected["allowed_tools"], list)
            self.assertIsInstance(expected["forbidden_tools"], list)
            self.assertTrue(expected["answer_checks"])


if __name__ == "__main__":
    unittest.main()
