"""Predeclared cross-family requests, independent numeric oracles and safe stops."""

import json
import os
import unittest

import numpy as np
from scipy.signal import welch

from eeg_harness.demo import build_synthetic_event_record, build_synthetic_no_event_record
from eeg_harness.pipeline import load_config
from eeg_harness.research.integrated_method.v3_acceptance import CASES, CaseFakeClient, run_case
from eeg_harness.research.integrated_method.v3_application import render_auxiliary_evidence_note


class CrossFamilyAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pathlib import Path
        cls.config = load_config(Path(__file__).resolve().parents[1] / "config" / "baseline.json")

    def _run(self, case_id, *, model_path=None):
        case = next(item for item in CASES if item["id"] == case_id)
        return run_case(case, CaseFakeClient(case["payloads"]), self.config, model_path)

    def test_c1_continuous_information_amplitude_and_psd_oracles(self):
        entry = self._run("C1_continuous")
        self.assertTrue(entry["goal_set_matches_predeclared"])
        self.assertEqual(entry["tool_count"], 3)
        goals = entry["final_result"]["evidence_bundle"]["goals"]
        info, amplitude, spectral = [item["result"] for item in goals]
        self.assertEqual((info["sfreq"], info["channel_count"], info["duration_seconds"]),
                         (128.0, 2, 8.0))
        x = build_synthetic_no_event_record().data[0, :256]
        self.assertEqual(amplitude["SYNTH-C1"]["mean_abs"], "{:.2e}".format(np.mean(np.abs(x))))
        self.assertEqual(amplitude["SYNTH-C1"]["rms"], "{:.2e}".format(np.sqrt(np.mean(x*x))))
        frequencies, density = welch(x, fs=128.0, nperseg=128.0)
        alpha = (frequencies >= 8) & (frequencies <= 13)
        self.assertEqual(spectral["SYNTH-C1"]["alpha"],
                         "{:.2e}".format(np.trapz(density[alpha], frequencies[alpha])))
        bundle = entry["final_result"]["evidence_bundle"]
        self.assertEqual(bundle["published_goal_count"], 3)
        self.assertEqual(bundle["goals"][2]["analysis_configuration"]["freq_bands"]["alpha"],
                         [8.0, 13.0])
        note = render_auxiliary_evidence_note(bundle)
        self.assertIn("分析配置", note)
        self.assertIn("输入绑定", note)
        self.assertIn("不构成 ASD 诊断", note)
        json.dumps(entry, allow_nan=False)

    def test_c2_event_trial_count_quality_and_power_oracles(self):
        entry = self._run("C2_event")
        self.assertTrue(entry["goal_set_matches_predeclared"])
        result = entry["final_result"]
        tools = [item["tool_name"] for item in result["tool_results"]]
        self.assertEqual(tools.count("list_events"), 1)
        self.assertEqual(tools.count("create_epochs"), 1)
        self.assertNotIn("select_quality_epochs", tools)
        summary, quality, power = [item["result"] for item in result["evidence_bundle"]["goals"]]
        self.assertEqual(summary["valid_epoch_count"], 2)
        self.assertEqual(summary["rejected_epoch_count"], 1)
        self.assertEqual(quality["threshold_status"], "empirical_not_clinically_calibrated")
        record = build_synthetic_event_record()
        segments = [record.data[0, int(onset*128):int((onset+1)*128)] for onset in (1, 3)]
        oracle = []
        for segment in segments:
            frequencies, density = welch(segment, fs=128.0, nperseg=128)
            mask = (frequencies >= 8) & (frequencies <= 13)
            oracle.append(float(np.trapz(density[mask], frequencies[mask])))
        observed = power["conditions"]["stimulus"]["channels"]["SYNTH-C1"]["alpha"]
        self.assertAlmostEqual(observed, float(np.mean(oracle)), places=12)

    def test_c3_model_resource_gate_and_optional_real_weight(self):
        blocked = self._run("C3_model")
        self.assertEqual(blocked["final_result"]["status"], "rejected")
        self.assertEqual(blocked["tool_count"], 0)
        model_path = os.environ.get("EEG_HARNESS_MODEL_PATH")
        if not model_path:
            self.skipTest("Set EEG_HARNESS_MODEL_PATH for synthetic 22-lead inference")
        entry = self._run("C3_model", model_path=model_path)
        self.assertTrue(entry["goal_set_matches_predeclared"])
        output = entry["final_result"]["evidence_bundle"]["goals"][0]["result"]
        self.assertEqual(len(output), 1)
        scores = output[0]["FP1-F7"]
        self.assertTrue(all(np.isfinite(value) and 0 <= value <= 1 for value in scores.values()))
        self.assertAlmostEqual(scores["Non-seiz"] + scores["seiz"], 1.0, places=1)

    def test_c4_cross_family_scope_and_amplitude(self):
        entry = self._run("C4_cross_family")
        self.assertTrue(entry["goal_set_matches_predeclared"])
        result = entry["final_result"]
        self.assertNotIn("select_quality_epochs", [item["tool_name"] for item in result["tool_results"]])
        amp, summary, power = [item["result"] for item in result["evidence_bundle"]["goals"]]
        x = build_synthetic_event_record().data[1, 128:384]
        self.assertEqual(amp["SYNTH-C2"]["rms"], "{:.2e}".format(np.sqrt(np.mean(x*x))))
        self.assertEqual(summary["valid_epoch_count"], 1)
        self.assertEqual(power["conditions"]["control"]["epoch_count"], 1)
        self.assertNotEqual(result["evidence_bundle"]["goals"][0]["analysis_scope"],
                            result["evidence_bundle"]["goals"][2]["analysis_scope"])

    def test_c5_clarification_preserves_scope_and_c6_c7_stop(self):
        clarified = self._run("C5_clarification")
        self.assertEqual(clarified["initial_status"], "clarification_required")
        self.assertEqual(clarified["initial_result"]["tool_results"], [])
        self.assertTrue(clarified["goal_set_matches_predeclared"])
        self.assertEqual(clarified["final_result"]["evidence_bundle"]["goals"][0]["parameters"],
                         {"channels": ["SYNTH-C2"], "start": 1, "end": 3})
        for name in ("C6_no_events", "C7_unsupported"):
            with self.subTest(case=name):
                stopped = self._run(name)
                self.assertEqual(stopped["final_result"]["status"], "rejected")
                self.assertEqual(stopped["tool_count"], 0)
                self.assertEqual(stopped["final_result"]["evidence_bundle"]["publication"], "none")


if __name__ == "__main__":
    unittest.main()
