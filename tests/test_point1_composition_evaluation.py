"""Frozen Issue #34 fixtures and independent scientific checks."""

import json
import unittest

from eeg_harness.research.composition_evaluation import (
    _numerical_check, build_fixture, load_protocol, new_context, run_expert,
    score_candidate, score_native,
)
from eeg_harness.research.integrated_method.v3 import (
    GoalInstance, InstanceTaskRequest, run_instances,
)


class CompositionEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = {item["id"]: item for item in load_protocol()["cases"]}

    def test_case_ids_splits_and_json_contract(self):
        protocol = load_protocol()
        self.assertEqual(len(protocol["cases"]), 10)
        self.assertEqual(len({item["id"] for item in protocol["cases"]}), 10)
        self.assertEqual(sum(item["split"] == "holdout" for item in protocol["cases"]), 4)
        self.assertEqual(protocol["external_llm_max_completions"], 24)
        json.dumps(protocol, allow_nan=False)

    def test_independent_expert_uses_real_registry_executor(self):
        for case in self.cases.values():
            result = run_expert(case)
            if case["expected"] == "complete":
                self.assertEqual(result["status"], "completed", case["id"])
                self.assertTrue(result["pass"], case["id"])
            self.assertFalse(any(item["tool_name"] in case["forbid"]
                                 for item in result["tool_results"]), case["id"])

    def test_candidate_structured_path_and_oracle_for_dependency_case(self):
        case = self.cases["D02"]
        context = new_context(case, "test")
        goals = tuple(GoalInstance(f"g{index}", item["capability"], item["parameters"])
                      for index, item in enumerate(case["gold"], 1))
        result = run_instances(context, InstanceTaskRequest(goals, ("selection",)))
        self.assertTrue(score_candidate(case, context, result)["pass"])
        self.assertEqual([item["tool_name"] for item in result["tool_results"]],
                         ["list_events", "create_epochs", "epoch_summary", "event_bandpower"])

    def test_edge_event_and_profile_stops(self):
        self.assertEqual(run_expert(self.cases["H04"])["status"],
                         "safe_stop_zero_valid_epochs")
        self.assertEqual(run_expert(self.cases["D05"])["status"],
                         "not_assessed_no_structured_goal")
        record, _ = build_fixture("native_events_edge")
        self.assertEqual(record.events.events[0].onset_seconds, 7.6)

    def test_independent_oracle_catches_wrong_psd(self):
        case = self.cases["D01"]
        context = new_context(case, "test-oracle")
        valid, _ = _numerical_check(context.record, "psd", case["gold"][0]["parameters"],
                                    {"SYNTH-C1": {"alpha": 999}}, context.executor.config)
        self.assertFalse(valid)

    def test_native_action_score_requires_both_window_instances(self):
        from eeg_harness.tooling import ToolRequest

        case = self.cases["D01"]
        context = new_context(case, "test-native")
        outputs = [context.execute(ToolRequest("psd", item["parameters"], f"n{index}")).to_dict()
                   for index, item in enumerate(case["gold"], 1)]
        result = {"execution_trace": context.trace.to_dict(), "tool_results": outputs,
                  "final_answer": "两段结果", "stop_reason": "completed"}
        self.assertTrue(score_native(case, context, result)["pass_action_numeric"])
        result["tool_results"] = outputs[:1]
        result["execution_trace"]["events"] = result["execution_trace"]["events"][:1]
        self.assertFalse(score_native(case, context, result)["pass_action_numeric"])

    def test_native_combined_epoch_producer_is_legal_alternative_plan(self):
        from eeg_harness.tooling import ToolRequest

        case = self.cases["H01"]
        context = new_context(case, "test-native-combined")
        psd = context.execute(ToolRequest("psd", case["gold"][0]["parameters"], "n1"))
        producer = context.execute(ToolRequest("create_epochs", {
            "labels": ["target", "control"], "tmin": 0, "tmax": 1}, "n2"))
        power = context.execute(ToolRequest("event_bandpower", {
            "artifact_id": producer.data["artifact_id"]}, "n3"))
        result = {"execution_trace": context.trace.to_dict(),
                  "tool_results": [psd.to_dict(), producer.to_dict(), power.to_dict()],
                  "final_answer": "按标签分别报告", "stop_reason": "completed"}
        score = score_native(case, context, result)
        self.assertTrue(score["pass_action_numeric"], score)
        self.assertEqual([item["satisfied"] for item in score["coverage"]],
                         [True, True, True])


if __name__ == "__main__":
    unittest.main()
