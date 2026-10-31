"""Issue48 public native-batch/summary invariants; Fake choices, real tools.

These are mechanism interventions, not autonomous model outcome scores.
"""
import json
import unittest

from eeg_harness.research.task_memory import synthetic_records
from eeg_harness.agent import EEGAgent
from eeg_harness.working_memory import WorkingMemoryStore
from eeg_harness.working_memory_agent import WorkingMemoryEEGAgent
from test_working_memory import ScriptedClient, finish


def batch(*actions):
    return {"role": "assistant", "content": None, "tool_calls": [
        {"id": f"batch-{i}", "type": "function", "function": {
            "name": name, "arguments": json.dumps(args)}}
        for i, (name, args) in enumerate(actions)]}


def begin(record, key):
    return "begin_subgoal", {"title": f"记录{record}的元信息", "record": record,
                              "deliveries": [{"key": key, "tool": "record_info", "scope": {}}]}


class BatchContextTest(unittest.TestCase):
    def agent(self, actions, **kwargs):
        client = ScriptedClient(actions)
        agent = WorkingMemoryEEGAgent(client, synthetic_records(),
                                      session_id="batch", memory_version="lifecycle", **kwargs)
        return agent, client

    def assert_paired(self, messages):
        pending = set()
        for message in messages:
            if message["role"] == "assistant" and message.get("tool_calls"):
                self.assertFalse(pending, "new assistant batch before previous tool results")
                ids = [call["id"] for call in message["tool_calls"]]
                self.assertEqual(len(ids), len(set(ids)))
                pending = set(ids)
            elif message["role"] == "tool":
                self.assertIn(message["tool_call_id"], pending)
                pending.remove(message["tool_call_id"])
        self.assertFalse(pending)

    def test_cross_goal_batch_owns_only_its_calls_and_keeps_original_batch(self):
        actions = [batch(begin("A", "a"), ("record_info", {}),
                         ("close_subgoal", {"status": "completed"}),
                         begin("B", "b"), ("record_info", {}),
                         ("close_subgoal", {"status": "completed"})), finish()]
        agent, client = self.agent(actions)
        result = agent.run("分别查询记录A和记录B的元信息。")
        self.assertEqual(result.stop_reason, "completed")
        store = agent.working_memory.store
        self.assertEqual([e.record for e in store.entries], ["A", "B"])
        original = agent.working_memory.exchanges[0]
        self.assertEqual(len(original[0]["tool_calls"]), 6)
        self.assert_paired(original)
        actual_ids = []
        for goal in store.subgoals:
            ids = []
            for pair in goal.exchanges:
                self.assert_paired(pair)
                ids += [c["id"] for c in pair[0].get("tool_calls", [])]
            actual_ids.append(set(ids))
        self.assertEqual(actual_ids, [{"batch-0", "batch-1", "batch-2"},
                                      {"batch-3", "batch-4", "batch-5"}])
        for messages in client.seen:
            self.assert_paired(messages)

    def test_limit_mid_batch_records_unexecuted_tail_and_preserves_success(self):
        agent, _ = self.agent([batch(("record_info", {}), ("list_events", {}))], max_tool_calls=1)
        result = agent.run("查询A的记录及事件元信息。")
        self.assertEqual(result.stop_reason, "tool_call_limit")
        self.assertEqual(len(agent.working_memory.store.entries), 1)
        self.assertEqual(len(result.tool_results), 2)
        self.assertTrue(result.tool_results[0]["success"])
        self.assertFalse(result.tool_results[1]["success"])
        self.assertTrue(result.tool_results[1]["error"]["code"])
        self.assertNotIn("observation", result.tool_results[1].get("data") or {})
        self.assert_paired(agent.working_memory.exchanges[0])

    def test_plain_agent_limit_preserves_each_call_result(self):
        store = WorkingMemoryStore("plain", synthetic_records())
        client = ScriptedClient([batch(("record_info", {}), ("list_events", {}))])
        agent = EEGAgent(client, store.contexts["A"], max_tool_calls=1)
        result = agent.run("查询当前记录的元信息。")
        self.assertEqual(result.stop_reason, "tool_call_limit")
        self.assertEqual([r["request_id"] for r in result.tool_results], ["batch-0", "batch-1"])
        self.assertTrue(result.tool_results[0]["success"])
        self.assertFalse(result.tool_results[1]["success"])
        self.assertEqual(result.tool_results[1]["error"]["code"], "NOT_EXECUTED")
        self.assertFalse(result.tool_results[1]["data"]["executed"])
        self.assertNotIn("observation", result.tool_results[1]["data"])

    def test_finish_mid_batch_never_executes_later_action(self):
        agent, _ = self.agent([("record_info", {}), batch(finish(), ("list_events", {}))])
        result = agent.run("查询A采样率即可。")
        self.assertEqual(result.stop_reason, "completed")
        self.assertEqual(len(agent.working_memory.store.entries), 1)
        self.assertFalse(result.tool_results[-1]["success"])
        self.assertTrue(result.tool_results[-1]["error"]["code"])
        self.assert_paired(agent.working_memory.exchanges[-1])

    def test_partial_failure_preserved_while_valid_metadata_executes(self):
        agent, client = self.agent([batch(("invented_tool", {}), ("record_info", {})), finish()])
        result = agent.run("查询A元信息。")
        self.assertEqual(result.stop_reason, "completed")
        self.assertFalse(result.tool_results[0]["success"])
        self.assertTrue(result.tool_results[1]["success"])
        self.assertEqual(len(agent.working_memory.store.entries), 1)
        self.assert_paired(agent.working_memory.exchanges[0])
        self.assert_paired(client.seen[-1])

    def test_same_archives_exact_read_and_scientific_guard_in_all_modes(self):
        archived = []
        interfaces = []
        for mode in ("working", "summary", "full"):
            with self.subTest(mode=mode):
                agent, client = self.agent([
                    ("record_info", {}), finish(),
                    ("read_evidence", {"task_id": "batch-t1", "record": "B", "parameters": {},
                                       "field_paths": [["sfreq"]]}),
                    ("read_evidence", {"task_id": "batch-t1", "record": "A", "parameters": {},
                                       "field_paths": [["sfreq"]]}), finish()], context_mode=mode)
                first = agent.run("查询A元信息。")
                self.assertEqual(first.stop_reason, "completed")
                second = agent.continue_run("读取先前A的采样率。")
                self.assertEqual(second.stop_reason, "completed")
                self.assertEqual(second.tool_results[0]["error"]["code"], "EVIDENCE_BINDING_MISMATCH")
                read = second.tool_results[1]
                self.assertTrue(read["success"])
                self.assertEqual(read["data"]["evidence"]["fields"][0]["value"], 128.0)
                entry = agent.working_memory.store.entries[0]
                archived.append((entry.record, entry.parameters, entry.result))
                interfaces.append(agent.working_memory.tool_definitions())
                if mode == "summary":
                    # Strong S already sees small exact historical facts; it is
                    # not forced to read them back in a real model run.
                    payload = json.loads(client.seen[2][1]["content"])
                    fact = payload["generic_summary"][0]["facts"][0]
                    self.assertEqual(fact["task_id"], "batch-t1")
                    self.assertEqual(fact["record"], "A")
                    sfreq = next(f for f in fact["evidence"]["fields"] if f["path"] == ["sfreq"])
                    self.assertEqual(sfreq["value"], 128.0)
                for decision in agent.working_memory.decisions:
                    parts = decision["input_components_bytes"]
                    self.assertTrue({"system", "tool_schema", "user_original", "current_state",
                                     "history_index_or_summary", "exact_evidence",
                                     "active_or_full_trajectory", "restored_trajectory"} <= set(parts))
                    self.assertTrue(all(type(value) is int and value >= 0 for value in parts.values()))
                for messages in client.seen:
                    self.assert_paired(messages)
        self.assertEqual(archived[0], archived[1])
        self.assertEqual(archived[1], archived[2])
        self.assertEqual(interfaces[0], interfaces[1])
        self.assertEqual(interfaces[1], interfaces[2])

    def test_compact_index_preserves_archive_exact_science_and_one_latest_batch(self):
        window = {"channels": ["SYNTH-C1"], "start": 0, "end": 2}
        psd_goal = ("begin_subgoal", {"title": "A的连续功率", "record": "A", "deliveries": [
            {"key": "p", "tool": "psd", "scope": window}]})

        def inspect_and_close(messages):
            # The latest batch spans a closed metadata goal and an active PSD
            # goal: replaying active.exchanges plus pending used to duplicate
            # the active goal's projected subset of this same native batch.
            assistant_batches = [m for m in messages if m["role"] == "assistant"]
            self.assertEqual(len(assistant_batches), 1)
            self.assertEqual([c["id"] for c in assistant_batches[0]["tool_calls"]],
                             [f"batch-{i}" for i in range(5)])
            self.assert_paired(messages)
            controller, store = agent.working_memory, agent.working_memory.store
            payload = json.loads(messages[1]["content"])
            entry = store.entries[-1]
            exact = next(e for e in payload["exact_evidence"] if e["task_id"] == entry.task_id)
            self.assertEqual(exact["record"], "A")
            self.assertEqual(exact["parameters"], window)
            self.assertEqual(exact["source"], entry.evidence["source"])
            self.assertEqual(exact["revision_of"], None)
            field = next(f for f in exact["fields"] if f["path"] == ["SYNTH-C1", "alpha"])
            self.assertEqual(field["value"], entry.result["SYNTH-C1"]["alpha"])
            self.assertEqual(field["semantics"], {"kind": "absolute_band_power", "unit": "V²"})
            compact = payload["active_subgoal"]
            self.assertEqual(compact["results"][0]["readable_fields"],
                             store.summary(store.active)["results"][0]["evidence"]["readable_fields"])
            self.assertNotIn("evidence", compact["results"][0])
            self.assertEqual(len(compact["verified_sources"]["p"]), 1)
            self.assertEqual(set(compact["verified_sources"]["p"][0]["fields"]), set(window))
            # View construction is read-only. Full sources, exact outputs,
            # native exchanges and original contract histories stay outside it.
            before = json.dumps([store.summary(g) for g in store.subgoals], sort_keys=True)
            native_before = json.dumps(controller.exchanges, sort_keys=True)
            controller.build_messages()
            self.assertEqual(before, json.dumps([store.summary(g) for g in store.subgoals], sort_keys=True))
            self.assertEqual(native_before, json.dumps(controller.exchanges, sort_keys=True))
            full = store.summary(store.active)
            self.assertIn("fields", full["results"][0]["evidence"])
            self.assertIn("parameter_sources", full)
            return "close_subgoal", {"status": "completed"}

        actions = [batch(begin("A", "meta"), ("record_info", {}),
                         ("close_subgoal", {"status": "completed"}), psd_goal, ("psd", window)),
                   inspect_and_close, finish()]
        agent, _ = self.agent(actions)
        result = agent.run("记录A的SYNTH-C1在0到2秒计算功率，并查询记录A元信息。")
        self.assertEqual(result.stop_reason, "completed")
        self.assertEqual(len(agent.working_memory.store.entries), 2)

    def test_full_mode_retains_all_native_history_after_new_turn(self):
        window = {"channels": ["SYNTH-C1"], "start": 0, "end": 2}
        agent, client = self.agent([
            ("record_info", {}), ("psd", window), finish(),
            ("read_evidence", {"task_id": "batch-t2", "record": "A", "parameters": window,
                               "field_paths": [["SYNTH-C1", "alpha"]]}), finish()], context_mode="full")
        self.assertEqual(agent.run("记录A的SYNTH-C1在0到2秒计算功率并查询元信息。").stop_reason, "completed")
        old_pairs = json.loads(json.dumps(agent.working_memory.exchanges))
        self.assertEqual(agent.continue_run("查回刚才A窗口的alpha精确值。").stop_reason, "completed")
        self.assertEqual(client.seen[3][2:], [message for pair in old_pairs for message in pair])
        self.assertEqual(agent.working_memory.exchanges[:len(old_pairs)], old_pairs)
        self.assertEqual(len(agent.working_memory.store.entries), 2)
        for messages in client.seen:
            self.assert_paired(messages)


if __name__ == "__main__":
    unittest.main()
