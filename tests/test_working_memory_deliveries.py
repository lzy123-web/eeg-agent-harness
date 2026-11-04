"""Controlled actions test mechanisms; they do not establish LLM autonomy."""
from dataclasses import replace
import json
import unittest
from unittest.mock import patch

import numpy as np

from eeg_harness.working_memory import WorkingMemoryStore
from eeg_harness.working_memory_deliveries import MultiResultWorkingMemoryStore
from eeg_harness.working_memory_agent import WorkingMemoryEEGAgent
from eeg_harness.tooling import ToolResult
from eeg_harness.research.task_memory import synthetic_records
from eeg_harness.research.task_memory_v2 import independent_oracle
from test_working_memory import ScriptedClient, artifact_action, finish


W = {"channels": ["SYNTH-C1"], "start": 0, "end": 2}
E = {"labels": ["stimulus"], "tmin": 0, "tmax": 1}


def item(key, tool, scope, **extra):
    return {"key": key, "tool": tool, "scope": scope, **extra}


class DeliveryTest(unittest.TestCase):
    def setUp(self):
        self.store = MultiResultWorkingMemoryStore("multi", synthetic_records())

    def begin(self, items, **extra):
        result = self.store.begin_subgoal("科学目的", "A", deliveries=items, **extra)
        self.assertEqual(result["status"], "active", result)

    def run_tool(self, name, params):
        result = self.store.execute_numeric(name, params)
        self.assertTrue(result["observation"]["result"]["success"], result)
        return result["observation"]["result"]["data"]

    def inject_failure(self, name, params):
        ctx = self.store.contexts["A"]
        with patch.object(ctx.executor, "execute", return_value=ToolResult(
                "injected", name, False, error_code="INJECTED_FAILURE", error_message="offline test")):
            return self.store.execute_numeric(name, params)

    def test_old_failure_reproduced_without_changing_old_mode(self):
        old = WorkingMemoryStore("old", synthetic_records())
        old.begin_subgoal("幅值及功率", "A", "amplitude", W)
        old.execute_numeric("amplitude", W)
        old.execute_numeric("psd", W)
        old.close_subgoal("completed")
        self.assertEqual([e.capability for e in old.entries], ["amplitude"])
        self.assertEqual(len(old.subgoals[0].observations), 2)

    def test_all_results_readable_before_and_after_complete_with_oracle(self):
        self.begin([item("amp", "amplitude", W), item("power", "psd", W)])
        self.run_tool("amplitude", W)
        self.assertFalse(self.store.completion_check(self.store.active)["valid"])
        self.assertEqual(self.store.close_subgoal("completed")["status"], "rejected")
        self.run_tool("psd", W)
        self.run_tool("record_info", {})  # Useful extra, not the only archived result.
        result = self.store.close_subgoal("completed")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["summary"]["results"]), 3)
        self.assertIsNone(self.store.find_entry("multi-s1"))  # No arbitrary terminal alias.
        for entry in self.store.entries:
            self.assertEqual(self.store.read_evidence(entry.task_id, "A", entry.parameters)["status"], "read")
        p = self.store.entries[1]
        oracle = independent_oracle(self.store.records["A"], {"capability": "psd", "parameters": W}, ["SYNTH-C1", "alpha"])
        self.assertTrue(np.isclose(float(p.result["SYNTH-C1"]["alpha"]), oracle, rtol=.005, atol=1e-13))
        samples = self.store.records["A"].data[0, :256]
        self.assertAlmostEqual(float(self.store.entries[0].result["SYNTH-C1"]["rms"]), np.sqrt(np.mean(samples**2)), delta=1e-7)
        json.dumps(result, allow_nan=False)

    def test_required_failure_resume_only_missing_part(self):
        self.begin([item("a", "amplitude", W), item("p", "psd", W)])
        self.run_tool("amplitude", W)
        self.inject_failure("psd", W)
        self.assertFalse(self.store.completion_check(self.store.active)["valid"])
        self.store.close_subgoal("suspended", ["功率计算失败"])
        restored = self.store.restore_subgoal("multi-s1")
        self.assertEqual(len(restored["action_observations"]), 2)
        self.store.resume_subgoal("multi-s1")
        self.run_tool("psd", W)
        self.assertEqual(self.store.close_subgoal("completed")["status"], "completed")
        self.assertEqual([o["request"]["name"] for o in self.store.subgoals[0].observations].count("amplitude"), 1)

    def test_optional_failure_not_global_failure(self):
        self.begin([item("a", "amplitude", W), item("p", "psd", W, required=False)])
        self.run_tool("amplitude", W)
        self.inject_failure("psd", W)
        result = self.store.close_subgoal("completed")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["summary"]["delivery_check"]["deliveries"][1]["status"], "failed")
        self.assertEqual(len(result["summary"]["failed_attempts"]), 1)

    def test_repeated_tool_distinct_scope_and_revision(self):
        self.run_tool("psd", W)  # Simple path remains implicit.
        old = self.store.entries[0]
        new = dict(W, end=3)
        self.begin([item("old", "psd", W), item("new", "psd", new, revision_of=old.task_id)])
        self.assertEqual(self.store.reuse_result("new", old.task_id)["code"], "REUSE_MISMATCH")
        self.assertEqual(self.store.reuse_result("old", old.task_id)["status"], "reused")
        self.run_tool("psd", new)
        self.assertEqual(self.store.close_subgoal("completed")["status"], "completed")
        self.assertEqual(self.store.entries[1].revision_of, old.task_id)
        self.assertEqual(self.store.entries[0].parameters, W)
        self.assertEqual(self.store.summary(self.store.subgoals[0])["results"][0]["superseded_by"], ["multi-t2"])

    def test_reuse_after_failed_attempt_and_later_attempt_precedence(self):
        self.run_tool("psd", W)
        self.begin([item("p", "psd", W)])
        self.inject_failure("psd", W)
        self.assertTrue(self.store.reuse_result("p", "multi-t1")["delivery_check"]["valid"])
        self.inject_failure("psd", W)
        self.assertFalse(self.store.completion_check(self.store.active)["valid"])
        self.assertEqual(len(self.store.entries), 1)

    def test_reuse_rejects_record_and_mutated_data(self):
        self.run_tool("psd", W)
        self.store.begin_subgoal("其他记录", "B", deliveries=[item("p", "psd", W)])
        self.assertEqual(self.store.reuse_result("p", "multi-t1")["code"], "REUSE_MISMATCH")
        self.store.close_subgoal("suspended", ["其他记录"])
        self.begin([item("p", "psd", W)])
        ctx = self.store.contexts["A"]
        ctx.record = replace(ctx.record, data=ctx.record.data * 2)
        self.assertEqual(self.store.reuse_result("p", "multi-t1")["code"], "REUSE_MISMATCH")

    def test_event_same_artifact_not_just_same_content(self):
        self.begin([item("quality", "epoch_quality", E), item("power", "event_bandpower", E)])
        first = self.run_tool("create_epochs", E)["artifact_id"]
        self.run_tool("epoch_quality", {"artifact_id": first})
        second = self.run_tool("create_epochs", E)["artifact_id"]
        self.run_tool("event_bandpower", {"artifact_id": second})
        self.assertFalse(self.store.completion_check(self.store.active)["valid"])
        self.run_tool("epoch_quality", {"artifact_id": second})
        self.assertEqual(self.store.close_subgoal("completed")["status"], "completed")
        self.assertEqual(len(self.store.entries), 5)

    def test_event_summary_count_and_psd_oracle(self):
        self.begin([item("count", "epoch_summary", E), item("power", "event_bandpower", E)])
        ident = self.run_tool("create_epochs", E)["artifact_id"]
        summary = self.run_tool("epoch_summary", {"artifact_id": ident})
        power = self.run_tool("event_bandpower", {"artifact_id": ident})
        self.assertEqual(summary["valid_epoch_count"], 3)
        path = ["conditions", "stimulus", "channels", "SYNTH-C1", "alpha"]
        oracle = independent_oracle(self.store.records["A"], {"capability": "event_bandpower", "parameters": E}, path)
        value = power
        for key in path:
            value = value[key]
        self.assertTrue(np.isclose(float(value), oracle, rtol=.005, atol=1e-13))
        self.assertEqual(self.store.close_subgoal("completed")["status"], "completed")

    def test_conditions_use_exact_result_and_numeric_string(self):
        self.begin([item("a", "amplitude", W)], criteria=[{"delivery": "a", "path": ["SYNTH-C1", "rms"], "op": "gte", "value": 1e-6}])
        self.run_tool("amplitude", W)
        self.assertTrue(self.store.completion_check(self.store.active)["valid"])
        self.store.active.criteria[0]["value"] = 1  # Controlled incompatible demand.
        self.assertFalse(self.store.completion_check(self.store.active)["valid"])

    def test_bad_contract_and_wrong_scope_cannot_complete(self):
        self.assertEqual(self.store.begin_subgoal("x", "A", deliveries=[item("x", "psd", {})])["status"], "rejected")
        self.assertEqual(self.store.begin_subgoal("x", "A", deliveries=[item("x", "psd", W, required=False)])["status"], "rejected")
        self.begin([item("a", "amplitude", W), item("p", "psd", dict(W, end=3))])
        self.run_tool("amplitude", W)
        self.run_tool("psd", W)  # Allowed measurement, wrong required scope.
        self.assertFalse(self.store.completion_check(self.store.active)["valid"])


