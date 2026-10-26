"""Independent unit/semantic expectations for real tool fields, Issue #47."""
import copy
import unittest
from unittest.mock import patch

from eeg_harness.applications.evidence_statement import make_statement, verify_statement, _render
from eeg_harness.result_semantics import result_field_semantics, UnsupportedResultField
from eeg_harness.working_memory_deliveries import MultiResultWorkingMemoryStore
from eeg_harness.research.task_memory import synthetic_records


class ResultSemanticsTest(unittest.TestCase):
    def setUp(self):
        self.store = MultiResultWorkingMemoryStore("units", synthetic_records())
        self.scope = {"labels": ["stimulus"], "tmin": 0, "tmax": 1}
        self.store.begin_subgoal("事件条件功率", "A", deliveries=[{
            "key": "power", "tool": "event_bandpower", "scope": self.scope}])
        self.artifact = self.store.execute_numeric("create_epochs", self.scope)["observation"]["result"]["data"]["artifact_id"]
        self.store.execute_numeric("event_bandpower", {"artifact_id": self.artifact})
        self.store.close_subgoal("completed")
        self.entry = self.store.entries[-1]

    def test_power_frequency_count_and_metadata_have_different_field_contracts(self):
        cases = [(["conditions", "stimulus", "channels", "SYNTH-C1", "alpha"], "V²", "mean_absolute_epoch_band_power"),
                 (["frequency_resolution_hz"], "Hz", "frequency_resolution"),
                 (["conditions", "stimulus", "epoch_count"], "count", "epoch_count"),
                 (["method"], "metadata", "metadata")]
        for path, unit, kind in cases:
            with self.subTest(path=path):
                claim = make_statement(self.store, self.entry.task_id, path)
                self.assertEqual(claim["unit_or_kind"], unit)
                self.assertEqual(claim["field_semantics"]["kind"], kind)
                self.assertEqual(claim["tool_unit_or_kind"], "V²")
                self.assertTrue(verify_statement(self.store, claim)["valid"])

    def test_old_wrong_counts_and_frequency_units_rejected_even_with_consistent_text(self):
        for path in (["conditions", "stimulus", "epoch_count"], ["frequency_resolution_hz"]):
            with self.subTest(path=path):
                legacy = make_statement(self.store, self.entry.task_id, path)
                legacy.pop("field_semantics")
                legacy.pop("tool_unit_or_kind")
                legacy["unit_or_kind"] = "V²"
                legacy["text"] = _render(legacy)
                report = verify_statement(self.store, legacy)
                self.assertFalse(report["valid"])
                self.assertFalse(report["checks"]["field_semantic_unit"])

    def test_correct_legacy_alpha_schema_remains_verifiable(self):
        legacy = make_statement(self.store, self.entry.task_id,
                                ["conditions", "stimulus", "channels", "SYNTH-C1", "alpha"])
        legacy.pop("field_semantics")
        legacy.pop("tool_unit_or_kind")
        self.assertTrue(verify_statement(self.store, legacy)["valid"])

    def test_verifier_does_not_call_generator_to_validate_units(self):
        claim = make_statement(self.store, self.entry.task_id, ["frequency_resolution_hz"])
        wrong = copy.deepcopy(claim)
        wrong["unit_or_kind"] = "V²"
        wrong["text"] = _render(wrong)
        with patch("eeg_harness.applications.evidence_statement.make_statement", return_value=wrong) as generator:
            self.assertTrue(verify_statement(self.store, claim)["valid"])
            self.assertFalse(verify_statement(self.store, wrong)["valid"])
            generator.assert_not_called()

    def test_unknown_present_field_has_no_fallback_unit(self):
        unexpected = copy.deepcopy(self.entry.result)
        unexpected["new_scalar"] = 17
        with self.assertRaises(UnsupportedResultField):
            result_field_semantics("event_bandpower", ["new_scalar"], unexpected,
                                   parameters=self.scope,
                                   analysis_configuration=self.entry.evidence["analysis_configuration"])
        # A new band is also not scientifically defined by merely appearing in output.
        unexpected["conditions"]["stimulus"]["channels"]["SYNTH-C1"]["unknown_band"] = 1.0
        with self.assertRaises(UnsupportedResultField):
            result_field_semantics("event_bandpower", ["conditions", "stimulus", "channels", "SYNTH-C1", "unknown_band"], unexpected,
                                   parameters=self.scope,
                                   analysis_configuration=self.entry.evidence["analysis_configuration"])

    def test_actual_value_type_checked_independently_of_claim(self):
        wrong = copy.deepcopy(self.entry.result)
        wrong["conditions"]["stimulus"]["epoch_count"] = 3.5
        with self.assertRaises(UnsupportedResultField):
            result_field_semantics("event_bandpower", ["conditions", "stimulus", "epoch_count"], wrong,
                                   parameters=self.scope,
                                   analysis_configuration=self.entry.evidence["analysis_configuration"])
        wrong["frequency_resolution_hz"] = float("nan")
        with self.assertRaises(UnsupportedResultField):
            result_field_semantics("event_bandpower", ["frequency_resolution_hz"], wrong)


if __name__ == "__main__":
    unittest.main()
