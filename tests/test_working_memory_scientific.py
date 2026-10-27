"""Real numerical tools under scripted decisions: mechanism, not autonomy."""
import json
import unittest

from eeg_harness.working_memory_agent import WorkingMemoryEEGAgent
from eeg_harness.research.task_memory import synthetic_records
from eeg_harness.tooling import ToolRequest
from test_working_memory import ScriptedClient, finish, WINDOW, EVENT
from test_working_memory_issue50_independent import visible_observations, shown_entry


class ScientificControllerTest(unittest.TestCase):
    def agent(self, actions, mode="working"):
        return WorkingMemoryEEGAgent(ScriptedClient(actions), synthetic_records(),
            session_id="science51", memory_version="scientific", context_mode=mode)

    def test_multi_instance_observations_drive_next_action_and_archive(self):
        later = {**WINDOW, "start": 2, "end": 4}
        def second(messages):
            card = json.loads(messages[1]["content"])["active_task"]
            self.assertFalse(card["delivery_check"]["valid"])
            self.assertEqual(len(visible_observations(messages)), 1)
            return "psd", later
        def compare(messages):
            observations = visible_observations(messages)
            self.assertEqual(len(observations), 2)
            return "compare_results", {"left_result": observations[0]["result_id"],
                "right_result": observations[1]["result_id"],
                "left_path": ["SYNTH-C1", "alpha"], "right_path": ["SYNTH-C1", "alpha"]}
        agent = self.agent([("focus_task", {"title": "比较两个窗口", "requirements": [
            {"tool": "psd", "record": "A", "scope": WINDOW},
            {"tool": "psd", "record": "A", "scope": later}]}),
            ("psd", WINDOW), second, compare, finish()])
        result = agent.run("记录A SYNTH-C1在0到2秒与2到4秒的alpha功率分别是多少，比较差值和比值。")
        self.assertEqual(result.stop_reason, "completed")
        controller = agent.working_memory
        self.assertEqual(len(controller.store.subgoals), 1)
        self.assertEqual(len(controller.store.subgoals[0].result_ids), 2)
        self.assertEqual(controller.store.subgoals[0].status, "completed")
        comp = controller.comparisons[0]
        a, b = [r["value"] for r in comp["operands"]]
        self.assertEqual(comp["right_minus_left"], b-a)
        self.assertEqual(comp["right_divided_by_left"], b/a)
        final, _ = controller.build_final_messages()
        self.assertIn(comp["canonical_display"], json.dumps(final, ensure_ascii=False))
        self.assertEqual(comp["difference_unit"], "V²")

    def test_comparison_rejects_different_quantity_or_band_and_stale(self):
        agent = self.agent([("psd", WINDOW), ("amplitude", WINDOW), finish()])
        self.assertEqual(agent.run("记录A SYNTH-C1在0到2秒的PSD和RMS。").stop_reason, "completed")
        c = agent.working_memory
        a, b = c.store.entries
        self.assertEqual(c._compare(a.task_id, a.task_id, ["SYNTH-C1", "alpha"], ["SYNTH-C1", "theta"])["code"], "INCOMPARABLE_FIELDS")
        self.assertEqual(c._compare(a.task_id, b.task_id, ["SYNTH-C1", "alpha"], ["SYNTH-C1", "rms"])["code"], "INCOMPARABLE_FIELDS")
        self.assertEqual(c._compare("not-real", a.task_id, ["SYNTH-C1", "alpha"], ["SYNTH-C1", "alpha"])["code"], "INVALID_RESULT")
        self.assertFalse(c.comparisons)

    def test_restore_actual_process_drives_original_artifact_quality(self):
        def power(messages):
            obs = next(o for o in visible_observations(messages) if o["request"]["name"] == "create_epochs")
            return "event_bandpower", {"artifact_id": obs["result"]["data"]["artifact_id"]}
        def restore(messages):
            row = shown_entry(messages, "create_epochs")
            return "restore_task", {"task_id": row["task_id"], "reason": "检查原试次构建过程再追加质量测量"}
        def quality(messages):
            restored = json.loads(messages[1]["content"])["restored_trajectories"][0]
            obs = restored["action_observations"]
            self.assertEqual([o["request"]["name"] for o in obs], ["create_epochs", "event_bandpower"])
            return "epoch_quality", {"artifact_id": obs[0]["result"]["data"]["artifact_id"]}
        agent = self.agent([("focus_task", {"title": "事件试次及功率", "requirements": [
            {"tool": "create_epochs", "record": "A", "scope": EVENT},
            {"tool": "event_bandpower", "record": "A", "scope": EVENT}]}),
            ("create_epochs", EVENT), power, finish(), restore, quality, finish()])
        self.assertEqual(agent.run("记录A stimulus事件后0到1秒试次，计算频带功率。").stop_reason, "completed")
        old = agent.working_memory.store.entries[0].result["artifact_id"]
        self.assertEqual(agent.continue_run("核对原试次创建和分析过程，沿用原试次追加质量测量，不重建。").stop_reason, "completed")
        c = agent.working_memory
        self.assertEqual(c.store.entries[-1].evidence["binding"]["artifact_id"], old)
        self.assertEqual(len(c.store.contexts["A"].artifacts), 1)
        self.assertEqual(c.restore_count, 1)

    def test_suspend_switch_cannot_hide_declared_missing_result(self):
        agent = self.agent([])
        c = agent.working_memory
        c.begin_turn("记录A SYNTH-C1在0到2秒和2到4秒PSD，另查记录信息。")
        c.store.focus_task("两个窗口", requirements=[{"tool":"psd","record":"A","scope":WINDOW},
            {"tool":"psd","record":"A","scope":{**WINDOW,"start":2,"end":4}}])
        c.store.execute_action("psd", WINDOW)
        c.store.focus_task("信息", requirements=[{"tool":"record_info","record":"A","scope":{}}])
        c.store.execute_action("record_info", {})
        c.build_messages()
        result = c.execute(ToolRequest("finish_task", {"status":"completed","answer":"都完成"}, "finish"))
        self.assertEqual(result.error_code, "UNFINISHED_DECLARED_TASK")

    def test_modes_share_contract_and_no_numeric_executor_fork(self):
        from eeg_harness.agent import EEGAgent
        self.assertIs(WorkingMemoryEEGAgent.run, EEGAgent.run)
        for mode in ("full", "summary", "working"):
            agent = self.agent([("psd", WINDOW), finish()], mode)
            self.assertEqual(agent.run("记录A SYNTH-C1在0到2秒PSD。").stop_reason, "completed")
            self.assertEqual(len(agent.working_memory.store.entries), 1)
            json.dumps(agent.working_memory.snapshot(), allow_nan=False)

    def test_two_exact_reads_preserve_both_values_for_final_generation(self):
        agent = self.agent([("amplitude", WINDOW), ("psd", WINDOW), finish()])
        agent.run("记录A SYNTH-C1在0到2秒的RMS和alpha功率。")
        c = agent.working_memory
        a, b = c.store.entries
        c.begin_turn("回顾记录A第一次窗口的RMS和alpha功率，不重新计算。")
        for entry, field in ((a,"rms"),(b,"alpha")):
            out = c.execute(ToolRequest("read_result", {"result_id":entry.task_id,
                "fields":[["SYNTH-C1",field]]}, entry.task_id))
            self.assertTrue(out.success)
        c.build_messages()
        final, _ = c.build_final_messages()
        payload = json.loads(final[1]["content"])
        evidence = {row["task_id"]:row for row in payload["available_evidence"]}
        self.assertEqual(evidence[a.task_id]["fields"][0]["value"], a.result["SYNTH-C1"]["rms"])
        self.assertEqual(evidence[b.task_id]["fields"][0]["value"], b.result["SYNTH-C1"]["alpha"])
        self.assertEqual(len(c.store.entries), 2)


if __name__ == "__main__":
    unittest.main()
