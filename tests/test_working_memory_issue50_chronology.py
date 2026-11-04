"""Regression for the actual Issue50 development continuation failure."""
import json
import unittest

from eeg_harness.research.task_memory import synthetic_records
from eeg_harness.working_memory_agent import WorkingMemoryEEGAgent
from test_working_memory import ScriptedClient, finish


class ManagedTurnChronologyTest(unittest.TestCase):
    def test_new_user_boundary_follows_old_finish_and_precedes_new_observations(self):
        for mode in ("full", "summary", "working"):
            with self.subTest(mode=mode):
                text = "请计算记录A的SYNTH-C1在0到2秒的alpha功率。"

                def new_action(messages):
                    self.assertEqual(messages[-1], {"role": "user", "content": text})
                    # Exact request is public conversation state, not an action
                    # selected by the evaluation driver or a new system hint.
                    if mode == "full":
                        self.assertTrue(any(m["role"] == "tool" for m in messages[:-1]))
                    else:
                        self.assertTrue(json.loads(messages[1]["content"])["task_summaries"])
                    return "psd", {"record": "A", "channels": ["SYNTH-C1"], "start": 0, "end": 2}

                def final(messages):
                    boundary = next(i for i,m in enumerate(messages) if m == {"role":"user","content":text})
                    observations = [json.loads(m["content"]) for m in messages[boundary+1:] if m["role"] == "tool"]
                    self.assertEqual([o["tool_name"] for o in observations], ["psd"])
                    self.assertTrue(observations[0]["success"])
                    return "finish_task", {"status":"completed","answer":"实际PSD已得到。"}

                agent = WorkingMemoryEEGAgent(ScriptedClient([
                    ("record_info", {"record":"A"}), finish(), new_action, final]),
                    synthetic_records(), memory_version="managed", context_mode=mode)
                self.assertEqual(agent.run("查看记录A信息。").stop_reason, "completed")
                self.assertEqual(agent.continue_run(text).stop_reason, "completed")


if __name__ == "__main__":
    unittest.main()
