import json
import unittest

import numpy as np

from eeg_harness.research.extensibility.common import build_context, compile_case, load_cases
from eeg_harness.research.extensibility.candidate import run_ciedg_extension
from eeg_harness.research.extensibility.evaluation import run_experiment
from eeg_harness.research.extensibility.expert import run_expert_extension
from eeg_harness.tooling import ToolRequest


class Point1ExtensibilityTest(unittest.TestCase):
    def test_registered_variance_tool_matches_manual_population_variance(self):
        case = load_cases()["cases"][0]
        context, _ = build_context(case)
        created = context.execute(ToolRequest(
            "create_epochs", {"labels": ["target"], "tmin": 0.0, "tmax": 1.0}, "create",
        ))
        result = context.execute(ToolRequest(
            "epoch_variance", {
                "artifact_id": created.data["artifact_id"],
                "expected_artifact_fingerprint": created.data["artifact_fingerprint"],
            }, "variance",
        ))
        values = context.artifacts[created.data["artifact_id"]].data[:, 0, :].reshape(-1)
        mean = sum(float(value) for value in values) / len(values)
        expected = sum((float(value) - mean) ** 2 for value in values) / len(values)
        self.assertTrue(result.success)
        self.assertTrue(np.isclose(
            result.data["conditions"]["target"]["channels"]["SYNTH-C1"], expected,
        ))
        json.dumps(result.to_dict(), allow_nan=False)

    def test_both_extensions_pass_all_frozen_cases(self):
        report = run_experiment()
        self.assertEqual(report["summary"]["CIEDG+extension"]["passed"], 7)
        self.assertEqual(report["summary"]["strong_dynamic_expert+extension"]["passed"], 7)

    def test_forbidden_selection_remains_on_source_epochs(self):
        case = next(item for item in load_cases()["cases"] if item["id"] == "X03")
        for runner_name in ("candidate", "expert"):
            context, _ = build_context(case)
            task, ledger, plan, check = compile_case(case, context)
            result = (
                run_ciedg_extension(case, context, task, ledger, plan, check)
                if runner_name == "candidate" else run_expert_extension(case, context)
            )
            self.assertEqual(result["status"], "completed")
            self.assertNotIn(
                "select_quality_epochs", [item["tool_name"] for item in result["tool_results"]],
            )
            release = next(item for item in result["release_results"] if item["tool_name"] == "epoch_variance")
            self.assertEqual(release["data"]["conditions"]["target"]["epoch_count"], 3)

    def test_equal_content_recovery_reuses_variance_and_changed_content_recomputes(self):
        cases = {item["id"]: item for item in load_cases()["cases"]}
        for case_id, expected_calls in (("X05", 1), ("X06", 2)):
            for method in ("candidate", "expert"):
                context, _ = build_context(cases[case_id])
                task, ledger, plan, check = compile_case(cases[case_id], context)
                result = (
                    run_ciedg_extension(cases[case_id], context, task, ledger, plan, check)
                    if method == "candidate" else run_expert_extension(cases[case_id], context)
                )
                calls = [
                    item for item in result["tool_results"]
                    if item["tool_name"] == "epoch_variance" and item["success"]
                ]
                self.assertEqual(len(calls), expected_calls)
                release = next(
                    item for item in result["release_results"]
                    if item["tool_name"] == "epoch_variance"
                )
                if case_id == "X05":
                    self.assertEqual(release.get("execution_kind"), "semantic_evidence_reuse")
                else:
                    self.assertIsNone(release.get("execution_kind"))


if __name__ == "__main__":
    unittest.main()
