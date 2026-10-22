from pathlib import Path
import unittest

from eeg_harness.research.intent_alignment.comparison import score_decision
from eeg_harness.research.intent_alignment.evaluation import load_suite


ROOT = Path(__file__).resolve().parents[1]


class IntentAlignmentComparisonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = load_suite(ROOT / "config" / "point1_intent_alignment_cases.json")
        cls.cases = {case["id"]: case for case in payload["cases"]}

    def test_missing_channel_must_remain_unknown(self):
        case = self.cases["hold-missing-channel-01"]
        good = {"action": "clarify", "analysis_type": "amplitude", "channels": [], "window": [1, 2], "event_labels": [], "source_stage": "current"}
        guessed = {**good, "action": "execute", "channels": ["SYNTH-C1"]}
        self.assertTrue(score_decision(case, good)["accepted"])
        self.assertFalse(score_decision(case, guessed)["accepted"])

    def test_explicit_distractor_does_not_replace_target_channel(self):
        case = self.cases["hold-channel-distractor-01"]
        good = {"action": "execute", "analysis_type": "psd", "channels": ["SYNTH-C2"], "window": [4, 6], "event_labels": [], "source_stage": "current"}
        wrong = {**good, "channels": ["SYNTH-C1"]}
        self.assertTrue(score_decision(case, good)["accepted"])
        self.assertFalse(score_decision(case, wrong)["accepted"])


if __name__ == "__main__":
    unittest.main()
