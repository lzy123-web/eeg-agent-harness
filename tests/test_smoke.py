import json
import math
import os
from pathlib import Path
import unittest

from eeg_harness.legacy.data_load import inspect_edf, load_edf_record
from eeg_harness.legacy.features import compute_amplitude, compute_psd
from eeg_harness.legacy.seizure import (
    ModelResourceError,
    load_seizure_model,
    seizureNormalModel_OneSecond,
)
from eeg_harness.pipeline import load_config, run_baseline


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config" / "baseline.json"


class MissingModelTest(unittest.TestCase):
    def test_missing_model_reports_explicit_failure(self):
        missing = PROJECT_ROOT / "models" / "does-not-exist.pth"
        with self.assertRaisesRegex(ModelResourceError, "resource not found"):
            load_seizure_model(str(missing))


@unittest.skipUnless(
    os.environ.get("EEG_HARNESS_TEST_EDF") and os.environ.get("EEG_HARNESS_MODEL_PATH"),
    "Set EEG_HARNESS_TEST_EDF and EEG_HARNESS_MODEL_PATH for resource smoke tests",
)
class RealResourceSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.edf_path = Path(os.environ["EEG_HARNESS_TEST_EDF"])
        cls.model_path = Path(os.environ["EEG_HARNESS_MODEL_PATH"])
        cls.config = load_config(CONFIG_PATH)
        cls.source_info = inspect_edf(cls.edf_path)
        cls.record = load_edf_record(cls.edf_path, cls.config)

    def test_edf_load_and_preprocessing_shape(self):
        self.assertEqual(self.source_info["original_sfreq"], 250.0)
        self.assertEqual(self.record.data.shape, (22, 61696))
        self.assertEqual(str(self.record.data.dtype), "float32")
        self.assertEqual(self.record.sfreq, 256.0)
        self.assertEqual(self.config["fs"], 256)

    def test_feature_outputs_are_numeric_and_serializable(self):
        amplitude = compute_amplitude(self.record, ["FP1-F7"], 0, 1, self.config)
        psd = compute_psd(self.record, ["FP1-F7"], 0, 1, self.config)
        self.assertEqual(set(amplitude["FP1-F7"]), {"mean_abs", "rms", "max_val", "min_val"})
        self.assertEqual(set(psd["FP1-F7"]), {"delta", "theta", "alpha", "beta", "gamma"})
        for value in [*amplitude["FP1-F7"].values(), *psd["FP1-F7"].values()]:
            self.assertTrue(math.isfinite(float(value)))
        json.dumps({"amplitude": amplitude, "psd": psd}, allow_nan=False)

    def test_model_output_shape_and_serialization(self):
        output = seizureNormalModel_OneSecond(
            self.record, ["FP1-F7"], 0, 1, self.config, model_path=self.model_path
        )
        self.assertEqual(len(output), 1)
        self.assertEqual(set(output[0]["FP1-F7"]), {"Non-seiz", "seiz"})
        probabilities = list(output[0]["FP1-F7"].values())
        self.assertEqual(len(probabilities), 2)
        self.assertAlmostEqual(sum(probabilities), 1.0, places=2)
        json.dumps(output, allow_nan=False)

    def test_complete_baseline_result_is_serializable(self):
        result = run_baseline(
            self.edf_path,
            self.model_path,
            CONFIG_PATH,
            channel="FP1-F7",
            start=0,
            end=1,
        )
        self.assertEqual(result["preprocessing"]["output_shape"], [22, 61696])
        self.assertEqual(result["preprocessing"]["target_sfreq"], 256)
        self.assertEqual(result["model_inference"]["model_input_shape_per_second"], [1, 256])
        self.assertFalse(result["data_management"]["uses_process_global_data_store"])
        json.dumps(result, ensure_ascii=False, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
