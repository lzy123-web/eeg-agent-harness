"""Issue48 natural run/continue hooks with Fake decisions and real EEG tools.

The scripted choices test data flow, not model autonomy. Artifact IDs are read
from actual visible observations/restore payloads, never guessed in the test.
"""
import json
import unittest

import numpy as np

from eeg_harness.research.task_memory import synthetic_records
from eeg_harness.research.task_memory_v2 import independent_oracle
from eeg_harness.working_memory_agent import WorkingMemoryEEGAgent
from test_working_memory import ScriptedClient, finish


def visible_epoch(messages):
    payload = json.loads(messages[1]["content"])
    candidates = []
    for restored in payload.get("restored_trajectories", []):
        candidates += restored["action_observations"]
    for message in messages[2:]:
        if message["role"] == "tool":
            data = json.loads(message["content"]).get("data") or {}
            if data.get("observation"):
                candidates.append(data["observation"])
    for observation in reversed(candidates):
        if observation["request"]["name"] == "create_epochs" and observation["result"]["success"]:
            return observation
    raise AssertionError("No actual created Epoch is visible to the decision")


def artifact_measurement(name):
    def action(messages):
        data = visible_epoch(messages)["result"]["data"]
        return name, {"artifact_id": data["artifact_id"],
                      "expected_artifact_fingerprint": data["artifact_fingerprint"]}
    return action


