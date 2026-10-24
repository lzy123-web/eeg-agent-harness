import hashlib
import json
from pathlib import Path
import unittest


PROTOCOL = Path("config/point1_formal_eval_protocol_v1.json")


class FrozenPoint1ProtocolTest(unittest.TestCase):
    def test_protocol_is_balanced_unique_and_runtime_blind(self):
        raw = PROTOCOL.read_bytes()
        protocol = json.loads(raw)
        cases = protocol["cases"]
        self.assertEqual(24, len(cases))
        self.assertEqual(24, len({case["id"] for case in cases}))
        self.assertEqual(12, sum(case["family"] == "selection" for case in cases))
        self.assertEqual(12, sum(case["family"] == "rereference" for case in cases))
        self.assertEqual(8, sum(case["split"] == "development" for case in cases))
        self.assertEqual(16, sum(case["split"] == "holdout" for case in cases))
        self.assertFalse(protocol["equal_conditions"]["offline_gold_visible_to_runtime"])
        self.assertEqual("frozen_not_executed", protocol["status"])
        self.assertEqual(64, len(hashlib.sha256(raw).hexdigest()))


if __name__ == "__main__":
    unittest.main()
