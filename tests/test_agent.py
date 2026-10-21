import json
import os
from pathlib import Path
import unittest

import numpy as np

from eeg_harness.agent import EEGAgent
from eeg_harness.context import ExecutionContext
from eeg_harness.edf import load_edf
from eeg_harness.executor import Executor
from eeg_harness.llm import DemoFakeLLM
from eeg_harness.pipeline import load_config
from eeg_harness.profiles import EDF_NATIVE, TUEV_BIPOLAR_22
from eeg_harness.record import EEGRecord
from eeg_harness.tools import build_default_registry


ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config(ROOT / "config" / "baseline.json")


def native_context():
    record = EEGRecord(
        data=np.ones((2, 512), dtype=np.float32),
        sfreq=256,
        channel_names=("C1", "C2"),
        reference="native",
        montage="native",
        source="memory://agent",
        metadata={"profile_id": "edf_native"},
    )
    return ExecutionContext(record, EDF_NATIVE, Executor(build_default_registry(), CONFIG))


class FakeAgentLoopTest(unittest.TestCase):
    def test_basic_information_request(self):
        fake = DemoFakeLLM()
        result = EEGAgent(fake, native_context()).run("请给出基础 EEG 信息")
        self.assertEqual(result.stop_reason, "completed")
        self.assertEqual(result.tool_results[0]["tool_name"], "record_info")
        self.assertTrue(result.tool_results[0]["success"])
        self.assertNotIn("data", fake.calls[0]["messages"][0]["content"].split("RECORD_METADATA=")[0])
        json.dumps(result.to_dict(), ensure_ascii=False, allow_nan=False)

    def test_band_power_request(self):
        result = EEGAgent(DemoFakeLLM(), native_context()).run("分析频带功率")
        self.assertEqual(result.tool_results[0]["tool_name"], "psd")
        self.assertTrue(result.tool_results[0]["success"])

    def test_profile_rejection_is_reported_without_crash(self):
        result = EEGAgent(DemoFakeLLM(), native_context()).run("调用癫痫模型")
        self.assertEqual(result.tool_calls, 0)
        self.assertIn("不支持", result.final_answer)

    def test_tool_call_limit_stops_repeating_model(self):
        class RepeatingFake:
            def complete(self, messages, tools):
                return {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": f"repeat-{len(messages)}",
                        "type": "function",
                        "function": {"name": "record_info", "arguments": "{}"},
                    }],
                }

        result = EEGAgent(
            RepeatingFake(), native_context(), max_rounds=5, max_tool_calls=2
        ).run("持续调用")
        self.assertEqual(result.stop_reason, "tool_call_limit")
        self.assertEqual(result.tool_calls, 2)


@unittest.skipUnless(
    os.environ.get("EEG_HARNESS_TEST_EDF") and os.environ.get("EEG_HARNESS_MODEL_PATH"),
    "Set EEG_HARNESS_TEST_EDF and EEG_HARNESS_MODEL_PATH for fake-agent model test",
)
class RealResourceFakeAgentTest(unittest.TestCase):
    def test_fake_llm_closes_loop_with_real_seizure_tool(self):
        record = load_edf(os.environ["EEG_HARNESS_TEST_EDF"], TUEV_BIPOLAR_22)
        context = ExecutionContext(
            record,
            TUEV_BIPOLAR_22,
            Executor(
                build_default_registry(),
                CONFIG,
                {"seizure_model": os.environ["EEG_HARNESS_MODEL_PATH"]},
            ),
        )
        result = EEGAgent(DemoFakeLLM(), context).run("检查癫痫活动")
        self.assertEqual(result.stop_reason, "completed")
        self.assertEqual(result.tool_results[0]["tool_name"], "seizure_detection")
        self.assertEqual(
            result.tool_results[0]["data"][0]["FP1-F7"],
            {"Non-seiz": 0.0, "seiz": 1.0},
        )


if __name__ == "__main__":
    unittest.main()
