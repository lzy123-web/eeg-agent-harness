import json
from pathlib import Path
import unittest

from eeg_harness.research.goal_completeness.evaluation import evaluate_protocol
from eeg_harness.research.goal_completeness.matcher import compare_contracts
from eeg_harness.research.goal_completeness.models import ScientificContract
from eeg_harness.research.goal_completeness.protocol import (
    FROZEN_PROTOCOL_SHA256,
    generate_protocol,
    load_protocol,
    parse_controlled_request,
    protocol_digest,
)


PROTOCOL = Path("config/eeg_goal_completeness_cases_v1.json")


class ControlledGoldProtocolTest(unittest.TestCase):
    def test_frozen_manifest_and_disjoint_template_families(self):
        protocol, digest = load_protocol(PROTOCOL)
        self.assertEqual(FROZEN_PROTOCOL_SHA256, digest)
        self.assertEqual(24, len(protocol["cases"]))
        self.assertEqual(12, sum(c["split"] == "development" for c in protocol["cases"]))
        self.assertEqual(12, sum(c["split"] == "holdout" for c in protocol["cases"]))
        development = set(protocol["split_policy"]["development_families"])
        holdout = set(protocol["split_policy"]["holdout_families"])
        self.assertFalse(development & holdout)
        self.assertFalse(protocol["annotation"]["independent_human_annotation"])
        self.assertFalse(protocol["annotation"]["llm_generated_or_scored"])
        self.assertEqual(digest, protocol_digest(generate_protocol()))

    def test_every_evidence_span_is_exact_and_unique(self):
        protocol, _ = load_protocol(PROTOCOL)
        for case in protocol["cases"]:
            with self.subTest(case=case["id"]):
                for claim in case["source_contract"]["claims"]:
                    self.assertEqual(1, case["request"].count(claim["evidence_span"]))

    def test_controlled_parser_round_trips_all_strong_gold(self):
        protocol, _ = load_protocol(PROTOCOL)
        for case in protocol["cases"]:
            with self.subTest(case=case["id"]):
                gold = ScientificContract.from_dict(case["source_contract"])
                parsed = parse_controlled_request(case["request"])
                gold_dict = gold.to_dict(include_evidence=False)
                parsed_dict = parsed.to_dict(include_evidence=False)
                gold_dict.pop("metadata")
                parsed_dict.pop("metadata")
                self.assertEqual(gold_dict, parsed_dict)

    def test_parser_rejects_free_prose_outside_controlled_grammar(self):
        with self.assertRaises(ValueError):
            parse_controlled_request(
                "Please inspect this EEG and do whatever scientific analysis is suitable.")


class CoverageMatcherTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol, _ = load_protocol(PROTOCOL)

    def _fault_case(self, fault_type):
        for case in self.protocol["cases"]:
            candidate = next((item for item in case["candidates"]
                              if item["fault_type"] == fault_type), None)
            if candidate is not None:
                return ScientificContract.from_dict(case["source_contract"]), candidate
        self.fail(f"No candidate for {fault_type}")

    def test_detects_each_registered_fault_type(self):
        expected = {
            "omit_operation": "missing_operation",
            "authorization_conflict": "authorization_conflict",
            "stage_conflict": "stage_conflict",
            "relation_missing": "missing_relation",
            "extra_operation": "extra_operation",
        }
        for fault_type, issue_type in expected.items():
            with self.subTest(fault=fault_type):
                source, candidate = self._fault_case(fault_type)
                report = compare_contracts(
                    source, ScientificContract.from_dict(candidate["contract"]))
                self.assertIn(issue_type, report.issue_types())
                self.assertNotEqual("accept", report.disposition)

    def test_exact_supported_candidate_is_not_unnecessarily_clarified(self):
        case = next(case for case in self.protocol["cases"]
                    if case["source_contract"]["expected_disposition"] == "accept")
        source = ScientificContract.from_dict(case["source_contract"])
        exact = ScientificContract.from_dict(case["candidates"][0]["contract"])
        report = compare_contracts(source, exact)
        self.assertEqual("accept", report.disposition)
        self.assertEqual((), report.issue_types())

    def test_unsupported_source_goal_is_rejected_even_when_candidate_matches(self):
        case = next(case for case in self.protocol["cases"]
                    if case["source_contract"]["expected_disposition"] == "reject")
        source = ScientificContract.from_dict(case["source_contract"])
        exact = ScientificContract.from_dict(case["candidates"][0]["contract"])
        report = compare_contracts(source, exact)
        self.assertEqual("reject", report.disposition)
        self.assertIn("unsupported_operation", report.issue_types())

    def test_report_is_json_serializable(self):
        source, candidate = self._fault_case("authorization_conflict")
        report = compare_contracts(
            source, ScientificContract.from_dict(candidate["contract"]))
        json.dumps(report.to_dict(), ensure_ascii=False, allow_nan=False)


class OfflineEvaluationTest(unittest.TestCase):
    def test_dry_run_has_no_llm_and_detects_registered_perturbations(self):
        result = evaluate_protocol(PROTOCOL)
        summary = result["summary"]
        self.assertFalse(result["uses_llm"])
        self.assertFalse(result["uses_eeg_waveforms"])
        self.assertEqual(24, summary["controlled_requests"])
        self.assertEqual(48, summary["candidate_pairs"])
        self.assertEqual(24, summary["fault_pairs"])
        self.assertEqual(24, summary["parser_contract_exact"])
        self.assertEqual(24, summary["oracle_primary_fault_detected"])
        self.assertEqual(24, summary["controlled_primary_fault_detected"])
        self.assertEqual(0, summary["exact_accept_false_clarify"])


if __name__ == "__main__":
    unittest.main()
