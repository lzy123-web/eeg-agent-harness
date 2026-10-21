import json
import unittest

from eeg_harness.llm import DeterministicGoalFakeLLM
from eeg_harness.planning_agent import NaturalLanguagePlanningAgent
from eeg_harness.planning_evaluation import make_synthetic_context
from eeg_harness.pipeline import load_config


CONFIG = load_config("config/baseline.json")


def run(text, variant="native_events"):
    context = make_synthetic_context(variant, "nl-agent", CONFIG)
    fake = DeterministicGoalFakeLLM()
    result = NaturalLanguagePlanningAgent(fake, context).run(text)
    return result, fake


class PlanningAgentTest(unittest.TestCase):
    def test_basic_information_window_and_bandpower(self):
        for text, tool in (
            ("给出基础信息", "record_info"),
            ("分析第一个通道的窗口幅值", "amplitude"),
            ("计算频带功率", "psd"),
        ):
            result, _ = run(text)
            self.assertEqual(result.stop_reason, "completed")
            self.assertEqual(result.execution["tool_results"][-1]["tool_name"], tool)

    def test_event_epoch_summary_and_combination(self):
        event, _ = run("分析事件频带功率")
        summary, _ = run("生成 epoch 摘要")
        combined, _ = run("组合执行：先幅值再事件")
        self.assertEqual(event.stop_reason, "completed")
        self.assertEqual(summary.stop_reason, "completed")
        self.assertEqual(summary.execution["tool_results"][-1]["tool_name"], "epoch_summary")
        self.assertEqual(len(combined.execution["tool_results"]), 4)

    def test_no_annotations_is_execution_rejection_not_parse_failure(self):
        result, _ = run("分析事件", "native_no_events")
        self.assertTrue(result.interpretation["success"])
        self.assertEqual(result.stop_reason, "rejected")

    def test_model_incompatibility_and_missing_resource_are_separate(self):
        incompatible, _ = run("调用癫痫模型", "native_events")
        missing, _ = run("调用癫痫模型", "tuev")
        self.assertEqual(incompatible.stop_reason, "rejected")
        self.assertIn("incompatible", incompatible.execution["plan"]["reason"]["message"])
        self.assertEqual(missing.stop_reason, "rejected")
        self.assertIn("resource", missing.execution["plan"]["reason"]["message"])

    def test_unsupported_diagnosis_is_safely_rejected(self):
        result, _ = run("请给出临床诊断")
        self.assertTrue(result.interpretation["success"])
        self.assertEqual(result.stop_reason, "rejected")
        self.assertEqual(result.execution["plan"]["reason"]["code"], "UNSUPPORTED_GOAL")

    def test_invalid_model_output_is_reported_without_execution(self):
        result, _ = run("__INVALID__")
        self.assertEqual(result.stop_reason, "intent_parse_error")
        self.assertIsNone(result.execution)
        json.dumps(result.to_dict(), ensure_ascii=False, allow_nan=False)

    def test_external_prompt_contains_no_raw_array_path_or_artifact_id(self):
        _, fake = run("给出基础信息")
        system = fake.calls[0]["messages"][0]["content"]
        self.assertNotIn("synthetic://", system)
        self.assertNotIn("artifact_id", system)
        self.assertNotIn("[[", system)


if __name__ == "__main__":
    unittest.main()
