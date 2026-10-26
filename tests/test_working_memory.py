"""Mechanism tests: scripted actions, real EEG tools and independent raw-sample oracle.

This Fake is an intervention, not evidence of autonomous model performance.
"""
from dataclasses import replace
import json
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from eeg_harness.working_memory import WorkingMemoryStore
from eeg_harness.working_memory_agent import WorkingMemoryEEGAgent
from eeg_harness.research.task_memory import synthetic_records
from eeg_harness.research.task_memory_v2 import independent_oracle
from eeg_harness.llm import LLMServiceError
from eeg_harness.working_memory_cli import ReservedPhaseClient


WINDOW = {"channels": ["SYNTH-C1"], "start": 0, "end": 2}
EVENT = {"labels": ["stimulus"], "tmin": 0, "tmax": 1}


class ScriptedClient:
    def __init__(self, actions):
        self.actions = iter(actions)
        self.seen = []

    def complete(self, messages, tools):
        self.seen.append(json.loads(json.dumps(messages)))
        action = next(self.actions)
        if callable(action):
            action = action(messages)
        if isinstance(action, dict):
            return action
        name, args = action
        return {"role": "assistant", "content": None, "tool_calls": [{
            "id": f"call-{len(self.seen)}", "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)}}]}


def artifact_action(name):
    def choose(messages):
        # Reads the actual preceding observation; never precomputes an artifact ID.
        for message in reversed(messages):
            if message["role"] == "tool":
                data = json.loads(message["content"])["data"]
                if "observation" in data:
                    ident = data["observation"]["result"]["data"]["artifact_id"]
                    return name, {"artifact_id": ident}
        raise AssertionError("No actual artifact observation")
    return choose


def finish(status="completed", **extra):
    return "finish_task", {"status": status, "answer": "受控测试回答，不是模型自主结果", **extra}


class WorkingMemoryTest(unittest.TestCase):
    def setUp(self):
        self.records = synthetic_records()
        self.store = WorkingMemoryStore("test", self.records)

    def begin_event(self, checks=None):
        return self.store.begin_subgoal("事件分析", "A", "event_bandpower", EVENT, checks=checks)

    def make_epochs(self):
        result = self.store.execute_numeric("create_epochs", EVENT)
        return result["observation"]["result"]["data"]["artifact_id"]

    def test_real_numeric_oracle_and_grounded_metadata(self):
        self.store.execute_numeric("psd", WINDOW)
        entry = self.store.entries[0]
        oracle = independent_oracle(self.records["A"], {
            "capability": "psd", "parameters": WINDOW}, ["SYNTH-C1", "alpha"])
        self.assertTrue(np.isclose(float(entry.result["SYNTH-C1"]["alpha"]), oracle,
                                   rtol=.005, atol=1e-13))
        self.assertEqual(entry.evidence["analysis_configuration"]["sfreq"], 128)
        self.assertEqual(entry.evidence["unit_or_kind"], "V²")

    def test_completion_requires_actual_check_and_same_artifact(self):
        self.begin_event(["epoch_quality"])
        self.assertEqual(self.store.close_subgoal("completed")["code"], "DELIVERABLE_MISSING")
        first = self.make_epochs()
        self.store.execute_numeric("epoch_quality", {"artifact_id": first})
        second = self.make_epochs()
        self.store.execute_numeric("event_bandpower", {"artifact_id": second})
        self.assertEqual(self.store.close_subgoal("completed")["code"], "CHECK_ARTIFACT_MISMATCH")
        self.store.execute_numeric("epoch_quality", {"artifact_id": second})
        self.assertEqual(self.store.close_subgoal("completed")["status"], "completed")

    def test_failed_or_changed_scope_not_success(self):
        self.store.begin_subgoal("PSD", "A", "psd", WINDOW)
        result = self.store.execute_numeric("psd", dict(WINDOW, end=3))
        self.assertEqual(result["observation"]["result"]["error"]["code"], "SCIENTIFIC_SCOPE_MISMATCH")
        self.assertFalse(self.store.completion_check(self.store.active)["valid"])
        self.assertEqual(self.store.close_subgoal("suspended", ["等待窗口确认"])["status"], "suspended")
        self.assertEqual(self.store.resume_subgoal("test-s1")["status"], "active")
        self.store.execute_numeric("psd", WINDOW)
        self.assertEqual(self.store.close_subgoal("completed")["status"], "completed")

    def test_missing_scope_and_unknown_tools(self):
        self.assertEqual(self.store.begin_subgoal("事件", "A", "event_bandpower", {})["status"], "rejected")
        self.assertEqual(self.store.execute_numeric("select_epochs", {})["code"], "TOOL_NOT_AVAILABLE")

    def test_observation_predicate_is_not_api_success(self):
        self.store.begin_subgoal("至少四试次", "A", "event_bandpower", EVENT,
            criteria=[{"tool": "create_epochs", "path": ["valid_epoch_count"], "op": "gte", "value": 4}])
        ident = self.make_epochs()
        self.store.execute_numeric("event_bandpower", {"artifact_id": ident})
        self.assertEqual(self.store.close_subgoal("completed")["code"], "CRITERION_NOT_SATISFIED")
        self.assertFalse(self.store.entries)

    def test_failed_read_never_becomes_evidence(self):
        fake = ScriptedClient([("psd", WINDOW),
            ("read_evidence", {"task_id": "test-t1", "record": "B", "parameters": WINDOW}), finish()])
        agent = WorkingMemoryEEGAgent(fake, self.records, session_id="test")
        result = agent.run("计算并读历史")
        self.assertFalse(result.tool_results[1]["success"])
        fields = json.loads(fake.seen[-1][1]["content"])["exact_evidence"][0]["fields"]
        self.assertTrue(all("read_full" not in f["via"] for f in fields))

    def test_restore_limit_and_pending_completion_rejected(self):
        fake = ScriptedClient([("psd", WINDOW),
            ("restore_subgoal", {"subgoal_id": "test-s1", "reason": "检查"}), finish()])
        agent = WorkingMemoryEEGAgent(fake, self.records, session_id="test", max_restores=0)
        result = agent.run("查询")
        self.assertEqual(result.tool_results[1]["error"]["code"], "RESTORE_LIMIT")

    def test_unrequested_transforms_not_available(self):
        outcome = self.store.begin_subgoal("校正", "A", "event_bandpower", dict(EVENT, baseline=[0, .1]))
        self.assertEqual(outcome["code"], "TRANSFORM_NOT_ENABLED")

    def test_ready_suspended_goal_can_close_without_reexecuting_or_guessing(self):
        self.begin_event(["epoch_quality"])
        ident = self.make_epochs()
        self.store.execute_numeric("epoch_quality", {"artifact_id": ident})
        self.store.execute_numeric("event_bandpower", {"artifact_id": ident})
        self.store.execute_numeric("psd", WINDOW)  # Out-of-scope request stays failed.
        self.store.close_subgoal("suspended", ["连续分析另做"])
        self.assertTrue(self.store.summary(self.store.subgoals[0])["delivery_check"]["valid"])
        count = len(self.store.subgoals[0].observations)
        self.assertEqual(self.store.close_subgoal("completed", subgoal_id="test-s1")["status"], "completed")
        self.assertEqual(len(self.store.subgoals[0].observations), count)
        self.assertEqual(self.store.find_entry("test-s1").task_id, "test-t1")
        self.store.begin_subgoal("修订", "A", "event_bandpower", dict(EVENT, tmax=.5), revision_of="test-s1")
        self.assertEqual(self.store.active.revision_of, "test-t1")

    def test_restore_is_not_duplicate_protocol_payload(self):
        fake = ScriptedClient([("psd", WINDOW), finish(),
            ("restore_subgoal", {"subgoal_id": "test-s1", "reason": "检查原行动"}), finish()])
        agent = WorkingMemoryEEGAgent(fake, self.records, session_id="test")
        agent.run("先分析")
        agent.continue_run("核对过程")
        after = fake.seen[-1]
        self.assertTrue(json.loads(after[1]["content"])["restored_trajectories"])
        self.assertFalse(any(m["role"] == "tool" and m["name"] == "restore_subgoal" for m in after))

    def test_source_artifact_isolation(self):
        self.begin_event()
        first = self.make_epochs()
        self.store.close_subgoal("suspended", ["换记录"])
        self.store.begin_subgoal("B", "B", "event_bandpower", EVENT)
        result = self.store.execute_numeric("event_bandpower", {"artifact_id": first})
        self.assertEqual(result["observation"]["result"]["error"]["code"], "ARTIFACT_NOT_FOUND")

    def test_version_binding_immutable_old_result(self):
        self.store.execute_numeric("psd", WINDOW)
        old = json.dumps(self.store.entries[0].result)
        self.store.begin_subgoal("修订", "A", "psd", dict(WINDOW, start=3, end=5), revision_of="test-t1")
        self.store.execute_numeric("psd", dict(WINDOW, start=3, end=5))
        self.store.close_subgoal("completed")
        self.assertEqual(json.dumps(self.store.entries[0].result), old)
        self.assertEqual(self.store.entries[1].revision_of, "test-t1")
        self.assertEqual(self.store.read_evidence("test-t1", "B", WINDOW)["code"], "EVIDENCE_BINDING_MISMATCH")
        self.assertEqual(self.store.read_evidence("test-t1", "A", dict(WINDOW, end=3))["status"], "rejected")

    def test_scalar_read_is_distinct_from_restore(self):
        self.store.execute_numeric("psd", WINDOW)
        read = self.store.read_evidence("test-t1", "A", WINDOW, field_paths=[["SYNTH-C1", "alpha"]])
        self.assertEqual(len(read["evidence"]["fields"]), 1)
        self.assertNotIn("action_observations", read)
        restore = self.store.restore_subgoal("test-s1")
        self.assertEqual(restore["action_observations"][0]["request"]["name"], "psd")

    def test_multistep_real_tools_live_observation_archive_and_protocol(self):
        fake = ScriptedClient([
            ("begin_subgoal", {"title": "事件质量和功率", "record": "A", "deliverable": "event_bandpower", "scope": EVENT, "checks": ["epoch_quality"]}),
            ("create_epochs", EVENT), artifact_action("epoch_quality"), artifact_action("event_bandpower"),
            ("close_subgoal", {"status": "completed"}), ("psd", WINDOW), finish()])
        agent = WorkingMemoryEEGAgent(fake, self.records, session_id="test")
        result = agent.run("检查 A stimulus 事件0–1秒质量后计算功率，并计算连续0–2秒功率；不筛选。")
        self.assertEqual(result.stop_reason, "completed")
        self.assertEqual(len(agent.working_memory.store.entries), 2)
        entry = agent.working_memory.store.entries[0]
        field = ["conditions", "stimulus", "channels", "SYNTH-C1", "alpha"]
        actual = entry.result["conditions"]["stimulus"]["channels"]["SYNTH-C1"]["alpha"]
        expected = independent_oracle(self.records["A"], {"capability": "event_bandpower", "parameters": EVENT}, field)
        self.assertTrue(np.isclose(actual, expected, rtol=1e-6))
        before_close = fake.seen[4]
        after_close = fake.seen[5]
        self.assertGreater(len(before_close), len(after_close))
        self.assertNotIn('"role": "tool", "tool_call_id": "call-2"', json.dumps(after_close))
        self.assertIn("epoch_counts", after_close[1]["content"])
        for messages in fake.seen:
            pending = set()
            for message in messages:
                if message["role"] == "assistant":
                    pending.update(c["id"] for c in message.get("tool_calls", []))
                if message["role"] == "tool":
                    self.assertIn(message["tool_call_id"], pending)
                    pending.remove(message["tool_call_id"])
            self.assertFalse(pending)
        json.dumps(result.to_dict(), allow_nan=False)

    def test_restore_is_visible_before_revision_and_evidence_union(self):
        fake = ScriptedClient([("psd", WINDOW), finish(),
            ("restore_subgoal", {"subgoal_id": "test-s1", "reason": "核对旧分析窗口再修订"}),
            ("begin_subgoal", {"title": "修订", "record": "A", "deliverable": "psd", "scope": dict(WINDOW, start=3, end=5), "revision_of": "test-t1"}),
            ("psd", dict(WINDOW, start=3, end=5)), ("close_subgoal", {"status": "completed"}),
            ("read_evidence", {"task_id": "test-t1", "record": "A", "parameters": WINDOW}), finish()])
        agent = WorkingMemoryEEGAgent(fake, self.records, session_id="test")
        agent.run("计算 A 连续0–2秒功率，禁止筛选")
        result = agent.continue_run("核对旧方法，将窗口改到3–5秒并比较")
        self.assertEqual(result.stop_reason, "completed")
        payload = json.loads(fake.seen[3][1]["content"])
        self.assertTrue(payload["restored_trajectories"][0]["action_observations"])
        self.assertIn("禁止筛选", payload["user_requests"][0])
        final = json.loads(fake.seen[-1][1]["content"])
        self.assertEqual({e["task_id"] for e in final["exact_evidence"]}, {"test-t1", "test-t2"})

    def test_simple_query_has_no_forced_hierarchy(self):
        fake = ScriptedClient([("record_info", {}), finish()])
        agent = WorkingMemoryEEGAgent(fake, self.records)
        result = agent.run("当前记录采样率是多少")
        self.assertEqual(result.tool_calls, 2)
        self.assertTrue(agent.working_memory.store.subgoals[0].implicit)

    def test_clarification_and_partial_are_not_completion(self):
        agent = WorkingMemoryEEGAgent(ScriptedClient([finish("clarification_required", unresolved=["事件窗口和条件"])]), self.records)
        self.assertEqual(agent.run("做事件分析").stop_reason, "clarification_required")
        partial = WorkingMemoryEEGAgent(ScriptedClient([("record_info", {}), finish("partial", unresolved=["缺少窗口"])]), self.records)
        self.assertEqual(partial.run("提供信息和频带分析").stop_reason, "partial")

    def test_no_progress_free_text_and_invalid_action(self):
        for action in ({"content": "完成了"}, ("absent_tool", {})):
            agent = WorkingMemoryEEGAgent(ScriptedClient([action] * 4), self.records)
            self.assertEqual(agent.run("测试").stop_reason, "no_progress")

    def test_scope_feedback_allows_recovery_without_silent_parameter_rewrite(self):
        bad = self.store.begin_subgoal("事件功率", "A", "event_bandpower", dict(EVENT, channels=["SYNTH-C1"]))
        self.assertEqual(bad["unexpected_keys"], ["channels"])
        self.assertIn("tmin", bad["required_scope_keys"])
        self.assertIsNone(self.store.active)
        self.assertEqual(self.begin_event()["status"], "active")

    def test_limits_cancellation_and_context_capacity(self):
        agent = WorkingMemoryEEGAgent(ScriptedClient([]), self.records)
        agent.cancel()
        self.assertEqual(agent.run("取消").stop_reason, "cancelled")
        agent = WorkingMemoryEEGAgent(ScriptedClient([]), self.records, max_context_bytes=20)
        self.assertEqual(agent.run("容量").stop_reason, "context_capacity")
        agent = WorkingMemoryEEGAgent(ScriptedClient([("record_info", {})]), self.records, max_rounds=1)
        self.assertEqual(agent.run("信息").stop_reason, "round_limit")

    def test_budget_stop_is_not_provider_failure(self):
        class Exhausted:
            def complete(self, messages, tools):
                raise LLMServiceError("STAGE_BUDGET_EXHAUSTED", "No reservation")
        agent = WorkingMemoryEEGAgent(Exhausted(), self.records)
        self.assertEqual(agent.run("信息").stop_reason, "budget_exhausted")

    def test_development_reservation_survives_restart(self):
        class NoNetwork:
            client = SimpleNamespace(max_tokens=1200)
            def complete(self, *args):
                raise AssertionError("Must not make another external call")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "budget.jsonl"
            ReservedPhaseClient(NoNetwork(), path, max_requests=96, max_tokens=240000, phase="development")
            with path.open("a", encoding="utf8") as stream:
                for row in [
                    {"event": "reserved", "request_id": "prior", "reserved_tokens": 140000, "context": {"phase": "development"}},
                    {"event": "received", "request_id": "prior", "total_tokens": 140000}]:
                    stream.write(json.dumps(row) + "\n")
            restarted = ReservedPhaseClient(NoNetwork(), path, max_requests=96, max_tokens=240000, phase="development")
            with self.assertRaises(LLMServiceError) as caught:
                restarted.complete([{"role": "user", "content": "normal request"}], [])
            self.assertEqual(caught.exception.code, "STAGE_BUDGET_EXHAUSTED")

    def test_real_data_gate(self):
        with self.assertRaises(ValueError):
            WorkingMemoryStore("bad", {"A": replace(self.records["A"], source="private://real")})

    def test_full_reference_shares_contracts_and_retains_history(self):
        fake = ScriptedClient([("psd", WINDOW), ("record_info", {}), finish()])
        agent = WorkingMemoryEEGAgent(fake, self.records, context_mode="full")
        self.assertEqual(agent.run("信息和功率").stop_reason, "completed")
        self.assertEqual(sum(m["role"] == "tool" for m in fake.seen[-1]), 2)


if __name__ == "__main__":
    unittest.main()
