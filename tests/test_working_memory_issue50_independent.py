"""Independent scientific counterexamples for Issue50's action-local path.

The actions below are interventions, not claims about model autonomy. Numerical
assertions use actual original EEG tools and a raw-sample oracle. Two negative
cases arose during independent implementation review, before any paid run.
"""
from copy import deepcopy
import json
import unittest

import numpy as np

from eeg_harness.research.task_memory import synthetic_records
from eeg_harness.research.task_memory_v2 import independent_oracle
from eeg_harness.working_memory_actions import ActionWorkingMemoryStore
from eeg_harness.working_memory_agent import WorkingMemoryEEGAgent
from eeg_harness.agent import EEGAgent
from test_working_memory import ScriptedClient, finish


WINDOW = {"channels": ["SYNTH-C1"], "start": 0, "end": 2}
EVENT = {"labels": ["stimulus"], "tmin": 0, "tmax": 1}


class IndependentActionScienceTest(unittest.TestCase):
    def setUp(self):
        self.store = ActionWorkingMemoryStore("independent50", synthetic_records())

    def request(self, text):
        self.store.turn += 1
        self.store.user_requests.append(text)

    def test_active_multiobject_history_cannot_authorize_cross_product_scope(self):
        self.request("记录A的SYNTH-C1在0到2秒做PSD；SYNTH-C2在2到4秒做PSD。稍后补充质量。")
        self.store.focus_task("不同对象分别计算", "A", ["psd", "record_quality"])
        first = self.store.execute_action("psd", WINDOW)
        second_scope = {"channels": ["SYNTH-C2"], "start": 2, "end": 4}
        second = self.store.execute_action("psd", second_scope)
        self.assertTrue(first["observation"]["result"]["success"])
        self.assertTrue(second["observation"]["result"]["success"])
        # All individual values occurred before, but never in this combination.
        crossed = self.store.execute_action("psd", dict(WINDOW, channels=["SYNTH-C2"]))
        self.assertEqual(crossed["status"], "rejected")
        self.assertEqual(len(self.store.entries), 2)
        self.assertIsNone(self.store.entries[1].revision_of,
                          "Parallel channels are not an inferred revision of each other")
        for entry in self.store.entries:
            channel = entry.parameters["channels"][0]
            raw = independent_oracle(self.store.records["A"], {
                "capability": "psd", "parameters": entry.parameters}, [channel, "alpha"])
            self.assertTrue(np.isclose(float(entry.result[channel]["alpha"]), raw,
                                       rtol=.005, atol=1e-25))

    def test_success_on_one_object_does_not_erase_other_object_missing_window(self):
        self.request("记录A的SYNTH-C1在0到2秒计算PSD；SYNTH-C2也要PSD，但窗口尚未确定。")
        self.store.focus_task("两个对象的功率", "A", ["psd"])
        missing = self.store.execute_action("psd", {"channels": ["SYNTH-C2"]})
        self.assertEqual(missing["code"], "MISSING_SCIENTIFIC_PARAMETER")
        good = self.store.execute_action("psd", WINDOW)
        self.assertTrue(good["observation"]["result"]["success"])
        self.assertEqual(len(self.store.entries), 1)
        self.assertIsNotNone(self.store.active)
        self.assertFalse(self.store.completion_check(self.store.active)["valid"])
        self.assertTrue(any(p["arguments"].get("channels") == ["SYNTH-C2"]
                            for p in self.store.active.pending_actions))

    def test_missing_event_window_does_not_block_independent_continuous_result(self):
        self.request("记录A的SYNTH-C1在0到2秒给RMS；stimulus事件也分析，但事件窗口稍后给。")
        self.store.focus_task("连续和事件分析", "A", ["amplitude", "event_bandpower"])
        missing = self.store.execute_action("create_epochs", {"labels": ["stimulus"]})
        good = self.store.execute_action("amplitude", WINDOW)
        self.assertEqual(missing["code"], "MISSING_SCIENTIFIC_PARAMETER")
        self.assertTrue(good["observation"]["result"]["success"])
        self.assertFalse(self.store.contexts["A"].artifacts)
        self.assertEqual([e.capability for e in self.store.entries], ["amplitude"])
        raw = self.store.records["A"].slice(0, 2, ["SYNTH-C1"])
        expected = float(np.sqrt(np.mean(np.square(raw.astype(float)))))
        self.assertTrue(np.isclose(float(self.store.entries[0].result["SYNTH-C1"]["rms"]),
                                   expected, rtol=.005, atol=1e-15))
        self.assertFalse(self.store.completion_check(self.store.active)["valid"])

    def test_continuous_range_does_not_authorize_relative_event_range(self):
        self.request("记录A的SYNTH-C1在0到2秒计算PSD；stimulus事件后0到1秒创建试次。")
        self.store.focus_task("两种时间基准", "A", ["psd", "create_epochs"])
        self.store.execute_action("psd", WINDOW)
        crossed = self.store.execute_action("create_epochs", dict(EVENT, tmax=2))
        self.assertEqual(crossed["status"], "rejected")
        self.assertFalse(self.store.contexts["A"].artifacts)
        good = self.store.execute_action("create_epochs", EVENT)
        self.assertTrue(good["observation"]["result"]["success"])
        self.assertEqual(good["observation"]["result"]["data"]["valid_epoch_count"], 3)
        self.assertIsNone(self.store.active,
                          "A rejected invented window is not a permanent scientific requirement")
        self.assertEqual(self.store.subgoals[-1].status, "completed")

    def test_correct_values_on_wrong_record_and_unauthorized_transform_are_rejected(self):
        self.request("记录A的SYNTH-C1在0到2秒计算PSD；stimulus事件后0到1秒创建试次，不做基线校正。")
        wrong_record = self.store.execute_action("psd", WINDOW, record="B")
        self.assertEqual(wrong_record["status"], "rejected")
        transformed = self.store.execute_action("create_epochs", dict(EVENT, baseline=[0, .2]), record="A")
        self.assertEqual(transformed["status"], "rejected")
        self.assertFalse(self.store.entries)
        self.assertTrue(all(not c.artifacts for c in self.store.contexts.values()))

    def test_actual_parameter_revision_preserves_original_result_and_binding(self):
        self.request("记录A的SYNTH-C1在0到2秒计算PSD。")
        self.store.execute_action("psd", WINDOW, record="A")
        original = self.store.entries[-1]
        original_payload = deepcopy(original.result)
        self.request("将记录A的SYNTH-C1窗口改成4到6秒，计算新的PSD，保留原结果。")
        self.store.execute_action("psd", dict(WINDOW, start=4, end=6), record="A",
                                  inherit_result=original.task_id)
        revised = self.store.entries[-1]
        self.assertEqual(len(self.store.entries), 2)
        self.assertEqual(revised.revision_of, original.task_id)
        self.assertEqual(original.result, original_payload)
        self.assertEqual(original.parameters, WINDOW)
        self.assertTrue(self.store._binding_valid(original))
        self.assertNotEqual(original.result["SYNTH-C1"]["alpha"], revised.result["SYNTH-C1"]["alpha"])


