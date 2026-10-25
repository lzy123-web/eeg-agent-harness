"""Deterministic multi-turn memory and shared real-tool tests."""

import json
import unittest

import numpy as np
from scipy.signal import welch

from eeg_harness.research.task_memory import (
    MultiTurnEEGSession, live_turn, load_protocol, replay_session,
    replay_policies, select_context, synthetic_records,
)
from eeg_harness.research.task_memory_eval import score_live_turn


class FakeDecisionClient:
    def __init__(self, actions):
        self.actions = iter(actions)

    def complete(self, messages, tools, tool_choice="auto"):
        action = next(self.actions)
        return {"tool_calls": [{"function": {
            "name": "submit_memory_action", "arguments": json.dumps(action),
        }}]}


class TaskMemoryTests(unittest.TestCase):
    def test_distinct_synthetic_records_and_independent_psd_oracle(self):
        records = synthetic_records()
        self.assertNotEqual(records["A"].source, records["B"].source)
        self.assertFalse(np.array_equal(records["A"].data, records["B"].data))
        session = MultiTurnEEGSession("numeric", records)
        values = []
        for alias in ("A", "B"):
            result = session.analyze(alias, "psd", {
                "channels": ["SYNTH-C1"], "start": 0, "end": 2,
            }, f"analyze {alias}")
            self.assertEqual(result["status"], "completed")
            observed = float(result["result"]["SYNTH-C1"]["alpha"])
            samples = records[alias].slice(0, 2, ["SYNTH-C1"])[0]
            frequencies, density = welch(samples, fs=128.0, nperseg=128)
            band = (frequencies >= 8) & (frequencies <= 13)
            expected = float(np.trapz(density[band], frequencies[band]))
            self.assertTrue(np.isclose(observed, expected, rtol=5e-3, atol=5e-13))
            values.append(observed)
        self.assertNotEqual(values[0], values[1])

    def test_revision_immutable_old_and_new_result(self):
        session = MultiTurnEEGSession("rev")
        one = session.analyze("A", "psd", {"channels": ["SYNTH-C1"], "start": 0,
                                                "end": 2}, "original")
        two = session.analyze("A", "psd", {"channels": ["SYNTH-C1"], "start": 3,
                                                "end": 5}, "revised", revision_of=one["task_id"])
        self.assertEqual(len(session.entries), 2)
        self.assertEqual(session.entries[1].revision_of, one["task_id"])
        self.assertNotEqual(session.read_task(one["task_id"], "old")["result"],
                            session.read_task(two["task_id"], "new")["result"])
        self.assertEqual(session.entries[0].parameters["start"], 0)

    def test_cross_record_artifact_isolation_and_history_read(self):
        session = MultiTurnEEGSession("cross")
        a = session.analyze("A", "epoch_summary", {"labels": ["stimulus"],
                                                      "tmin": 0, "tmax": 1}, "A event")
        session.switch("B", "switch B")
        b = session.analyze("B", "epoch_summary", {"labels": ["control"],
                                                      "tmin": 0, "tmax": 1}, "B event")
        self.assertEqual(a["status"], "completed")
        self.assertEqual(b["status"], "completed")
        self.assertEqual(session.read_task(a["task_id"], "old A")["record"], "A")
        self.assertNotEqual(session.entries[0].evidence["input_binding"],
                            session.entries[1].evidence["input_binding"])

    def test_all_arms_share_history_and_ambiguity_retained(self):
        scripts = load_protocol()["sessions"]
        self.assertEqual(len(scripts), 6)
        for script in scripts:
            rows = replay_policies(script)
            self.assertTrue(all(row["entries"] == rows[0]["entries"] for row in rows))
            for row in rows:
                self.assertTrue(all(item["status"] in {"completed", "switched"}
                                    for item in row["observations"] if "status" in item))
        ambiguous = replay_session(scripts[3], "E")["observations"][-2]
        self.assertEqual(ambiguous["op"], "clarify")

    def test_fake_llm_real_tools_then_shared_history_read(self):
        script = load_protocol()["sessions"][0]
        session = MultiTurnEEGSession("M1")
        client = FakeDecisionClient([
            {"operation": "analyze", "record": "A", "capability": "psd",
             "parameters": script["turns"][0]["parameters"]},
            {"operation": "history", "task_id": "M1-t1"},
        ])
        first = live_turn(session, "G", script["turns"][0]["text"], client)
        self.assertTrue(score_live_turn(script, 0, first)["correct"])
        second = live_turn(session, "G", "刚才那次结果？", client)
        self.assertEqual(second["outcome"]["status"], "read")
        self.assertEqual(second["outcome"]["task_id"], "M1-t1")
        json.dumps(second, ensure_ascii=False, allow_nan=False)

    def test_full_history_and_generic_memory_not_artificially_empty(self):
        session = MultiTurnEEGSession("compare")
        for start in (0, 1, 2, 3):
            session.analyze("A", "amplitude", {"channels": ["SYNTH-C1"],
                                                  "start": start, "end": start + 1},
                            f"幅值 {start}")
        full = select_context(session, "第一次幅值", "F")
        summary = select_context(session, "第一次幅值", "S")
        generic = select_context(session, "第一次幅值", "G")
        eeg = select_context(session, "第一次幅值", "E")
        self.assertEqual(len(full["shown_task_ids"]), 4)
        self.assertIn("full_messages", full["payload"])
        self.assertEqual(len(summary["payload"]["cards"][0]["rolling_summary"]), 1)
        self.assertEqual(len(generic["shown_task_ids"]), 3)
        self.assertEqual(len(eeg["shown_task_ids"]), 3)


if __name__ == "__main__":
    unittest.main()