class LifecycleIntegrationTest(unittest.TestCase):
    def make(self, actions, *, ident="life"):
        fake = ScriptedClient(actions)
        return WorkingMemoryEEGAgent(fake, synthetic_records(), session_id=ident,
                                     memory_version="lifecycle"), fake

    def test_continuous_pending_survives_unrelated_short_turn_then_completes(self):
        goal = {"title": "A的RMS", "record": "A", "deliveries": [
            {"key": "rms", "tool": "amplitude", "scope": {"channels": ["SYNTH-C1"]}}]}
        window = {"channels": ["SYNTH-C1"], "start": 0, "end": 2}
        agent, _ = self.make([
            ("begin_subgoal", goal),
            finish("clarification_required", unresolved=["需要记录绝对时间窗"]),
            ("record_info", {}), finish(),
            ("amend_subgoal", {"subgoal_id": "life-s1", "updates": {"rms": {"start": 0, "end": 2}}}),
            ("amplitude", window), ("close_subgoal", {"status": "completed"}), finish()])
        first = agent.run("请给记录A的SYNTH-C1计算RMS，时间窗稍后确定。")
        self.assertEqual(first.stop_reason, "clarification_required")
        self.assertEqual(len(agent.working_memory.store.entries), 0)
        second = agent.continue_run("先告诉我记录A的采样率。")
        self.assertEqual(second.stop_reason, "completed")
        self.assertNotEqual(agent.working_memory.store.subgoals[0].status, "completed")
        third = agent.continue_run("刚才RMS的时间窗确定为0到2秒。")
        self.assertEqual(third.stop_reason, "completed")
        store = agent.working_memory.store
        self.assertEqual(store.subgoals[0].subgoal_id, "life-s1")
        self.assertEqual(store.subgoals[0].status, "completed")
        self.assertEqual(len(store.subgoals), 2)  # one pending purpose, one short metadata purpose
        self.assertEqual([e.capability for e in store.entries], ["record_info", "amplitude"])
        entry = store.entries[-1]
        expected = independent_oracle(store.records["A"], {"capability": "amplitude", "parameters": window}, ["SYNTH-C1", "rms"])
        self.assertTrue(np.isclose(float(entry.result["SYNTH-C1"]["rms"]), expected, rtol=.005, atol=5e-13))
        sources = store.subgoals[0].verified_sources["rms"]
        self.assertEqual(sources["channels"]["turn"], 1)
        self.assertEqual(sources["start"]["turn"], 3)

    def test_event_clarification_fills_same_goal_and_uses_actual_artifact(self):
        goal = {"title": "stimulus有效试次数", "record": "A", "deliveries": [
            {"key": "epochs", "tool": "create_epochs", "scope": {"labels": ["stimulus"]}},
            {"key": "count", "tool": "epoch_summary", "scope": {"labels": ["stimulus"]}}]}
        scope = {"labels": ["stimulus"], "tmin": 0, "tmax": 1}
        agent, _ = self.make([
            ("begin_subgoal", goal), finish("clarification_required", unresolved=["需要事件相对时间窗"]),
            ("amend_subgoal", {"subgoal_id": "life-s1", "updates": {
                "epochs": {"tmin": 0, "tmax": 1}, "count": {"tmin": 0, "tmax": 1}}}),
            ("create_epochs", scope), artifact_measurement("epoch_summary"),
            ("close_subgoal", {"status": "completed"}), finish()])
        first = agent.run("统计记录A的stimulus条件可用试次数，事件窗请先问我。")
        self.assertEqual(first.stop_reason, "clarification_required")
        self.assertEqual(agent.working_memory.store.contexts["A"].artifacts, {})
        second = agent.continue_run("事件窗取事件后0到1秒，不做基线校正。")
        self.assertEqual(second.stop_reason, "completed")
        store = agent.working_memory.store
        self.assertEqual(len(store.subgoals), 1)
        self.assertEqual(len(store.contexts["A"].artifacts), 1)
        self.assertEqual([e.capability for e in store.entries], ["create_epochs", "epoch_summary"])
        expected = independent_oracle(store.records["A"], {"capability": "epoch_summary", "parameters": scope}, ["valid_epoch_count"])
        self.assertEqual(store.entries[-1].result["valid_epoch_count"], expected)
        self.assertEqual(store.entries[0].evidence["binding"]["artifact_id"],
                         store.entries[1].evidence["binding"]["artifact_id"])

    def test_restored_process_enters_next_input_and_drives_same_epoch_quality(self):
        scope = {"labels": ["stimulus"], "tmin": 0, "tmax": 1}
        goal = {"title": "stimulus试次数", "record": "A", "deliveries": [
            {"key": "epochs", "tool": "create_epochs", "scope": scope},
            {"key": "count", "tool": "epoch_summary", "scope": scope}]}

        def continue_quality(messages):
            observation = visible_epoch(messages)
            ident = observation["result"]["data"]["artifact_id"]
            return "begin_subgoal", {"title": "原Epoch质量", "record": "A", "deliveries": [
                {"key": "quality", "tool": "epoch_quality", "scope": observation["scope"]}],
                "parameter_sources": {"quality": {"kind": "artifact", "artifact_id": ident}},
                "dependencies": [observation["result_id"]]}

        agent, fake = self.make([
            ("begin_subgoal", goal), ("create_epochs", scope), artifact_measurement("epoch_summary"),
            ("close_subgoal", {"status": "completed"}), finish(),
            ("restore_subgoal", {"subgoal_id": "life-s1", "reason": "核对先前试次创建过程并沿用同一工件"}),
            continue_quality, artifact_measurement("epoch_quality"),
            ("close_subgoal", {"status": "completed"}), finish()])
        first = agent.run("记录A的stimulus事件后0到1秒，统计有效试次数，不做基线校正或筛选。")
        self.assertEqual(first.stop_reason, "completed")
        first_result = agent.working_memory.store.entries[0]
        second = agent.continue_run("沿用记录A刚才stimulus那批Epoch补测质量，说明先前处理过程，不重新创建或筛选。")
        self.assertEqual(second.stop_reason, "completed")
        store = agent.working_memory.store
        self.assertEqual([e.capability for e in store.entries], ["create_epochs", "epoch_summary", "epoch_quality"])
        self.assertEqual(len(store.contexts["A"].artifacts), 1)
        quality = store.entries[-1]
        self.assertEqual(quality.evidence["binding"]["artifact_id"], first_result.evidence["binding"]["artifact_id"])
        self.assertEqual(quality.evidence["binding"]["artifact_fingerprint"], first_result.evidence["binding"]["artifact_fingerprint"])
        after_restore = json.loads(fake.seen[6][1]["content"])
        restored = after_restore["restored_trajectories"][0]
        actual = next(o for o in restored["action_observations"] if o["request"]["name"] == "create_epochs")
        self.assertEqual(actual["result"]["data"]["artifact_id"], quality.evidence["binding"]["artifact_id"])
        quality_action = store.subgoals[-1].observations[0]
        self.assertEqual(quality_action["request"]["arguments"]["artifact_id"], actual["result"]["data"]["artifact_id"])
        self.assertEqual(first_result.result["baseline"], None)
        self.assertEqual(quality.result["epoch_counts"]["created"], first_result.result["valid_epoch_count"])


if __name__ == "__main__":
    unittest.main()