def visible_observations(messages):
    """Read actual model input; do not reach into the agent's hidden store."""
    payload = json.loads(messages[1]["content"])
    observations = [o for task in payload.get("restored_trajectories", [])
                    for o in task["action_observations"]]
    for message in messages[2:]:
        if message["role"] == "tool":
            data = json.loads(message["content"]).get("data") or {}
            if data.get("observation"):
                observations.append(data["observation"])
    return observations


def shown_entry(messages, capability, *, first=True):
    payload = json.loads(messages[1]["content"])
    entries = [r for task in payload.get("task_summaries", []) for r in task["results"]
               if r["capability"] == capability]
    if not entries:
        raise AssertionError("Expected actual archived result is not visible")
    return entries[0 if first else -1]


class IndependentManagedAgentTest(unittest.TestCase):
    def make(self, actions, mode="working"):
        client = ScriptedClient(actions)
        agent = WorkingMemoryEEGAgent(client, synthetic_records(), session_id="agent50-review",
                                     memory_version="managed", context_mode=mode)
        return agent, client

    def test_original_loop_active_observation_archive_revision_and_untouched_old_read(self):
        first_request = "记录A的SYNTH-C1在0到2秒计算RMS与alpha功率，说明单位。"

        def psd_after_actual_amplitude(messages):
            payload = json.loads(messages[1]["content"])
            self.assertIsNotNone(payload["active_task"])
            observed = visible_observations(messages)
            self.assertEqual([o["request"]["name"] for o in observed], ["amplitude"])
            self.assertTrue(observed[0]["result"]["success"])
            self.assertGreater(float(observed[0]["result"]["data"]["SYNTH-C1"]["rms"]), 0)
            return "psd", WINDOW

        def revise(messages):
            entry = shown_entry(messages, "psd")
            return "psd", {"start": 4, "end": 6, "inherit_result": entry["task_id"]}

        def old_read(messages):
            self.assertIn(first_request, json.loads(messages[1]["content"])["user_requests"])
            entry = shown_entry(messages, "amplitude")
            return "read_result", {"result_id": entry["task_id"], "fields": [["SYNTH-C1", "rms"]]}

        def finish_after_read(messages):
            payload = json.loads(messages[1]["content"])
            evidence = next(e for e in payload["retrieved_evidence"] if e["capability"] == "amplitude")
            self.assertEqual(evidence["record"], "A")
            self.assertEqual(evidence["parameters"], WINDOW)
            self.assertEqual(evidence["fields"][0]["semantics"]["unit"], "V")
            self.assertTrue(evidence["fields"][0]["canonical_display"].endswith(" V"))
            return finish()

        agent, client = self.make([
            ("focus_task", {"title": "同一范围的幅值与功率", "record": "A", "expected_tools": ["amplitude", "psd"]}),
            ("amplitude", WINDOW), psd_after_actual_amplitude, finish(),
            revise, finish(), old_read, finish_after_read])
        self.assertIs(WorkingMemoryEEGAgent.run, EEGAgent.run)
        self.assertEqual(agent.run(first_request).stop_reason, "completed")
        store = agent.working_memory.store
        self.assertEqual(len(store.subgoals), 1)
        self.assertEqual(store.subgoals[0].status, "completed")
        self.assertEqual(len(store.subgoals[0].result_ids), 2)
        self.assertIsNone(store.active)
        self.assertEqual(agent.continue_run("将记录A同一通道窗口改为4到6秒计算PSD，保留原结果。").stop_reason, "completed")
        self.assertEqual(store.entries[-1].revision_of, store.entries[1].task_id)
        historical = agent.continue_run("再告诉我第一次记录A的0到2秒RMS，不重新计算。")
        self.assertEqual(historical.stop_reason, "completed")
        self.assertEqual([r["tool_name"] for r in historical.tool_results], ["read_result", "finish_task"])
        self.assertEqual(len(store.entries), 3)
        self.assertFalse(any(c["function"]["name"] in {"begin_subgoal", "close_subgoal", "amend_subgoal"}
                             for pair in agent.working_memory.exchanges
                             for message in pair for c in message.get("tool_calls", [])))
        for messages in client.seen:
            for i, message in enumerate(messages):
                calls = message.get("tool_calls", [])
                if calls:
                    following = messages[i+1:i+1+len(calls)]
                    self.assertEqual({c["id"] for c in calls}, {r.get("tool_call_id") for r in following})

    def test_real_restoration_enters_next_input_and_original_artifact_drives_quality(self):
        def measure_power(messages):
            creation = next(o for o in visible_observations(messages) if o["request"]["name"] == "create_epochs")
            return "event_bandpower", {"artifact_id": creation["result"]["data"]["artifact_id"]}

        def restore(messages):
            entry = shown_entry(messages, "create_epochs")
            return "restore_task", {"task_id": entry["task_id"], "reason": "核实原试次处理过程并在原工件上追加质量"}

        def quality_from_restoration(messages):
            payload = json.loads(messages[1]["content"])
            self.assertEqual(len(payload["restored_trajectories"]), 1)
            restored = payload["restored_trajectories"][0]
            self.assertEqual([o["request"]["name"] for o in restored["action_observations"]],
                             ["create_epochs", "event_bandpower"])
            original = restored["action_observations"][0]
            self.assertIsNone(original["result"]["data"]["baseline"])
            return "epoch_quality", {"artifact_id": original["result"]["data"]["artifact_id"],
                                     "inherit_result": original["result_id"]}

        agent, client = self.make([
            ("focus_task", {"title": "试次与频带分析", "record": "A", "expected_tools": ["create_epochs", "event_bandpower"]}),
            ("create_epochs", EVENT), measure_power, finish(),
            restore, quality_from_restoration, finish()])
        self.assertEqual(agent.run("记录A的stimulus事件后0到1秒创建试次并计算频带功率，不做基线校正或筛选。").stop_reason,
                         "completed")
        store = agent.working_memory.store
        original = store.entries[0]
        result = agent.continue_run("沿用记录A刚才的原试次和处理，追加质量测量，不重新创建或筛选。")
        self.assertEqual(result.stop_reason, "completed")
        self.assertEqual([e.capability for e in store.entries], ["create_epochs", "event_bandpower", "epoch_quality"])
        self.assertEqual(len(store.contexts["A"].artifacts), 1)
        quality = store.entries[-1]
        self.assertEqual(quality.evidence["binding"]["artifact_id"], original.evidence["binding"]["artifact_id"])
        self.assertEqual(quality.evidence["binding"]["artifact_fingerprint"], original.evidence["binding"]["artifact_fingerprint"])
        self.assertEqual(quality.result["epoch_counts"]["created"], original.result["valid_epoch_count"])
        self.assertEqual([r["tool_name"] for r in result.tool_results], ["restore_task", "epoch_quality", "finish_task"])
        self.assertTrue(json.loads(client.seen[5][1]["content"])["restored_trajectories"])

    def test_partial_reads_union_survives_failure_without_prefetching_unread_fields(self):
        theta = ["conditions", "stimulus", "channels", "SYNTH-C2", "theta"]
        beta = ["conditions", "stimulus", "channels", "SYNTH-C1", "beta"]
        unread = ["conditions", "stimulus", "channels", "SYNTH-C2", "gamma"]

        def power(messages):
            creation = next(o for o in visible_observations(messages) if o["request"]["name"] == "create_epochs")
            return "event_bandpower", {"artifact_id": creation["result"]["data"]["artifact_id"]}

        def read(path, *, record="A"):
            def choose(messages):
                entry = shown_entry(messages, "event_bandpower")
                return "read_result", {"result_id": entry["task_id"], "record": record, "fields": [path]}
            return choose

        def final(messages):
            payload = json.loads(messages[1]["content"])
            row = next(e for e in payload["retrieved_evidence"] if e["capability"] == "event_bandpower")
            actual_paths = [f["path"] for f in row["fields"]]
            self.assertIn(theta, actual_paths)
            self.assertIn(beta, actual_paths)
            self.assertNotIn(unread, actual_paths, "Do not fetch unseen archive fields for an answer")
            self.assertGreater(row["omitted_fields"], 0)
            final_messages, _ = agent.working_memory.build_final_messages()
            final_row = next(e for e in json.loads(final_messages[1]["content"])["available_evidence"]
                             if e["capability"] == "event_bandpower")
            self.assertIn(theta, [f["path"] for f in final_row["fields"]])
            self.assertIn(beta, [f["path"] for f in final_row["fields"]])
            self.assertNotIn(unread, [f["path"] for f in final_row["fields"]])
            return finish()

        agent, _ = self.make([
            ("focus_task", {"title": "试次功率", "record": "A", "expected_tools": ["create_epochs", "event_bandpower"]}),
            ("create_epochs", EVENT), power, finish(),
            read(theta), read(beta), read(unread, record="B"), final])
        self.assertEqual(agent.run("记录A的stimulus事件后0到1秒创建试次并计算功率，不基线或筛选。").stop_reason,
                         "completed")
        result = agent.continue_run("查询记录A原试次的C2 theta和C1 beta，不重算。")
        self.assertEqual(result.stop_reason, "completed")
        self.assertFalse(result.tool_results[-2]["success"])
        self.assertEqual(len(agent.working_memory.store.entries), 2)

    def test_current_turn_archival_then_quality_keeps_already_seen_power_for_final(self):
        theta = ["conditions", "stimulus", "channels", "SYNTH-C2", "theta"]

        def power(messages):
            creation = next(o for o in visible_observations(messages) if o["request"]["name"] == "create_epochs")
            payload = json.loads(messages[1]["content"])
            self.assertNotIn(creation["result_id"], [e["task_id"] for e in payload["retrieved_evidence"]],
                             "Do not repeat a full result already supplied by active action-observation")
            return "event_bandpower", {"artifact_id": creation["result"]["data"]["artifact_id"]}

        def quality(messages):
            observed = next(o for o in visible_observations(messages) if o["request"]["name"] == "event_bandpower")
            return "epoch_quality", {"artifact_id": observed["result"]["data"]["artifact_id"],
                                     "inherit_result": observed["result_id"]}

        def final(messages):
            payload = json.loads(messages[1]["content"])
            power_row = next(e for e in payload["retrieved_evidence"] if e["capability"] == "event_bandpower")
            self.assertIn(theta, [f["path"] for f in power_row["fields"]])
            final_messages, _ = agent.working_memory.build_final_messages()
            rows = json.loads(final_messages[1]["content"])["available_evidence"]
            self.assertEqual({r["capability"] for r in rows}, {"create_epochs", "event_bandpower", "epoch_quality"})
            self.assertIn(theta, [f["path"] for r in rows if r["capability"] == "event_bandpower" for f in r["fields"]])
            return finish()

        agent, _ = self.make([
            ("focus_task", {"title": "试次与功率", "record": "A", "expected_tools": ["create_epochs", "event_bandpower"]}),
            ("create_epochs", EVENT), power, quality, final])
        result = agent.run("记录A的stimulus事件后0到1秒创建试次，计算各通道功率并追加质量测量，不基线或筛选。")
        self.assertEqual(result.stop_reason, "completed")
        self.assertEqual(len(agent.working_memory.store.entries), 3)


if __name__ == "__main__":
    unittest.main()