class DeliveryAgentTest(unittest.TestCase):
    def test_actual_request_context_archive_read_restore_and_continuation(self):
        deliveries = [item("count", "epoch_summary", E), item("power", "event_bandpower", E)]
        def restored_artifact(messages):
            payload = json.loads(messages[1]["content"])
            trace = payload["restored_trajectories"][0]["action_observations"]
            ident = next(o["result"]["data"]["artifact_id"] for o in trace if o["request"]["name"] == "create_epochs")
            return "epoch_quality", {"artifact_id": ident}
        fake = ScriptedClient([
            ("begin_subgoal", {"title": "事件试次数与功率", "record": "A", "deliveries": deliveries}),
            ("create_epochs", E), artifact_action("epoch_summary"), artifact_action("event_bandpower"),
            ("close_subgoal", {"status": "completed"}), finish(),
            ("restore_subgoal", {"subgoal_id": "agent-s1", "reason": "在同一工件上追加质量测量"}),
            ("begin_subgoal", {"title": "保留旧功率并追加质量", "record": "A", "deliveries": [item("p", "event_bandpower", E), item("q", "epoch_quality", E)]}),
            ("reuse_result", {"delivery_key": "p", "task_id": "agent-t3"}), restored_artifact,
            ("close_subgoal", {"status": "completed"}),
            ("read_evidence", {"task_id": "agent-t2", "record": "A", "parameters": E, "field_paths": [["valid_epoch_count"]]}),
            finish(),
        ])
        agent = WorkingMemoryEEGAgent(fake, synthetic_records(), session_id="agent", memory_version="multi_result")
        first = agent.run("分析 A 的 stimulus 条件，0 到 1 秒，给出试次数和频带功率。")
        second = agent.continue_run("保留已有功率，在同一批试次上补充质量测量并说明原试次数。")
        self.assertEqual((first.stop_reason, second.stop_reason), ("completed", "completed"))
        store = agent.working_memory.store
        self.assertEqual(len(store.entries), 4)
        tools = [o["request"]["name"] for g in store.subgoals for o in g.observations]
        self.assertEqual(tools.count("create_epochs"), 1)
        self.assertEqual(tools.count("event_bandpower"), 1)
        before = json.loads(fake.seen[9][1]["content"])
        self.assertTrue(before["restored_trajectories"])
        last = json.loads(fake.seen[-1][1]["content"])
        self.assertEqual({e["task_id"] for e in last["exact_evidence"]}, {"agent-t1", "agent-t2", "agent-t3", "agent-t4"})
        read = next(e for e in last["exact_evidence"] if e["task_id"] == "agent-t2")
        self.assertIn("read_fields", next(f for f in read["fields"] if f["path"] == ["valid_epoch_count"])["via"])
        json.dumps(agent.working_memory.snapshot(), allow_nan=False)

    def test_short_request_and_missing_parameter_safe_clarification(self):
        fake = ScriptedClient([("amplitude", W), finish()])
        agent = WorkingMemoryEEGAgent(fake, synthetic_records(), memory_version="multi_result")
        self.assertEqual(agent.run("A，SYNTH-C1，0到2秒幅值").stop_reason, "completed")
        self.assertTrue(agent.working_memory.store.subgoals[0].implicit)
        fake = ScriptedClient([("begin_subgoal", {"title": "功率", "record": "A", "deliveries": [item("p", "psd", {})]}),
                               finish("clarification_required", unresolved=["需要窗口和通道"])])
        agent = WorkingMemoryEEGAgent(fake, synthetic_records(), memory_version="multi_result")
        self.assertEqual(agent.run("看看功率").stop_reason, "clarification_required")
        self.assertFalse(agent.working_memory.store.entries)


if __name__ == "__main__":
    unittest.main()
