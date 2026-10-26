"""Request closure interventions through the real Agent, tools and shared modes.

Fake choices test public data flow only, never autonomous model performance.
Evidence IDs and artifact references below are read from real observations.
"""
import json
import unittest

from eeg_harness.research.task_memory import synthetic_records
from eeg_harness.working_memory_agent import WorkingMemoryEEGAgent
from eeg_harness.working_memory_lifecycle import ReliableWorkingMemoryStore
from test_working_memory import ScriptedClient
from test_working_memory_lifecycle_integration import visible_epoch, artifact_measurement


WINDOW = {"channels": ["SYNTH-C1"], "start": 0, "end": 2}
EVENT = {"labels": ["stimulus"], "tmin": 0, "tmax": 1}
REQUEST = "请给记录A的SYNTH-C1在0到2秒RMS和alpha功率。"


def deliver(status="completed", *, capability=None, unresolved=None):
    def choose(messages):
        payload = json.loads(messages[1]["content"])
        rows = [e for e in payload["exact_evidence"]
                if capability is None or e["capability"] == capability]
        coverage = {"quote": payload["current_request"], "result_ids": [e["task_id"] for e in rows]}
        args = {"status": status, "answer": "受控机制回答，不代表模型自主表现。",
                "coverage": [coverage], "coverage_complete": status == "completed"}
        if unresolved:
            args["unresolved"] = [unresolved]
            coverage["unresolved"] = unresolved
        return "finish_task", args
    return choose


def declare_two():
    return "begin_subgoal", {"title": "连续双结果", "record": "A", "deliveries": [
        {"key": "rms", "tool": "amplitude", "scope": WINDOW},
        {"key": "power", "tool": "psd", "scope": WINDOW}],
        "requirements": [{"quote": REQUEST, "delivery_keys": ["rms", "power"]}]}


class ClosingClient(ScriptedClient):
    def __init__(self, actions):
        super().__init__(actions)
        self.interfaces = []
        self.budget_checks = []

    def prepare_decision(self, *args, **kwargs):
        self.budget_checks.append((args, kwargs))
        return len(self.seen) >= 1

    def complete(self, messages, tools, tool_choice=None):
        self.interfaces.append([t["function"]["name"] for t in tools])
        return super().complete(messages, tools)


