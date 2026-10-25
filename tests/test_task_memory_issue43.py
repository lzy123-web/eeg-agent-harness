"""Issue 43 message-level regressions. Old path is intentionally not changed."""

import json
import unittest

from eeg_harness.research.task_memory_issue42 import build_same_history, history_turn, load_spec
from eeg_harness.research.task_memory_issue43 import (
    history_turn as repaired_turn, load_spec as new_spec, offline_preflight,
    score_history as repaired_score, select_context43,
)
from eeg_harness.research.task_memory_evidence import bind_read_scope
from eeg_harness.research.task_memory_evidence import scalar_paths
from eeg_harness.research.task_memory_evidence import merge_evidence


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


def actions(*items):
    return {"tool_calls": [{"function": {"name": "submit_evidence_action",
                                      "arguments": json.dumps(item)}} for item in items]}


def scope(record, kind, window, *, condition=None, version=None):
    item = {"record": record, "kind": kind, "window": window}
    if condition:
        item["condition"] = condition
    if version:
        item["version"] = version
    return item


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
        conservative = repaired_score(session, script["turns"][3], observed, keys,
                                      {turn["key"]: turn for turn in script["turns"]
                                       if "key" in turn})
        self.assertFalse(conservative["science_valid_screen"])


class RepairedHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old = {item["id"]: item for item in load_spec()["workflows"]}
        cls.new = {item["id"]: item for item in new_spec()["workflows"]}

    def test_new_real_tool_workflows_and_independent_oracle(self):
        rows = offline_preflight()
        self.assertEqual([(row["workflow"], row["analysis_tasks"])
                          for row in rows], [("N-continuous", 3), ("N-mixed", 4)])

    def test_two_directly_visible_do_not_read(self):
        script = self.old["C-continuous"]
        session, keys = build_same_history(script, 2)
        client = CapturingClient([actions({"operation": "answer", "answer": "两项均见"})])
        observed = repaired_turn(session, "F", script["turns"][2]["text"], client)
        self.assertEqual(len(client.sent), 1)
        self.assertEqual(observed["status"], "answered")
        for entry in keys.values():
            self.assertTrue(any(ref["task_id"] == entry.task_id
                                for ref in observed["final_visible"]))

    def test_visible_plus_new_read_reaches_final_message_with_provenance(self):
        script = self.old["C-mixed"]
        session, keys = build_same_history(script, 3)
        event, continuous = keys["a_pulse"], keys["a_cont"]
        client = CapturingClient([
            actions({"operation": "read_fields", "task_id": event.task_id,
                     "field_paths": [["conditions", "pulse", "channels", "SYNTH-C1", "alpha"]],
                     "scope": scope("A", "event", [0, 1], condition="pulse")}),
            {"content": "已见连续和新读事件的部分结果"},
        ])
        observed = repaired_turn(session, "HC", script["turns"][3]["text"], client)
        self.assertEqual(observed["status"], "answered")
        final = json.loads(client.sent[1][1]["content"])
        self.assertEqual({item["task_id"] for item in final["evidence"]},
                         {event.task_id, continuous.task_id})
        self.assertNotIn("memory", final)
        self.assertNotIn("tool_trace", json.dumps(final))
        by_id = {item["task_id"]: item for item in final["evidence"]}
        self.assertEqual(by_id[continuous.task_id]["source"], continuous.evidence["source"])
        self.assertEqual(by_id[continuous.task_id]["unit_or_kind"], "V²")
        self.assertEqual(by_id[continuous.task_id]["fields"][2]["via"], ["first_visible"])
        self.assertEqual(by_id[event.task_id]["fields"][0]["via"], ["read_fields"])
        self.assertIn(str(continuous.result["SYNTH-C1"]["alpha"]),
                      client.sent[1][1]["content"])

    def test_two_reads_different_records_event_scopes_and_partial_fields(self):
        script = self.old["C-mixed"]
        session, keys = build_same_history(script, 5)
        a, b = keys["a_pulse"], keys["b_click"]
        client = CapturingClient([
            actions(
                {"operation": "read_fields", "task_id": a.task_id,
                 "field_paths": [["conditions", "pulse", "channels", "SYNTH-C1", "alpha"]],
                 "scope": scope("A", "event", [0, 1], condition="pulse")},
                {"operation": "read_fields", "task_id": b.task_id,
                 "field_paths": [["conditions", "click", "channels", "SYNTH-C1", "alpha"]],
                 "scope": scope("B", "event", [0, 1], condition="click")}),
            {"content": "两项 alpha 值"},
        ])
        observed = repaired_turn(session, "HC", script["turns"][5]["text"], client)
        self.assertEqual([read["status"] for read in observed["reads"]],
                         ["read_fields", "read_fields"])
        final = json.loads(client.sent[1][1]["content"])
        for entry, condition in ((a, "pulse"), (b, "click")):
            row = next(item for item in final["evidence"] if item["task_id"] == entry.task_id)
            self.assertEqual(row["record"], entry.record)
            self.assertEqual(row["parameters"]["labels"], [condition])
            self.assertEqual(len(row["fields"]), 1)
            self.assertEqual(row["fields"][0]["path"][-1], "alpha")
            self.assertFalse(any(ref["task_id"] == entry.task_id and
                                 ref["path"][-1] == "beta"
                                 for ref in observed["final_visible"]))

    def test_failed_read_not_promoted_while_successful_one_survives(self):
        script = self.old["C-mixed"]
        session, keys = build_same_history(script, 5)
        a, b = keys["a_pulse"], keys["b_click"]
        client = CapturingClient([
            actions(
                {"operation": "read_fields", "task_id": a.task_id,
                 "field_paths": [["conditions", "pulse", "channels", "SYNTH-C1", "alpha"]],
                 "scope": scope("B", "event", [0, 1], condition="click")},
                {"operation": "read_fields", "task_id": b.task_id,
                 "field_paths": [["conditions", "click", "channels", "SYNTH-C1", "alpha"]],
                 "scope": scope("B", "event", [0, 1], condition="click")}),
            {"content": "B 有值，A 的指定事件值缺失"},
        ])
        observed = repaired_turn(session, "HC", script["turns"][5]["text"], client)
        self.assertEqual(observed["reads"][0]["code"], "SCIENTIFIC_SCOPE_MISMATCH")
        self.assertFalse(any(ref["task_id"] == a.task_id for ref in observed["read_success"]))
        self.assertTrue(any(ref["task_id"] == b.task_id for ref in observed["final_visible"]))
        final = json.loads(client.sent[1][1]["content"])
        self.assertEqual(final["failed_reads"][0]["task_id"], a.task_id)

    def test_versions_deduplicated_and_wrong_scope_rejected(self):
        script = self.new["N-continuous"]
        session, keys = build_same_history(script, 3)
        query = script["turns"][3]["text"]
        old, new = keys["a_early"], keys["a_late"]
        text, error = bind_read_scope(session, old, query,
                                      scope("A", "continuous", [0, 2], version="old"))
        self.assertIsNone(error)
        self.assertIn("修改前", text)
        _, error = bind_read_scope(session, old, query,
                                   scope("A", "continuous", [3, 5], version="new"))
        self.assertEqual(error, "SCIENTIFIC_SCOPE_MISMATCH")
        _, error = bind_read_scope(session, new, query,
                                   scope("A", "continuous", [3, 5]))
        self.assertEqual(error, "VERSION_BINDING_REQUIRED")
        client = CapturingClient([
            actions(
                {"operation": "read_fields", "task_id": old.task_id,
                 "field_paths": [["SYNTH-C1", "alpha"]],
                 "scope": scope("A", "continuous", [0, 2], version="old")},
                {"operation": "read_fields", "task_id": old.task_id,
                 "field_paths": [["SYNTH-C1", "alpha"]],
                 "scope": scope("A", "continuous", [0, 2], version="old")}),
            {"content": "重复读取归并"},
        ])
        observed = repaired_turn(session, "HC", query, client)
        row = next(item for item in json.loads(client.sent[1][1]["content"])["evidence"]
                   if item["task_id"] == old.task_id)
        self.assertEqual(sum(field["path"] == ["SYNTH-C1", "alpha"]
                             for field in row["fields"]), 1)
        self.assertEqual(row["revision_of"], None)

    def test_paths_are_canonical_and_nonexecuted_task_cannot_be_read(self):
        script = self.old["C-mixed"]
        session, keys = build_same_history(script, 3)
        selected = select_context43(session, script["turns"][3]["text"], "HC")
        card = next(item for item in selected["payload"]["working_tasks"]
                    if item["task_id"] == keys["a_pulse"].task_id)
        self.assertIn(["conditions", "pulse", "channels", "SYNTH-C1", "alpha"],
                      card["readable_fields"])
        self.assertNotIn("field_index", card)
        client = CapturingClient([actions({"operation": "read_full",
                                           "task_id": "never-executed"}),
                                  {"content": "仅能报告当前可见值；缺失任务未执行。"}])
        observed = repaired_turn(session, "HC", script["turns"][3]["text"], client)
        self.assertEqual(observed["reads"][0]["code"], "TASK_NOT_FOUND")
        self.assertEqual(len(client.sent), 1 if not observed["first_visible"] else 2)

    def test_public_fix_applies_to_f_s_hc_and_score_uses_last_visible(self):
        script = self.old["C-mixed"]
        for policy in ("F", "S", "HC"):
            with self.subTest(policy=policy):
                session, keys = build_same_history(script, 3)
                event = keys["a_pulse"]
                client = CapturingClient([
                    actions({"operation": "read_fields", "task_id": event.task_id,
                             "field_paths": [["conditions", "pulse", "channels",
                                              "SYNTH-C1", "alpha"]],
                             "scope": scope("A", "event", [0, 1], condition="pulse")}),
                    {"content": "仅报告事件值，连续值未写出。"},
                ])
                observed = repaired_turn(session, policy, script["turns"][3]["text"],
                                         client)
                score = repaired_score(session, script["turns"][3], observed, keys,
                                       {turn["key"]: turn for turn in script["turns"]
                                        if "key" in turn})
                self.assertFalse(score["science_valid_screen"])
                self.assertTrue(score["target_checks"][0]["final_visible"])
                self.assertTrue(score["target_checks"][1]["final_visible"] if
                                policy in ("F", "S", "HC") else False)
                self.assertEqual(len(client.sent), 2)

    def test_multi_object_binding_keeps_count_channel_independent(self):
        script = self.new["N-mixed"]
        session, keys = build_same_history(script, 4)
        query = script["turns"][4]["text"]
        count = keys["a_count"]
        text, reason = bind_read_scope(session, count, query,
                                       scope("A", "event", [0, 1], condition="pulse"))
        self.assertIsNone(reason)
        self.assertNotIn("SYNTH-C1", text)
        _, reason = bind_read_scope(session, count, query,
                                    scope("B", "event", [0, 1], condition="click"))
        self.assertEqual(reason, "SCIENTIFIC_SCOPE_MISMATCH")

    def test_event_label_of_other_object_does_not_poison_continuous_read(self):
        script = self.old["C-mixed"]
        session, keys = build_same_history(script, 3)
        query = script["turns"][3]["text"]
        text, reason = bind_read_scope(session, keys["a_cont"], query,
                                       scope("A", "continuous", [0, 2]))
        self.assertIsNone(reason)
        self.assertNotIn("pulse", text)

    def test_scope_negative_matrix_and_ambiguous_multitarget(self):
        script = self.old["C-mixed"]
        session, keys = build_same_history(script, 5)
        query = script["turns"][5]["text"]
        event = keys["a_pulse"]
        cases = [
            ({}, "RECORD_BINDING_REQUIRED"),
            (scope("A", "continuous", [0, 1], condition="pulse"),
             "SCIENTIFIC_SCOPE_MISMATCH"),
            (scope("A", "event", [0, 1], condition="click"),
             "SCIENTIFIC_SCOPE_MISMATCH"),
            (scope("A", "event", [3, 5], condition="pulse"), "UNREQUESTED_WINDOW"),
            ({**scope("A", "event", [0, 1], condition="pulse"),
              "channel": "NOT-A-CHANNEL"}, "UNREQUESTED_CHANNEL"),
        ]
        for supplied, expected in cases:
            with self.subTest(supplied=supplied):
                _, reason = bind_read_scope(session, event, query, supplied)
                self.assertEqual(reason, expected)
        _, reason = bind_read_scope(session, event, query,
                                    scope("A", "event", [0, 1]))
        self.assertEqual(reason, "CONDITION_BINDING_REQUIRED")

    def test_conflicting_exact_values_cannot_be_merged(self):
        first = [{"task_id": "t1", "record": "A", "source": "synthetic://a",
                  "fields": [{"path": ["alpha"], "value": "1.0", "via": ["first_visible"]}]}]
        second = [{"task_id": "t1", "record": "A", "source": "synthetic://a",
                   "fields": [{"path": ["alpha"], "value": "2.0", "via": ["read_fields"]}]}]
        with self.assertRaisesRegex(ValueError, "Conflicting exact"):
            merge_evidence(first, second)

    def test_partial_field_never_grants_other_field_or_index_number(self):
        script = self.old["C-mixed"]
        session, keys = build_same_history(script, 3)
        event = keys["a_pulse"]
        client = CapturingClient([
            actions({"operation": "read_fields", "task_id": event.task_id,
                     "field_paths": [["conditions", "pulse", "channels", "SYNTH-C1", "alpha"]],
                     "scope": scope("A", "event", [0, 1], condition="pulse")}),
            {"content": "仅 alpha 已读"},
        ])
        observed = repaired_turn(session, "HC", script["turns"][3]["text"], client)
        self.assertFalse(any(ref["task_id"] == event.task_id and ref["path"][-1] == "beta"
                             for ref in observed["final_visible"]))
        self.assertFalse(any(ref["task_id"] == event.task_id
                             for ref in observed["first_visible"]))
        self.assertNotIn(str(event.result["conditions"]["pulse"]["channels"]
                             ["SYNTH-C1"]["beta"]), client.sent[1][1]["content"])

    def test_science_screen_positive_and_swapped_record_negative(self):
        script = self.new["N-continuous"]
        session, keys = build_same_history(script, 3)
        old, late, b = keys["a_early"], keys["a_late"], keys["b_early"]
        a0 = old.result["SYNTH-C1"]["alpha"]
        a1 = late.result["SYNTH-C1"]["alpha"]
        b0 = b.result["SYNTH-C1"]["alpha"]
        refs = [{"task_id": entry.task_id, "path": path}
                for entry in keys.values() for path, _ in scalar_paths(entry.result)]
        base = {"status": "answered", "actions": [{"operation": "answer"}],
                "first_visible": refs, "read_success": [], "final_visible": refs}
        text = (f"记录 A 修改前 0 到 2 秒 alpha={a0} V²；"
                f"记录 A 修改后 3 到 5 秒 alpha={a1} V²；"
                f"记录 B 0 到 2 秒 alpha={b0} V²。")
        by_key = {turn["key"]: turn for turn in script["turns"] if "key" in turn}
        positive = repaired_score(session, script["turns"][3],
                                  {**base, "answer": text}, keys, by_key)
        self.assertTrue(positive["science_valid_screen"])
        swapped = text.replace(f"alpha={a0}", "alpha=PLACEHOLDER", 1).replace(
            f"alpha={b0}", f"alpha={a0}", 1).replace("alpha=PLACEHOLDER",
                                                        f"alpha={b0}", 1)
        negative = repaired_score(session, script["turns"][3],
                                  {**base, "answer": swapped}, keys, by_key)
        self.assertFalse(negative["science_valid_screen"])

    def test_mixed_count_power_amplitude_not_interchangeable(self):
        script = self.new["N-mixed"]
        session, keys = build_same_history(script, 4)
        refs = [{"task_id": entry.task_id, "path": path}
                for entry in keys.values() for path, _ in scalar_paths(entry.result)]
        a = keys["a_event"].result["conditions"]["pulse"]["channels"]["SYNTH-C1"]["alpha"]
        b = keys["b_event"].result["conditions"]["click"]["channels"]["SYNTH-C1"]["alpha"]
        count = keys["a_count"].result["valid_epoch_count"]
        rms = keys["a_rms"].result["SYNTH-C1"]["rms"]
        answer = (f"记录 A pulse 事件后 0 到 1 秒 alpha={a} V²；"
                  f"记录 B click 事件后 0 到 1 秒 alpha={b} V²；"
                  f"记录 A pulse 事件后 0 到 1 秒有效试次数={count} 次；"
                  f"记录 A 连续信号 3 到 5 秒 RMS={rms} V。")
        base = {"status": "answered", "actions": [{"operation": "answer"}],
                "first_visible": refs, "final_visible": refs, "read_success": [],
                "answer": answer}
        by_key = {turn["key"]: turn for turn in script["turns"] if "key" in turn}
        scored = repaired_score(session, script["turns"][4], base, keys, by_key)
        self.assertTrue(scored["science_valid_screen"])
        self.assertFalse(repaired_score(session, script["turns"][4],
                                        {**base, "answer": answer.replace("V²", "V²/Hz")},
                                        keys, by_key)["science_valid_screen"])
        missing = [ref for ref in refs if not (ref["task_id"] == keys["a_count"].task_id
                                             and ref["path"] == ["valid_epoch_count"])]
        self.assertFalse(repaired_score(session, script["turns"][4],
                                        {**base, "final_visible": missing}, keys,
                                        by_key)["science_valid_screen"])


if __name__ == "__main__":
    unittest.main()
