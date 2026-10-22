import json
import os
from pathlib import Path
import unittest
import tempfile

import numpy as np
import mne

from eeg_harness.agent import EEGAgent
from eeg_harness.agent_cli import main as agent_cli_main
from eeg_harness.context import ExecutionContext
from eeg_harness.edf import load_edf
from eeg_harness.executor import Executor
from eeg_harness.events import events_from_mne_raw
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


def event_context():
    sfreq = 64.0
    times = np.arange(0, 5, 1 / sfreq)
    data = np.vstack([np.sin(2 * np.pi * 10 * times)]).astype(np.float32)
    raw = mne.io.RawArray(data, mne.create_info(["C1"], sfreq, "eeg"), verbose=False)
    raw.set_annotations(mne.Annotations([1.0, 3.0], [0, 0], ["stimulus", "stimulus"]))
    record = EEGRecord(
        data=data,
        sfreq=sfreq,
        channel_names=("C1",),
        reference="native",
        montage="native",
        source="memory://agent-events",
        metadata={"profile_id": "edf_native"},
        events=events_from_mne_raw(raw, "memory://agent-events"),
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

    def test_multiple_independent_tool_calls_in_one_assistant_message(self):
        class ParallelFake:
            def complete(self, messages, tools):
                if messages[-1]["role"] == "tool":
                    return {"role": "assistant", "content": "两项分析均已完成。"}
                return {
                    "role": "assistant", "content": None,
                    "tool_calls": [
                        {"id": "multi-a", "type": "function", "function": {
                            "name": "amplitude",
                            "arguments": '{"channels":["C1"],"start":0,"end":1}',
                        }},
                        {"id": "multi-b", "type": "function", "function": {
                            "name": "psd",
                            "arguments": '{"channels":["C1"],"start":0,"end":1}',
                        }},
                    ],
                }

        result = EEGAgent(ParallelFake(), native_context()).run("同时分析两类基础特征")
        self.assertEqual(result.stop_reason, "completed")
        self.assertEqual([item["tool_name"] for item in result.tool_results], ["amplitude", "psd"])
        self.assertTrue(all(item["success"] for item in result.tool_results))

    def test_event_request_runs_four_tool_chain(self):
        result = EEGAgent(DemoFakeLLM(), event_context()).run("执行事件 Epoch 分析")
        self.assertEqual(result.stop_reason, "completed")
        self.assertEqual(
            [item["tool_name"] for item in result.tool_results],
            ["list_events", "create_epochs", "epoch_summary", "event_bandpower"],
        )
        self.assertTrue(all(item["success"] for item in result.tool_results))
        self.assertNotIn("data", result.tool_results[1]["data"])

    def test_synthetic_agent_cli_needs_no_edf(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "agent.json"
            self.assertEqual(agent_cli_main([
                "--demo-synthetic", "--fake", "--request", "分析频带功率",
                "--output", str(output),
            ]), 0)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["tool_results"][0]["tool_name"], "psd")
            self.assertTrue(payload["tool_results"][0]["success"])
            self.assertEqual(payload["execution_trace"]["profile_id"], "edf_native")

    def test_openai_client_omits_tool_fields_for_goal_interpretation(self):
        from unittest.mock import patch
        from eeg_harness.llm import OpenAICompatibleClient

        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return b'{"choices":[{"message":{"content":"{}"}}]}'

        captured = {}
        def fake_urlopen(http_request, timeout):
            captured.update(json.loads(http_request.data.decode("utf-8")))
            return Response()

        with patch("eeg_harness.llm.request.urlopen", fake_urlopen):
            OpenAICompatibleClient("https://example.invalid", "secret", "model").complete(
                [{"role": "user", "content": "x"}], []
            )
        self.assertNotIn("tools", captured)
        self.assertNotIn("tool_choice", captured)


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
