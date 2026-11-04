"""Review-driven offline memory protocol and scientific read validation."""

from copy import deepcopy
import json
import unittest

from eeg_harness.research.task_memory_eval import PROTOCOL_V2
from eeg_harness.research.task_memory_v2 import (
    build_protocol_session, classify_action_failure, live_turn_v2,
    parse_visible_query, replay_protocol_v2, score_read_semantics,
    score_observed_history_turn, select_context_v2,
)


class FakeClient:
    def __init__(self, action):
        self.action = action

    def complete(self, messages, tools, tool_choice="auto"):
        return {"tool_calls": [{"function": {
            "name": "submit_memory_action",
            "arguments": json.dumps(self.action),
        }}]}


class TaskMemoryV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol = json.loads(PROTOCOL_V2.read_text(encoding="utf-8"))

    def test_protocol_lengths_and_dynamic_event_metadata(self):
        self.assertEqual([len(s["steps"]) for s in self.protocol["sessions"]], [3, 6, 10])
        script = self.protocol["sessions"][1]
        session, _ = build_protocol_session(script)
        labels = {event.label for event in session.records["A"].events.events}
        self.assertEqual(labels, {"cue", "rest"})
        query = parse_visible_query(session, "回顾 A 的 cue 事件试次")
        self.assertEqual(query.event_labels, ("cue",))
        self.assertEqual(query.scientific_scope, "event")
        self.assertEqual(session.records["A"].processing_metadata,
                         session.records["B"].processing_metadata)

    def test_middle_and_long_histories_activate_real_summary_and_selection(self):
        for script in self.protocol["sessions"][1:]:
            session, _ = build_protocol_session(script)
            before = len(session.messages)
            text = script["queries"][0]["text"]
            full = select_context_v2(session, text, "F")
            summary = select_context_v2(session, text, "S")
            generic = select_context_v2(session, text, "G")
            eeg = select_context_v2(session, text, "E")
            self.assertTrue(summary["summary_triggered"])
            self.assertEqual(summary["archive_count"], len(script["steps"]) - 3)
            self.assertEqual(len(full["shown_task_ids"]), len(script["steps"]))
            self.assertEqual(len(summary["shown_task_ids"]), len(script["steps"]))
            self.assertEqual(len(generic["shown_task_ids"]), 3)
            self.assertEqual(len(eeg["shown_task_ids"]), 3)
            self.assertLess(summary["characters"], full["characters"])
            self.assertLess(generic["characters"], summary["characters"])
            self.assertEqual(len(session.messages), before)

    def test_generic_has_temporal_revision_retrieval(self):
        script = self.protocol["sessions"][2]
        session, keys = build_protocol_session(script)
        for query in script["queries"][:2]:
            for policy in ("G", "E", "E-no-science"):
                selection = select_context_v2(session, query["text"], policy)
                self.assertEqual(selection["ranked_task_ids"][0],
                                 keys[query["target"]].task_id)
        for text, key in (("A 的 SYNTH-C1 连续功率 0 到 2 秒", "a_power_old"),
                          ("A 的 SYNTH-C1 连续功率 3 到 5 秒", "a_power_new")):
            selection = select_context_v2(session, text, "G")
            self.assertEqual(selection["ranked_task_ids"][0], keys[key].task_id)

    def test_semantic_read_checks_scope_source_version_and_independent_value(self):
        script = self.protocol["sessions"][2]
        session, keys = build_protocol_session(script)
        query = script["queries"][1]
        task_id = keys[query["target"]].task_id
        good = session.read_task(task_id, query["text"], record_message=False)
        self.assertTrue(score_read_semantics(session, script, query, keys, task_id)["valid"])
        for field, wrong in (("record", "B"), ("source", "synthetic://wrong"),
                             ("revision_of", None),
                             ("parameters", {"channels": ["SYNTH-C1"],
                                             "start": 0, "end": 2})):
            bad = deepcopy(good)
            bad[field] = wrong
            score = score_read_semantics(session, script, query, keys, task_id,
                                         observed_read=bad)
            self.assertFalse(score["valid"], field)
            self.assertFalse(score["checks"]["revision" if field == "revision_of" else field])
        bad = deepcopy(good)
        bad["result"]["SYNTH-C1"]["alpha"] = "9e9"
        score = score_read_semantics(session, script, query, keys, task_id,
                                     observed_read=bad)
        self.assertFalse(score["valid"])
        self.assertFalse(score["checks"]["value"])

    def test_all_replay_target_reads_match_raw_record_oracle(self):
        for script in self.protocol["sessions"]:
            for row in replay_protocol_v2(script):
                for query in row["queries"]:
                    self.assertTrue(query["target_read"]["valid"])
                    self.assertTrue(query["target_visible"])

    def test_action_and_memory_failures_are_separate(self):
        self.assertEqual(classify_action_failure("analyze", "switch"),
                         "common_action_selection_error")
        self.assertEqual(classify_action_failure("history", "history",
                                                expected_history_written=False),
                         "history_absent_after_prior_failure")
        self.assertEqual(classify_action_failure("history", "history",
                                                target_visible=False),
                         "memory_selection_miss")
        self.assertEqual(classify_action_failure("history", "history",
                                                target_correct=False),
                         "model_read_or_evidence_error")

    def test_live_history_semantics_survive_task_id_shift(self):
        script = self.protocol["sessions"][0]
        # The first scripted analysis failed: the B analysis becomes t1, not t3.
        session = build_protocol_session({**script, "steps": [script["steps"][2]]})[0]
        query = script["queries"][1]
        correct_id = session.entries[0].task_id
        observation = {"action": {"operation": "history", "task_id": correct_id},
                       "shown_task_ids": [correct_id],
                       "outcome": session.read_task(correct_id, query["text"],
                                                    record_message=False)}
        score = score_observed_history_turn(session, script, query, observation)
        self.assertTrue(score["valid"])
        self.assertEqual(score["category"], "correct")
        wrong = {**observation, "action": {"operation": "switch", "record": "B"}}
        self.assertEqual(score_observed_history_turn(session, script, query, wrong)["category"],
                         "common_action_selection_error")
        missing = score_observed_history_turn(session, script, script["queries"][0],
                                              observation)
        self.assertEqual(missing["category"], "history_absent_after_prior_failure")

    def test_fake_agent_uses_v2_selector_and_common_execution(self):
        script = self.protocol["sessions"][0]
        session, keys = build_protocol_session(script)
        target = keys["a_power"]
        answer = live_turn_v2(session, "G", "回顾 A 的连续频带功率 alpha",
                              FakeClient({"operation": "history",
                                          "task_id": target.task_id}))
        self.assertEqual(answer["outcome"]["status"], "read")
        self.assertEqual(answer["outcome"]["record"], "A")
        self.assertEqual(answer["outcome"]["result"], target.result)

    def test_empty_history_analysis_and_pure_record_switch_share_action_interface(self):
        script = self.protocol["sessions"][0]
        session, _ = build_protocol_session({**script, "steps": []})
        self.assertFalse(session.entries)
        switch = live_turn_v2(session, "G", "切换到 B。",
                              FakeClient({"operation": "switch", "record": "B"}))
        self.assertEqual(switch["outcome"], {"status": "switched", "record": "B"})
        step = script["steps"][0]
        analyze = live_turn_v2(session, "E", step["text"],
                               FakeClient({"operation": "analyze",
                                           "record": step["record"],
                                           "capability": step["capability"],
                                           "parameters": step["parameters"]}))
        self.assertEqual(analyze["outcome"]["status"], "completed")
        self.assertEqual(len(session.entries), 1)


if __name__ == "__main__":
    unittest.main()
