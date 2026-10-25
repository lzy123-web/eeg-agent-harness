"""Issue 43 message-level regressions. Old path is intentionally not changed."""

import json
import unittest

from eeg_harness.research.task_memory_issue42 import build_same_history, history_turn, load_spec


class CapturingClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.sent = []

    def complete(self, messages, tools, tool_choice="auto"):
        self.sent.append(messages)
        return self.responses.pop(0)


def read_action(task_id, path, quote):
    return {"tool_calls": [{"function": {
        "name": "submit_evidence_action", "arguments": json.dumps({
            "operation": "read_fields", "task_id": task_id,
            "field_paths": [path], "scope_quote": quote,
        })}}]}


class OldHandoffReproduction(unittest.TestCase):
    def test_first_visible_result_disappears_from_second_message(self):
        script = next(item for item in load_spec()["workflows"] if item["id"] == "C-mixed")
        session, keys = build_same_history(script, 3)
        visible = keys["a_cont"]
        indexed = keys["a_pulse"]
        client = CapturingClient([
            read_action(indexed.task_id,
                        ["conditions", "pulse", "channels", "SYNTH-C1", "alpha"],
                        "A 的 pulse 事件后 0 到 1 秒"),
            {"content": "部分结果"},
        ])
        observed = history_turn(session, "HC", script["turns"][3]["text"], client)
        self.assertEqual(observed["status"], "answered")
        first = json.loads(client.sent[0][1]["content"])
        last = json.loads(client.sent[1][1]["content"])
        self.assertIn("exact_result", json.dumps(first["memory"], ensure_ascii=False))
        self.assertNotIn("memory", last)
        self.assertNotIn(str(visible.result["SYNTH-C1"]["alpha"]),
                         json.dumps(last, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
