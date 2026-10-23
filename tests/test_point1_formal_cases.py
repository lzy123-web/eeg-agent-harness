import hashlib
import json
from pathlib import Path
import unittest


CASES = Path("config/point1_formal_eval_cases_v1.json")
SKELETON = Path("config/point1_formal_eval_protocol_v1.json")


class FormalCaseSupplementTest(unittest.TestCase):
    def test_supplement_preserves_registered_ids_and_splits(self):
        supplement = json.loads(CASES.read_text(encoding="utf-8"))
        skeleton = json.loads(SKELETON.read_text(encoding="utf-8"))
        expected = {
            row["id"]: (row["family"], row["split"])
            for row in skeleton["cases"]
        }
        actual = {
            row["id"]: (row["family"], row["split"])
            for row in supplement["cases"]
        }
        self.assertEqual(expected, actual)
        self.assertEqual(24, len(actual))

    def test_every_case_has_executable_inputs_fault_and_independent_gold(self):
        supplement = json.loads(CASES.read_text(encoding="utf-8"))
        for case in supplement["cases"]:
            self.assertTrue(case["request"])
            self.assertIn(case["fixture"]["profile"], {"edf_native", "tuev_bipolar_22"})
            self.assertIn(case["task"]["disposition"], {"execute", "clarify"})
            self.assertIn("kind", case["fault"])
            self.assertIn(case["gold"]["terminal"], {
                "completed", "clarification_required", "scientifically_blocked",
                "plan_rejected",
            })
            self.assertTrue(case["gold"]["invariants"])
            self.assertEqual(
                set(case["gold"]["required_tools"]).isdisjoint(
                    case["gold"]["forbidden_tools"]
                ), True,
            )

    def test_manifest_has_stable_content_hash(self):
        digest = hashlib.sha256(CASES.read_bytes()).hexdigest()
        self.assertEqual(64, len(digest))


if __name__ == "__main__":
    unittest.main()
