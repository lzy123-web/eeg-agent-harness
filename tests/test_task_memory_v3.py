"""Task-episode lifecycle and scientific evidence restoration checks."""

import json
import contextlib
import io
import unittest

from eeg_harness.research.task_memory_eval import (PROTOCOL_V2, main,
                                                    run_paired_v3)
from eeg_harness.research.task_memory_v2 import build_protocol_session, protocol_records
from eeg_harness.research.task_memory_v3 import (
    EpisodeMemorySession, live_turn_v3, replay_protocol_v3,
    scientific_read_mismatch, select_context_v3,
)


class FakeClient:
    def __init__(self, action):
        self.action = action

    def complete(self, messages, tools, tool_choice="auto"):
        return {"tool_calls": [{"function": {
            "name": "submit_memory_action", "arguments": json.dumps(self.action)}}]}


class SequenceFake:
    def __init__(self, actions):
        self.actions = iter(actions)

    def complete(self, messages, tools, tool_choice="auto"):
        return FakeClient(next(self.actions)).complete(messages, tools, tool_choice)


class TaskEpisodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scripts = json.loads(PROTOCOL_V2.read_text(encoding="utf-8"))["sessions"]

    def test_real_tool_completion_archives_task_with_original_trace(self):
        script = self.scripts[0]
        session = EpisodeMemorySession("episode", protocol_records(script))
        step = script["steps"][0]
        result = session.analyze(step["record"], step["capability"],
                                 step["parameters"], step["text"])
        self.assertEqual(result["status"], "completed")
        self.assertIsNone(session.active_task)
        self.assertEqual([event["event"] for event in session.lifecycle],
                         ["started", "archived"])
        self.assertTrue(session.entries[0].tool_trace)
        self.assertEqual(session.entries[0].evidence["source"], session.records["A"].source)
        self.assertEqual(session.task_summaries[result["task_id"]]["read_task_id"],
                         result["task_id"])

    def test_blocked_task_preserves_observation_and_resumes_only_same_goal(self):
        script = self.scripts[0]
        session = EpisodeMemorySession("repair", protocol_records(script))
        step = script["steps"][0]
        bad = session.analyze("A", "psd", {**step["parameters"],
                                           "channels": ["NOT-A-CHANNEL"]}, "先分析")
        self.assertNotEqual(bad["status"], "completed")
        self.assertEqual(session.active_task["state"], "blocked")
        self.assertFalse(session.entries)
        self.assertFalse(session.task_summaries)
        active = select_context_v3(session, "继续分析", "H")["payload"]["active_task"]
        self.assertEqual(active["attempts"][0]["status"], bad["status"])
        good = session.analyze("A", "psd", step["parameters"], "修正通道后继续")
        self.assertEqual(good["status"], "completed")
        self.assertIsNone(session.active_task)
        self.assertEqual(session.lifecycle[-1]["attempt_count"], 2)
        self.assertEqual(len(session.entries), 1)

    def test_completed_index_and_scientific_version_group_are_observed(self):
        session, keys = build_protocol_session(
            self.scripts[2], session_class=EpisodeMemorySession)
        text = self.scripts[2]["queries"][0]["text"]
        direct = select_context_v3(session, text, "H")
        adapted = select_context_v3(session, text, "HE")
        self.assertEqual(direct["archive_count"], 7)
        self.assertTrue(direct["summary_triggered"])
        self.assertEqual(len(direct["payload"]["completed_index"]), 7)
        groups = adapted["payload"]["scientific_object_groups"]
        lineage = [group for group in groups
                   if {keys["a_power_old"].task_id, keys["a_power_new"].task_id}
                   <= {version["task_id"] for version in group["versions"]}]
        self.assertEqual(len(lineage), 1)
        self.assertNotEqual(lineage[0]["versions"][0]["window"],
                            lineage[0]["versions"][1]["window"])
        self.assertNotIn("target_key", json.dumps(adapted["payload"]))

    def test_live_history_restores_original_evidence_then_switch_clears_focus(self):
        session, keys = build_protocol_session(
            self.scripts[0], session_class=EpisodeMemorySession)
        target = keys["a_power"]
        count = len(session.entries)
        observed = live_turn_v3(session, "HE", "回顾 A 的连续频带功率 alpha",
                                FakeClient({"operation": "history",
                                            "task_id": target.task_id}))
        self.assertEqual(observed["outcome"]["status"], "read")
        self.assertEqual(observed["outcome"]["result"], target.result)
        self.assertEqual(observed["outcome"]["tool_trace"], list(target.tool_trace))
        self.assertEqual(len(session.entries), count)  # no repeated EEG calculation
        next_context = select_context_v3(session, "再看该结果", "HE")
        self.assertEqual(next_context["payload"]["focused_evidence"]["task_id"],
                         target.task_id)
        self.assertEqual(session.evidence_reads, 1)
        session.switch("B", "切换 B")
        self.assertIsNone(select_context_v3(session, "新任务", "HE")
                          ["payload"]["focused_evidence"])

    def test_fake_multi_turn_analysis_revision_and_history_use_real_executor(self):
        script = self.scripts[2]
        session = EpisodeMemorySession("loop", protocol_records(script))
        old_step = script["steps"][0]
        new_step = script["steps"][6]
        old = live_turn_v3(session, "HE", old_step["text"],
                           FakeClient({"operation": "analyze", "record": "A",
                                       "capability": "psd",
                                       "parameters": old_step["parameters"]}))
        self.assertEqual(old["outcome"]["status"], "completed")
        parent_id = old["outcome"]["task_id"]
        revised = live_turn_v3(session, "HE", new_step["text"],
                               FakeClient({"operation": "revise", "record": "A",
                                           "capability": "psd",
                                           "parameters": new_step["parameters"],
                                           "parent_task_id": parent_id}))
        self.assertEqual(revised["outcome"]["status"], "completed")
        self.assertEqual(session.entries[-1].revision_of, parent_id)
        past = live_turn_v3(session, "HE", "最初 A 的 SYNTH-C1 连续功率 alpha 是多少？",
                            FakeClient({"operation": "history", "task_id": parent_id}))
        self.assertEqual(past["outcome"]["status"], "read")
        self.assertEqual(past["outcome"]["result"], session.entries[0].result)
        self.assertEqual(len(session.entries), 2)

    def test_shared_read_guard_rejects_wrong_record_event_and_version(self):
        session, keys = build_protocol_session(
            self.scripts[1], session_class=EpisodeMemorySession)
        old = keys["a_cue_count_old"]
        self.assertEqual(scientific_read_mismatch(session, old, "B 的 cue 试次数"),
                         "record")
        self.assertEqual(scientific_read_mismatch(session, old, "A 的 rest 事件试次数"),
                         "event_labels")
        self.assertEqual(scientific_read_mismatch(session, old, "修改后 A 的 cue 试次数"),
                         "version")
        wrong = session.read_task(old.task_id, "A 的 rest 事件试次数")
        self.assertEqual(wrong["code"], "SCIENTIFIC_SCOPE_MISMATCH")
        self.assertIsNone(session.focused_task_id)
        self.assertEqual(session.read_task(old.task_id, "修改前 A 的 cue 试次数")
                         ["status"], "read")

    def test_shared_read_guard_checks_channel_window_and_analysis_scope(self):
        session, keys = build_protocol_session(
            self.scripts[0], session_class=EpisodeMemorySession)
        power = keys["a_power"]
        self.assertEqual(scientific_read_mismatch(
            session, power, "A 的 SYNTH-C2 连续功率"), "channels")
        self.assertEqual(scientific_read_mismatch(
            session, power, "A 的 SYNTH-C1 连续功率 3 到 5 秒"), "window")
        self.assertEqual(scientific_read_mismatch(
            session, power, "A 的事件功率"), "analysis_scope")

    def test_same_history_replay_preserves_independent_oracle(self):
        for script in self.scripts:
            for row in replay_protocol_v3(script):
                self.assertTrue(all(query["target_read_correct"]
                                    for query in row["queries"]))
                self.assertEqual(len(row["lifecycle"]), 2 * len(script["steps"]))

    def test_paired_runner_uses_common_actions_and_real_tool_results(self):
        script = self.scripts[0]
        actions = [{"operation": "analyze", "record": step["record"],
                    "capability": step["capability"],
                    "parameters": step["parameters"]} for step in script["steps"]]
        actions += [{"operation": "history", "task_id": f"{script['id']}-t{index}"}
                    for index in (1, 3)]
        observed = run_paired_v3({"sessions": [script]}, SequenceFake(actions),
                                 policies=("HE",))
        self.assertEqual(len(observed), 5)
        self.assertTrue(all(item["score"]["valid"] for item in observed))
        self.assertEqual(observed[-1]["outcome"]["status"], "read")
        self.assertEqual(observed[-1]["evidence_reads"], 2)

    def test_paid_v3_requires_explicit_gate_before_loading_client(self):
        for argv in (["--mode", "real-v3"],
                     ["--mode", "real-v3", "--enable-paid-v3"]):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main(argv)
            self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
