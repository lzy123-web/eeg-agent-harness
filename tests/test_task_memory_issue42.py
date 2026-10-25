"""Offline checks for the frozen Issue #42 workflow and shared read interface."""

from copy import deepcopy
import json
import unittest

from eeg_harness.research.task_memory_issue42 import (
    _attributed_in_answer, _scope_for_read, build_same_history, history_turn, load_spec,
    offline_preflight, run_workflow, score_history,
)
from eeg_harness.research.task_memory_v2 import independent_oracle


class FakeClient:
    def __init__(self, messages):
        self.messages = list(messages)
        self.request_count = 0
        self.total_usage = {"total_tokens": 0}
        self.context = {}

    def set_context(self, **context):
        self.context = context

    def complete(self, messages, tools, tool_choice="auto"):
        self.request_count += 1
        self.total_usage["total_tokens"] += 100
        return self.messages.pop(0)


def action(**arguments):
    return {"tool_calls": [{"function": {"name": "submit_evidence_action",
                                         "arguments": json.dumps(arguments)}}]}


class Issue42Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec()
        cls.scripts = {item["id"]: item for item in cls.spec["workflows"]}

    def test_protocol_preflight_executes_real_tools_and_oracles(self):
        rows = offline_preflight(self.spec)
        self.assertEqual([row["workflow"] for row in rows],
                         ["D-short", "C-continuous", "C-mixed"])
        self.assertEqual([row["analysis_tasks"] for row in rows], [1, 4, 4])
        self.assertEqual([row["history_turns"] for row in rows], [1, 2, 2])

    def test_shared_comparison_scope_blocks_erasure_and_wrong_record(self):
        script = self.scripts["C-mixed"]
        session, keys = build_same_history(script, 3)
        query = script["turns"][3]["text"]
        event = keys["a_pulse"]
        continuous = keys["a_cont"]
        self.assertIsNone(_scope_for_read(session, event, query, "alpha"))
        self.assertIsNone(_scope_for_read(session, event, query,
                                           "A 的连续记录 0 到 2 秒"))
        self.assertIsNotNone(_scope_for_read(session, event, query,
                                               "A 的 pulse 事件后 0 到 1 秒"))
        self.assertIsNotNone(_scope_for_read(session, continuous, query,
                                               "A 的连续记录 0 到 2 秒"))

    def test_multi_evidence_read_and_independent_science_screen(self):
        script = self.scripts["C-continuous"]
        session, keys = build_same_history(script, 2)
        query = script["turns"][2]
        a, b = keys["a_old"], keys["b_rms"]
        value_a = independent_oracle(session.records["A"], script["turns"][0],
                                     ["SYNTH-C1", "rms"])
        value_b = independent_oracle(session.records["B"], script["turns"][1],
                                     ["SYNTH-C1", "rms"])
        client = FakeClient([{"tool_calls": [
            {"function": {"name": "submit_evidence_action", "arguments": json.dumps({
                "operation": "read_fields", "task_id": a.task_id,
                "field_paths": [["SYNTH-C1", "rms"]],
                "scope_quote": "A 的 SYNTH-C1 在 0 到 2 秒"})}},
            {"function": {"name": "submit_evidence_action", "arguments": json.dumps({
                "operation": "read_fields", "task_id": b.task_id,
                "field_paths": [["SYNTH-C1", "rms"]],
                "scope_quote": "B 的 SYNTH-C1 在 0 到 2 秒"})}},
        ]}, {"content": f"A: {value_a:.12g} V；B: {value_b:.12g} V。A 更大。"}])
        observed = history_turn(session, "HC", query["text"], client)
        self.assertEqual(observed["status"], "answered")
        self.assertEqual([item["status"] for item in observed["reads"]],
                         ["read_fields", "read_fields"])
        scored = score_history(session, query, deepcopy(observed), keys,
                               {turn["key"]: turn for turn in script["turns"]
                                if "key" in turn})
        self.assertTrue(scored["science_valid_screen"])
        self.assertEqual(client.request_count, 2)

    def test_invalid_quote_does_not_read_or_restore(self):
        script = self.scripts["C-mixed"]
        session, keys = build_same_history(script, 3)
        query = script["turns"][3]["text"]
        client = FakeClient([action(operation="read_full", task_id=keys["a_pulse"].task_id,
                                    scope_quote="A 的连续记录 0 到 2 秒")])
        observed = history_turn(session, "HC", query, client)
        self.assertEqual(observed["reads"][0]["code"], "INVALID_SCOPE_QUOTE")
        self.assertEqual(session.full_reads, 0)

    def test_swapped_record_values_are_not_counted_correct(self):
        script = self.scripts["C-continuous"]
        a, b = script["turns"][0], script["turns"][1]
        session, _ = build_same_history(script, 2)
        value_a = independent_oracle(session.records["A"], a, ["SYNTH-C1", "rms"])
        value_b = independent_oracle(session.records["B"], b, ["SYNTH-C1", "rms"])
        swapped = f"A: {value_b:.12g} V；B: {value_a:.12g} V"
        self.assertFalse(_attributed_in_answer(swapped, value_a, a, [a, b]))
        self.assertFalse(_attributed_in_answer(swapped, value_b, b, [a, b]))

    def test_complete_short_workflow_fake_model_and_no_gold_prompt(self):
        script = self.scripts["D-short"]
        session, _ = build_same_history(script, 1)
        scalar = independent_oracle(session.records["A"], script["turns"][0],
                                    ["SYNTH-C1", "rms"])
        client = FakeClient([
            {"tool_calls": [{"function": {"name": "submit_memory_action",
                                         "arguments": json.dumps({
                                             "operation": "analyze", "record": "A",
                                             "capability": "amplitude",
                                             "parameters": script["turns"][0]["parameters"]})}}]},
            action(operation="answer", task_id="D-short-t1",
                   answer=f"A 0 到 2 秒 SYNTH-C1 RMS 为 {scalar:.12g} V。"),
        ])
        rows = run_workflow(script, "S", client)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["score"]["science_valid_screen"] for row in rows))
        self.assertEqual(client.request_count, 2)
        self.assertFalse(client.messages)


if __name__ == "__main__":
    unittest.main()
