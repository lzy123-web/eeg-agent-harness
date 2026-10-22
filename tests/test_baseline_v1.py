import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from eeg_harness.baseline_v1 import (
    CASE_FILE_HASH,
    build_case_context,
    load_case_suite,
    run_suite,
    evaluate_case,
)
from eeg_harness.pipeline import load_config


ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = ROOT / "config" / "agent_baseline_v1_cases.json"
CONFIG = load_config(ROOT / "config" / "baseline.json")


class BaselineV1RunnerTest(unittest.TestCase):
    def test_frozen_hash_and_synthetic_scenarios(self):
        payload, digest = load_case_suite(CASE_PATH)
        self.assertEqual(digest, CASE_FILE_HASH)
        for scenario, expected_profile in (
            ("synthetic_event_native", "edf_native"),
            ("synthetic_no_event_native", "edf_native"),
            ("synthetic_tuev_22_with_model", "tuev_bipolar_22"),
        ):
            case = next(item for item in payload["cases"] if item["scenario"] == scenario)
            context = build_case_context(case, CONFIG)
            self.assertEqual(context.profile.profile_id, expected_profile)
            self.assertTrue(context.record.metadata["is_synthetic"])

    def test_protocol_double_runs_all_frozen_cases(self):
        payload, _ = load_case_suite(CASE_PATH)
        with tempfile.NamedTemporaryFile(suffix=".pth") as model_file, patch(
            "eeg_harness.tools.seizureNormalModel_OneSecond",
            return_value=[{"FP1-F7": {"Non-seiz": 0.5, "seiz": 0.5}}],
        ):
            report = run_suite(
                payload, CONFIG, "fake", model_path=model_file.name
            )
        failures = [
            (item["case_id"], item.get("checks"))
            for item in report["results"] if not item.get("accepted")
        ]
        self.assertEqual(failures, [])
        self.assertEqual(report["summary"]["case_count"], 30)
        self.assertEqual(report["summary"]["accepted_count"], 30)
        json.dumps(report, ensure_ascii=False, allow_nan=False)

    def test_answer_checker_accepts_explicit_erd_ers_negation(self):
        class Result:
            final_answer = "这是绝对功率，不能解释为 ERD/ERS。"
            stop_reason = "completed"
            tool_results = [{"tool_name": "psd", "success": True, "data": {}}]
            execution_trace = {"events": [{
                "tool_name": "psd",
                "arguments": {"channels": ["SYNTH-C1"], "start": 0, "end": 2},
            }]}

        payload, _ = load_case_suite(CASE_PATH)
        case = next(item for item in payload["cases"] if item["id"] == "dev-psd-01")
        checks = evaluate_case(case, Result())
        self.assertTrue(checks["answer:not_erd_ers"])


if __name__ == "__main__":
    unittest.main()
