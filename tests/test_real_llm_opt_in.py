"""Opt-in network acceptance test; CI never receives or requires a secret."""

import os
from pathlib import Path
import unittest

from eeg_harness.llm import OpenAICompatibleClient
from eeg_harness.real_llm_evaluation import run_real_llm_suite


REQUIRED = (
    "EEG_HARNESS_LLM_BASE_URL",
    "EEG_HARNESS_LLM_API_KEY",
    "EEG_HARNESS_LLM_MODEL",
)
ENABLED = os.environ.get("EEG_HARNESS_RUN_REAL_LLM_TEST") == "1" and all(
    os.environ.get(name) for name in REQUIRED
)


@unittest.skipUnless(
    ENABLED,
    "Set EEG_HARNESS_RUN_REAL_LLM_TEST=1 and all LLM variables for network tests",
)
class RealLLMOptInTest(unittest.TestCase):
    def test_synthetic_acceptance_suite(self):
        root = Path(__file__).resolve().parents[1]
        report = run_real_llm_suite(
            OpenAICompatibleClient.from_env,
            root / "config" / "baseline.json",
        )
        self.assertTrue(report["summary"]["all_accepted"])
        self.assertTrue(report["privacy"]["synthetic_only"])
        self.assertFalse(report["privacy"]["raw_eeg_sent_to_llm"])


if __name__ == "__main__":
    unittest.main()