class RequestClosureIntegrationTest(unittest.TestCase):
    def make(self, actions, mode="working", client_class=ScriptedClient):
        client = client_class(actions)
        agent = WorkingMemoryEEGAgent(client, synthetic_records(), session_id="closure",
            memory_version="lifecycle", request_closure=True, context_mode=mode)
        return agent, client

    def test_declared_multi_result_finish_checks_real_coverage_then_autoarchives(self):
        archives = []
        for mode in ("working", "summary", "full"):
            with self.subTest(mode=mode):
                agent, client = self.make([declare_two(), ("amplitude", WINDOW), ("psd", WINDOW),
                    deliver(capability="amplitude"), deliver()], mode)
                result = agent.run(REQUEST)
                self.assertEqual(result.stop_reason, "completed")
                # Both numerical results exist, but citing only one does not
                # complete a registered two-result requirement.
                self.assertFalse(result.tool_results[-2]["success"])
                self.assertTrue(result.tool_results[-1]["success"])
                store = agent.working_memory.store
                self.assertEqual(len(store.entries), 2)
                self.assertEqual(store.subgoals[0].status, "completed")
                self.assertIsNone(store.active)
                self.assertNotIn("close_subgoal", [r["tool_name"] for r in result.tool_results])
                self.assertIn(REQUEST, json.dumps(client.seen[-1], ensure_ascii=False))
                archives.append([(e.record, e.parameters, e.result) for e in store.entries])
        self.assertEqual(archives[0], archives[1])
        self.assertEqual(archives[1], archives[2])

    def test_partial_reply_preserves_unexecuted_required_science(self):
        agent, _ = self.make([declare_two(), ("amplitude", WINDOW),
            deliver("partial", unresolved="alpha功率尚未执行")])
        result = agent.run(REQUEST)
        self.assertEqual(result.stop_reason, "partial")
        store = agent.working_memory.store
        self.assertEqual([e.capability for e in store.entries], ["amplitude"])
        self.assertNotEqual(store.subgoals[0].status, "completed")
        self.assertFalse(store.completion_check(store.subgoals[0])["valid"])

    def test_missing_window_unrelated_query_then_same_goal_supplement(self):
        first = "请给记录A的SYNTH-C1计算RMS，时间窗稍后确定。"
        goal = ("begin_subgoal", {"title": "待定RMS", "record": "A", "deliveries": [
            {"key": "rms", "tool": "amplitude", "scope": {"channels": ["SYNTH-C1"]}}],
            "requirements": [{"quote": first, "delivery_keys": ["rms"]}]})
        agent, _ = self.make([goal,
            deliver("clarification_required", unresolved="需要记录绝对时间窗"),
            ("record_info", {"record": "B"}), deliver(),
            ("amend_subgoal", {"subgoal_id": "closure-s1", "updates": {"rms": {"start": 0, "end": 2}}}),
            ("amplitude", WINDOW), deliver()])
        self.assertEqual(agent.run(first).stop_reason, "clarification_required")
        self.assertEqual(agent.continue_run("先查询记录B的采样率。").stop_reason, "completed")
        store = agent.working_memory.store
        self.assertNotEqual(store.subgoals[0].status, "completed")
        final = agent.continue_run("原来RMS的窗口确定为0到2秒，继续记录A的原要求。")
        self.assertEqual(final.stop_reason, "completed")
        self.assertEqual(store.subgoals[0].subgoal_id, "closure-s1")
        self.assertEqual(store.subgoals[0].status, "completed")
        self.assertEqual(store.entries[-1].record, "A")
        self.assertEqual(store.entries[-1].parameters, WINDOW)
        self.assertEqual([e.capability for e in store.entries], ["record_info", "amplitude"])

    def test_budget_finalization_keeps_real_values_and_uses_same_agent_answer(self):
        agent, client = self.make([("record_info", {"record": "B"}), deliver()], client_class=ClosingClient)
        result = agent.run("记录B的采样率、时长和通道是什么？")
        self.assertEqual(result.stop_reason, "completed")
        self.assertEqual(client.interfaces[-1], ["finish_task"])
        self.assertTrue(client.budget_checks)
        payload = json.loads(client.seen[-1][1]["content"])
        metadata = next(e for e in payload["exact_evidence"] if e["capability"] == "record_info")
        sfreq = next(f for f in metadata["fields"] if f["path"] == ["sfreq"])
        self.assertEqual(sfreq["value"], 128.0)
        self.assertEqual(metadata["record"], "B")
        self.assertEqual([a["tool_name"] for a in result.tool_results], ["record_info", "finish_task"])

    def test_summary_and_full_can_use_actually_visible_history_without_forced_read(self):
        def cite_visible_history(messages):
            payload = json.loads(messages[1]["content"])
            ids = []
            for goal in payload.get("generic_summary", []):
                ids += [f["task_id"] for f in goal["facts"] if f.get("evidence", {}).get("fields")]
            for message in messages[2:]:
                if message["role"] == "tool":
                    observation = (json.loads(message["content"]).get("data") or {}).get("observation")
                    if observation and observation["result"]["success"]:
                        ids.append(observation["result_id"])
            self.assertTrue(ids, "The baseline must actually see the old result, not just its locator")
            return "finish_task", {"status": "completed", "answer": "先前真实采样率为128 Hz。",
                "coverage_complete": True, "coverage": [{"quote": payload["current_request"], "result_ids": ids}]}

        for mode in ("summary", "full"):
            with self.subTest(mode=mode):
                agent, _ = self.make([("record_info", {"record": "A"}), deliver(), cite_visible_history], mode)
                self.assertEqual(agent.run("查询记录A的采样率。").stop_reason, "completed")
                result = agent.continue_run("再告诉我刚才记录A的采样率，不重算。")
                self.assertEqual(result.stop_reason, "completed")
                self.assertEqual([r["tool_name"] for r in result.tool_results], ["finish_task"])
                self.assertEqual(len(agent.working_memory.store.entries), 1)

    def test_working_locator_is_not_treated_as_an_exact_old_value(self):
        def cite_locator(messages):
            payload = json.loads(messages[1]["content"])
            row = payload["archived_summaries"][0]["results"][0]
            self.assertFalse(payload["exact_evidence"])
            return "finish_task", {"status": "completed", "answer": "未实际读到值的错误声明。",
                "coverage_complete": True, "coverage": [{"quote": payload["current_request"], "result_ids": [row["task_id"]]}]}

        def read_locator(messages):
            row = json.loads(messages[1]["content"])["archived_summaries"][0]["results"][0]
            return "read_evidence", {"task_id": row["task_id"], "record": row["record"],
                "parameters": row["parameters"], "field_paths": [["SYNTH-C1", "alpha"]]}

        agent, _ = self.make([("psd", WINDOW), deliver(), cite_locator, read_locator, deliver()])
        self.assertEqual(agent.run("记录A的SYNTH-C1在0到2秒的alpha功率是多少？").stop_reason, "completed")
        result = agent.continue_run("读取刚才记录A的alpha历史精确值，不重新计算。")
        self.assertEqual(result.stop_reason, "completed")
        self.assertFalse(result.tool_results[0]["success"])
        self.assertTrue(result.tool_results[1]["success"])
        self.assertEqual(len(agent.working_memory.store.entries), 1)

    def test_assistant_self_report_cannot_create_trusted_read_visibility(self):
        agent, _ = self.make([("psd", WINDOW), deliver()])
        self.assertEqual(agent.run("记录A的SYNTH-C1在0到2秒分析alpha功率。").stop_reason, "completed")
        controller = agent.working_memory
        original = controller.store.entries[0]
        controller.begin_turn("再查原来记录A的alpha，不重算。")
        messages = controller.build_messages()
        self.assertNotIn(original.task_id, controller._visible_results(messages))
        messages.append({"role": "assistant", "content": json.dumps({
            "task_id": original.task_id, "fields": [{"path": ["SYNTH-C1", "alpha"], "value": -123}]})})
        self.assertNotIn(original.task_id, controller._visible_results(messages),
            "A model's fabricated fields are not a successful tool read or a program-rendered fact")

    def test_restore_enters_decision_and_original_epoch_drives_quality(self):
        first = "记录A的stimulus事件后0到1秒，给出有效试次数，不做基线或筛选。"
        second = "沿用记录A刚才的原试次补充质量测量，并解释处理来源，不重建或筛选。"
        goal = ("begin_subgoal", {"title": "原试次计数", "record": "A", "deliveries": [
            {"key": "epochs", "tool": "create_epochs", "scope": EVENT}],
            "requirements": [{"quote": first, "delivery_keys": ["epochs"]}]})

        def continued_goal(messages):
            observation = visible_epoch(messages)
            data = observation["result"]["data"]
            return "begin_subgoal", {"title": "原试次质量", "record": "A", "deliveries": [
                {"key": "quality", "tool": "epoch_quality", "scope": observation["scope"]}],
                "parameter_sources": {"quality": {"kind": "artifact", "artifact_id": data["artifact_id"]}},
                "dependencies": [observation["result_id"]],
                "requirements": [{"quote": second, "delivery_keys": ["quality"]}]}

        agent, client = self.make([goal, ("create_epochs", EVENT), deliver(),
            ("restore_subgoal", {"subgoal_id": "closure-s1", "reason": "核对创建原试次的真实处理并沿用原工件"}),
            continued_goal, artifact_measurement("epoch_quality"), deliver()])
        self.assertEqual(agent.run(first).stop_reason, "completed")
        self.assertEqual(agent.continue_run(second).stop_reason, "completed")
        store = agent.working_memory.store
        self.assertEqual([e.capability for e in store.entries], ["create_epochs", "epoch_quality"])
        original, quality = store.entries
        self.assertEqual(quality.evidence["binding"]["artifact_id"], original.evidence["binding"]["artifact_id"])
        self.assertEqual(quality.evidence["binding"]["artifact_fingerprint"], original.evidence["binding"]["artifact_fingerprint"])
        self.assertEqual(len(store.contexts["A"].artifacts), 1)
        restored = json.loads(client.seen[4][1]["content"])["restored_trajectories"]
        self.assertTrue(restored)
        observation = next(o for o in restored[0]["action_observations"] if o["request"]["name"] == "create_epochs")
        self.assertEqual(observation["result"]["data"]["artifact_id"], quality.evidence["binding"]["artifact_id"])
        self.assertIsNone(original.result["baseline"])

    def test_unrequested_epoch_rebuild_cannot_replace_pinned_original_process(self):
        first = "记录A的stimulus事件后0到1秒创建试次，不做基线。"
        second = "沿用记录A刚才的原试次做质量测量，不重建。"
        original_goal = ("begin_subgoal", {"title": "原试次", "record": "A", "deliveries": [
            {"key": "original", "tool": "create_epochs", "scope": EVENT}],
            "requirements": [{"quote": first, "delivery_keys": ["original"]}]})

        def quality_goal(messages):
            observation = visible_epoch(messages)
            return "begin_subgoal", {"title": "原试次质量", "record": "A", "deliveries": [
                {"key": "quality", "tool": "epoch_quality", "scope": observation["scope"]}],
                "dependencies": [observation["result_id"]],
                "parameter_sources": {"quality": {"kind": "artifact", "artifact_id": observation["result"]["data"]["artifact_id"]}},
                "requirements": [{"quote": second, "delivery_keys": ["quality"]}]}

        agent, _ = self.make([original_goal, ("create_epochs", EVENT), deliver(),
            ("restore_subgoal", {"subgoal_id": "closure-s1", "reason": "续用原试次"}),
            quality_goal, ("create_epochs", EVENT), artifact_measurement("epoch_quality"), deliver()])
        self.assertEqual(agent.run(first).stop_reason, "completed")
        original = agent.working_memory.store.entries[0]
        result = agent.continue_run(second)
        self.assertEqual(result.stop_reason, "completed")
        self.assertFalse(result.tool_results[2]["success"])
        store = agent.working_memory.store
        self.assertEqual(len(store.contexts["A"].artifacts), 1)
        self.assertEqual([e.capability for e in store.entries], ["create_epochs", "epoch_quality"])
        self.assertEqual(store.entries[-1].evidence["binding"]["artifact_id"], original.evidence["binding"]["artifact_id"])

    def test_same_request_recompute_quote_cannot_mint_execution_by_reparenting(self):
        def recompute_goal(messages):
            payload = json.loads(messages[1]["content"])
            sources = [e for e in payload["exact_evidence"] if e["capability"] == "psd"]
            if not sources:
                # A locator is enough to name a revision parent; its scientific
                # result must become visible before final numerical delivery.
                sources = [r for g in payload["archived_summaries"] for r in g["results"] if r["capability"] == "psd"]
            parent = sources[-1]["task_id"]
            return "begin_subgoal", {"title": "一次重算", "record": "A", "deliveries": [
                {"key": "power", "tool": "psd", "scope": WINDOW, "revision_of": parent}],
                "recompute_source": {"kind": "user", "turn": 2, "quote": payload["current_request"]}}

        agent, _ = self.make([("psd", WINDOW), deliver(),
            recompute_goal, ("psd", WINDOW), ("close_subgoal", {"status": "completed"}),
            recompute_goal, ("psd", WINDOW), deliver()])
        self.assertEqual(agent.run("记录A的SYNTH-C1在0到2秒计算PSD。").stop_reason, "completed")
        result = agent.continue_run("记录A的SYNTH-C1在0到2秒重新计算PSD一次。")
        self.assertEqual(result.stop_reason, "completed")
        entries = agent.working_memory.store.entries
        self.assertEqual(len(entries), 2, "One explicit recompute permits one fresh result, not a same-scope lineage loop")
        self.assertEqual(entries[-1].revision_of, entries[0].task_id)

    def test_verified_original_source_pins_auto_and_completed_reuse_paths(self):
        for path in ("auto_result", "completed_contract"):
            with self.subTest(path=path):
                store = ReliableWorkingMemoryStore("sourcepin", synthetic_records())
                store.turn = 1
                store.user_requests = ["记录A的stimulus事件后0到1秒创建试次并质量测量；请重新计算一次。"]
                create = {"key": "epoch", "tool": "create_epochs", "scope": EVENT}
                quality = {"key": "quality", "tool": "epoch_quality", "scope": EVENT}
                store.begin_subgoal("最初试次", "A", deliveries=[create])
                first = store.execute_numeric("create_epochs", EVENT)["observation"]
                first_id = first["result"]["data"]["artifact_id"]
                store.close_subgoal("completed")
                store.begin_subgoal("明确重建", "A", deliveries=[create, quality] if path == "auto_result" else [create],
                    recompute_source={"kind": "user", "turn": 1, "quote": "请重新计算一次"})
                second = store.execute_numeric("create_epochs", EVENT)["observation"]
                second_id = second["result"]["data"]["artifact_id"]
                self.assertNotEqual(first_id, second_id)
                if path == "completed_contract":
                    store.close_subgoal("completed")
                    store.begin_subgoal("新试次质量", "A", deliveries=[quality],
                        parameter_sources={"quality": {"kind": "artifact", "artifact_id": second_id}})
                store.execute_numeric("epoch_quality", {"artifact_id": second_id})
                self.assertEqual(store.close_subgoal("completed")["status"], "completed")
                before = len(store.entries)
                requested = store.begin_subgoal("原试次质量", "A", deliveries=[quality],
                    parameter_sources={"quality": {"kind": "artifact", "artifact_id": first_id}})
                self.assertEqual(requested["status"], "active")
                self.assertFalse(requested["progress"]["valid"])
                self.assertFalse(store.active.reused)
                result = store.execute_numeric("epoch_quality", {"artifact_id": first_id})
                self.assertEqual(result["status"], "observed")
                self.assertEqual(len(store.entries), before + 1)
                self.assertEqual(store.entries[-1].evidence["binding"]["artifact_id"], first_id)
                self.assertEqual(store.close_subgoal("completed")["status"], "completed")


if __name__ == "__main__":
    unittest.main()
