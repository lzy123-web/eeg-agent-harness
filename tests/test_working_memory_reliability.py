"""Issue47: shared progress guard and bounded current evidence, real tools."""
import json
import unittest

from eeg_harness.working_memory_agent import WorkingMemoryEEGAgent, WorkingMemoryController
from eeg_harness.working_memory_deliveries import MultiResultWorkingMemoryStore
from eeg_harness.research.task_memory import synthetic_records
from eeg_harness.tooling import ToolRequest
from test_working_memory import ScriptedClient, finish

W = {"channels": ["SYNTH-C1"], "start": 0, "end": 2}


class ReliabilityTest(unittest.TestCase):
    def test_four_different_goals_close_and_deliver_same_turn_both_modes(self):
        for mode in ("single", "multi_result"):
            with self.subTest(mode=mode):
                actions = []
                for i in range(4):
                    scope = dict(W, end=2+i)
                    contract = ({"deliveries": [{"key": "a", "tool": "amplitude", "scope": scope}]} if mode == "multi_result"
                                else {"deliverable": "amplitude", "scope": scope})
                    actions += [("begin_subgoal", {"title": f"窗口{i}", "record": "A", **contract}),
                                ("amplitude", scope), ("close_subgoal", {"status": "completed"})]
                agent = WorkingMemoryEEGAgent(ScriptedClient(actions+[finish()]), synthetic_records(), memory_version=mode)
                result = agent.run("比较四个合法窗口")
                self.assertEqual(result.stop_reason, "completed")
                self.assertEqual(sum(g.status == "completed" for g in agent.working_memory.store.subgoals), 4)

    def test_same_target_successful_read_still_bounded(self):
        read = ("read_evidence", {"task_id": "same-t1", "record": "A", "parameters": W})
        agent = WorkingMemoryEEGAgent(ScriptedClient([("psd", W)]+[read]*5), synthetic_records(), session_id="same", memory_version="multi_result")
        self.assertEqual(agent.run("无进展重复").stop_reason, "repeated_action")
        self.assertEqual(len(agent.working_memory.store.entries), 1)

    def archive(self, count=10):
        store = MultiResultWorkingMemoryStore("many", synthetic_records())
        for i in range(count):
            store.execute_numeric("psd", dict(W, end=2+i*.1))
        return store

    def test_many_archived_results_new_turn_and_earliest_field_read(self):
        store = self.archive()
        controller = WorkingMemoryController(store)
        controller.begin_turn("读取最早窗口alpha")
        payload = json.loads(controller.build_messages()[1]["content"])
        self.assertEqual(payload["exact_evidence"], [])
        self.assertEqual(len(payload["archived_summaries"]), 10)
        self.assertTrue(all("fields" not in r["evidence"] for g in payload["archived_summaries"] for r in g["results"]))
        read = controller.execute(ToolRequest("read_evidence", {"task_id": "many-t1", "record": "A", "parameters": W,
                                                              "field_paths": [["SYNTH-C1", "alpha"]]}, "r1"))
        self.assertTrue(read.success)
        payload = json.loads(controller.build_messages()[1]["content"])
        self.assertEqual(len(payload["exact_evidence"]), 1)
        self.assertEqual(len(payload["exact_evidence"][0]["fields"]), 1)
        self.assertEqual(payload["exact_evidence"][0]["source"], store.entries[0].evidence["source"])
        self.assertEqual(payload["exact_evidence"][0]["revision_of"], None)
        self.assertEqual(len(store.entries), 10)
        controller.execute(ToolRequest("amplitude", W, "a1"))
        self.assertTrue(controller.build_messages())
        self.assertEqual(len(store.entries), 11)

    def test_dependency_and_revision_keep_old_new_together(self):
        store = self.archive()
        controller = WorkingMemoryController(store)
        controller.begin_turn("修订最早功率，并与原结果比较")
        new = dict(W, end=4)
        controller.execute(ToolRequest("begin_subgoal", {"title": "修订", "record": "A", "deliveries": [
            {"key": "new", "tool": "psd", "scope": new, "revision_of": "many-t1"}], "dependencies": ["many-t1"]}, "b"))
        controller.execute(ToolRequest("psd", new, "p"))
        controller.execute(ToolRequest("close_subgoal", {"status": "completed"}, "c"))
        payload = json.loads(controller.build_messages()[1]["content"])
        by_id = {e["task_id"]: e for e in payload["exact_evidence"]}
        self.assertEqual(set(by_id), {"many-t1", "many-t11"})
        self.assertEqual(by_id["many-t1"]["parameters"], W)
        self.assertEqual(by_id["many-t11"]["parameters"], new)
        self.assertEqual(by_id["many-t11"]["revision_of"], "many-t1")

    def test_simultaneously_required_overflow_is_explicit_no_archive_deletion(self):
        store = self.archive()
        controller = WorkingMemoryController(store)
        controller.begin_turn("同时比较九份证据")
        for i, entry in enumerate(store.entries[:9]):
            self.assertTrue(controller.execute(ToolRequest("read_evidence", {"task_id": entry.task_id, "record": entry.record,
                "parameters": entry.parameters, "field_paths": [["SYNTH-C1", "alpha"]]}, str(i))).success)
        self.assertEqual(controller.build_messages(), [])
        self.assertEqual(controller.stop_reason, "evidence_capacity")
        self.assertEqual(len(store.entries), 10)
        controller.begin_turn("改为单项查询")
        self.assertTrue(controller.build_messages())

    def test_history_request_protocol_and_archive_integrity(self):
        fake = ScriptedClient([("psd", W), finish(), ("read_evidence", {"task_id": "paired-t1", "record": "A", "parameters": W}), finish()])
        agent = WorkingMemoryEEGAgent(fake, synthetic_records(), session_id="paired", memory_version="multi_result")
        agent.run("第一次分析")
        original = json.dumps(agent.working_memory.store.entries[0].result)
        self.assertEqual(agent.continue_run("查询旧窗口").stop_reason, "completed")
        self.assertEqual(original, json.dumps(agent.working_memory.store.entries[0].result))
        self.assertEqual(json.loads(fake.seen[2][1]["content"])["exact_evidence"], [])
        first = json.loads(fake.seen[1][1]["content"])["exact_evidence"][0]
        second = json.loads(fake.seen[-1][1]["content"])["exact_evidence"][0]
        self.assertTrue(first["acquired_this_turn"])
        self.assertFalse(second["acquired_this_turn"])
        self.assertEqual(first["created_turn"], second["created_turn"])
        self.assertEqual(second["created_turn"], 1)
        for messages in fake.seen:
            pending = set()
            for m in messages:
                if m["role"] == "assistant":
                    pending.update(c["id"] for c in m.get("tool_calls", []))
                elif m["role"] == "tool":
                    self.assertIn(m["tool_call_id"], pending)
                    pending.remove(m["tool_call_id"])
            self.assertFalse(pending)


if __name__ == "__main__":
    unittest.main()
