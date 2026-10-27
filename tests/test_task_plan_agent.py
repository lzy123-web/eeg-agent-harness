"""Controlled decisions on the real EEG executor, not model-autonomy scores.

The scripted client deliberately exercises common and incorrect proposals. No
expected task order or answer is part of the production Agent entry point.
"""
import json
import unittest
import traceback
from dataclasses import replace

import numpy as np

from eeg_harness.agent import EEGAgent
from eeg_harness.task_plan_agent import TaskPlanEEGAgent
from eeg_harness.research.task_memory import synthetic_records
from eeg_harness.research.task_memory_v2 import independent_oracle
from test_working_memory import ScriptedClient, finish, WINDOW, EVENT


ARMS = ("A", "B", "C", "A-equivalent")
LATER = {**WINDOW, "start": 2, "end": 4}
REVISED = {**WINDOW, "start": 4, "end": 6}


def delivery(key, capability="psd", scope=None, record="A", refs=None, rules=None):
    return {"key": key, "capability": capability, "record": record,
            "scope": WINDOW.copy() if scope is None else scope,
            "input_refs": refs or [], "acceptance_rule": rules or []}


def node(ident, deliveries, deps=None, optional=None):
    return {"task_id": ident, "goal": f"科学目的 {ident}", "dependencies": deps or [],
            "required_outputs": deliveries, "optional_operations": optional or []}


def reference(ident, key, level="result", fields=None):
    return {"task_id": ident, "key": key, "level": level, "fields": fields or []}


def payload(messages):
    return json.loads(messages[1]["content"])


class InspectableScriptedClient(ScriptedClient):
    def __init__(self, actions):
        super().__init__(actions)
        self.errors = []

    def complete(self, messages, tools, **kwargs):
        try:
            return super().complete(messages, tools)
        except Exception:
            self.errors.append(traceback.format_exc())
            raise


class TaskPlanAgentTest(unittest.TestCase):
    def agent(self, actions, arm="C"):
        self.last_client = InspectableScriptedClient(actions)
        return TaskPlanEEGAgent(self.last_client, synthetic_records(), arm=arm,
                               session_id=f"controlled52-{arm}")

    def assert_completed(self, result):
        self.assertEqual(result.stop_reason, "completed", {"stop": result.stop_reason,
            "errors": self.last_client.errors,
            "tools": [(r["tool_name"], r["success"], r["error"]) for r in result.tool_results]})

    def test_shared_original_agent_and_real_numeric_oracle(self):
        self.assertIs(TaskPlanEEGAgent.run, EEGAgent.run)
        for arm in ARMS:
            with self.subTest(arm=arm):
                a = self.agent([("plan_tasks", {"nodes": [node("window", [delivery("power")])]}),
                                ("psd", {}), finish()], arm)
                self.assert_completed(a.run("记录A SYNTH-C1在0到2秒的alpha功率。"))
                entry = a.working_memory.store.entries[0]
                expected = independent_oracle(a.working_memory.store.records["A"],
                    {"capability": "psd", "parameters": WINDOW}, ["SYNTH-C1", "alpha"])
                self.assertTrue(np.isclose(float(entry.result["SYNTH-C1"]["alpha"]), expected, rtol=.005, atol=1e-13))
                self.assertEqual(a.working_memory.graph.nodes["window"].status, "TASK_COMPLETED")

    def test_two_same_capability_windows_do_not_complete_after_one_result(self):
        for arm in ARMS:
            with self.subTest(arm=arm):
                def after_first(messages):
                    view = payload(messages)
                    current = next(n for n in view["plan"] if n["task_id"] == "two-windows")
                    self.assertNotEqual(current["status"], "TASK_COMPLETED")
                    summary = next(n for n in view["task_summaries"] if n["task_id"] == "two-windows")
                    self.assertEqual(set(summary["outputs"]), {"early"})
                    return "psd", LATER
                a = self.agent([("plan_tasks", {"nodes": [node("two-windows", [
                    delivery("early"), delivery("late", scope=LATER)])]}),
                    ("psd", WINDOW), after_first, finish()], arm)
                self.assert_completed(a.run("记录A SYNTH-C1在0到2秒和2到4秒分别计算alpha功率。"))
                self.assertEqual(len(a.working_memory.store.entries), 2)
                self.assertEqual(set(a.working_memory.graph.nodes["two-windows"].outputs), {"early", "late"})

    def test_failed_optional_metadata_attempt_does_not_create_scientific_debt(self):
        for arm in ARMS:
            with self.subTest(arm=arm):
                a = self.agent([("plan_tasks", {"nodes": [node("window", [delivery("power")], optional=["list_events"])]}),
                    ("list_events", {"unexpected_argument": 2}), ("psd", {}), finish()], arm)
                result = a.run("记录A SYNTH-C1在0到2秒的alpha功率；必要时可查看事件元信息。")
                self.assert_completed(result)
                failed = [r for r in result.tool_results if not r["success"]]
                self.assertTrue(failed)
                self.assertEqual(a.working_memory.graph.nodes["window"].status, "TASK_COMPLETED")
                self.assertEqual(len(a.working_memory.store.entries), 1)

    def test_mixed_graph_passes_actual_epoch_object_between_nodes(self):
        for arm in ARMS:
            with self.subTest(arm=arm):
                nodes = [node("epochs", [delivery("trials", "create_epochs", EVENT)]),
                    node("continuous", [delivery("rms", "amplitude", WINDOW)]),
                    node("power", [delivery("theta", "event_bandpower", EVENT,
                        refs=[reference("epochs", "trials")])], deps=["epochs"])]
                def event_power(messages):
                    p = payload(messages)
                    self.assertEqual(p["current_plan_task"], "power")
                    self.assertTrue(p["dependency_evidence"])
                    return "event_bandpower", {}
                a = self.agent([("plan_tasks", {"nodes": nodes}), ("create_epochs", {}),
                    ("amplitude", {}), event_power, finish()], arm)
                self.assert_completed(a.run("记录A stimulus事件后0到1秒建立试次并计算theta功率；另算记录A SYNTH-C1在0到2秒RMS。不筛选、不基线校正。"))
                s = a.working_memory.store
                self.assertEqual([e.capability for e in s.entries], ["create_epochs", "amplitude", "event_bandpower"])
                self.assertEqual(s.entries[0].evidence["binding"]["artifact_id"], s.entries[2].evidence["binding"]["artifact_id"])
                self.assertEqual(len(s.contexts["A"].artifacts), 1)

    def test_stable_revision_reuses_unchanged_result_and_preserves_old_entries(self):
        for arm in ARMS:
            with self.subTest(arm=arm):
                outputs = [delivery("early"), delivery("late", scope=LATER)]
                a = self.agent([("plan_tasks", {"nodes": [node("two", outputs)]}),
                    ("psd", WINDOW), ("psd", LATER), finish(),
                    ("revise_plan", {"task_id": "two", "updates": {"required_outputs": [
                        delivery("early", scope=REVISED), delivery("late", scope=LATER)]}, "reason": "用户仅修订第一个窗口"}),
                    ("psd", REVISED), finish()], arm)
                self.assert_completed(a.run("记录A SYNTH-C1在0到2秒和2到4秒分别计算PSD。"))
                old_entries = list(a.working_memory.store.entries)
                self.assert_completed(a.continue_run("将记录A SYNTH-C1第一个窗口改成4到6秒重新计算PSD；第二个2到4秒结果沿用原值。"))
                s, n = a.working_memory.store, a.working_memory.graph.nodes["two"]
                self.assertEqual(len(s.entries), 3)
                self.assertEqual(s.entries[:2], old_entries)
                self.assertEqual(n.revision, 2)
                self.assertEqual(n.outputs["late"]["result_id"], old_entries[1].task_id)
                self.assertEqual(s.entries[-1].revision_of, old_entries[0].task_id)

    def test_explicit_exact_history_read_is_visible_before_final_answer(self):
        for arm in ARMS:
            with self.subTest(arm=arm):
                def inspect(messages):
                    p = payload(messages)
                    rendered = json.dumps(p, ensure_ascii=False)
                    self.assertIn("SYNTH-C1", rendered)
                    self.assertIn("alpha", rendered)
                    actual = a.working_memory.store.entries[0].result["SYNTH-C1"]["alpha"]
                    self.assertIn(str(actual), rendered)
                    return finish()
                a = self.agent([("plan_tasks", {"nodes": [node("window", [delivery("power")])]}),
                    ("psd", {}), finish(),
                    ("read_dependency", {"task_id": "window", "key": "power", "level": "result", "fields": [["SYNTH-C1", "alpha"]]}),
                    inspect], arm)
                self.assert_completed(a.run("记录A SYNTH-C1在0到2秒的alpha功率。"))
                self.assert_completed(a.continue_run("请查回记录A原来0到2秒的alpha功率，别重算。"))
                self.assertEqual(len(a.working_memory.store.entries), 1)

    def test_process_read_enters_next_input_before_original_artifact_quality(self):
        for arm in ARMS:
            with self.subTest(arm=arm):
                def quality(messages):
                    p = payload(messages)
                    self.assertTrue(p["restored_trajectories"])
                    observations = p["restored_trajectories"][0]["action_observations"]
                    self.assertEqual(observations[0]["request"]["name"], "create_epochs")
                    return "epoch_quality", {}
                a = self.agent([("plan_tasks", {"nodes": [node("epochs", [delivery("trials", "create_epochs", EVENT)])]}),
                    ("create_epochs", {}), finish(),
                    ("plan_tasks", {"nodes": [node("quality", [delivery("quality", "epoch_quality", EVENT,
                        refs=[reference("epochs", "trials", "process")])], deps=["epochs"])]}),
                    ("read_dependency", {"task_id": "epochs", "key": "trials", "level": "process"}),
                    quality, finish()], arm)
                self.assert_completed(a.run("记录A stimulus事件后0到1秒建立试次，不筛选。"))
                original = a.working_memory.store.entries[0].evidence["binding"]["artifact_id"]
                self.assert_completed(a.continue_run("请核对原试次处理过程，沿用记录A原来的stimulus试次追加质量测量，不重建、不筛选。"))
                s = a.working_memory.store
                self.assertEqual(s.entries[-1].evidence["binding"]["artifact_id"], original)
                self.assertEqual(len(s.contexts["A"].artifacts), 1)

    def test_missing_event_parameters_allow_independent_continuous_branch(self):
        a = self.agent([("plan_tasks", {"nodes": [node("events", [delivery("trials", "create_epochs", {"labels": ["stimulus"]})]),
            node("continuous", [delivery("power")])]}),
            ("wait_node", {"task_id": "events", "reason": "尚缺用户指定的事件相对窗口"}),
            ("psd", {}), finish("clarification_required", unresolved=["尚缺用户指定的事件相对窗口"])])
        result = a.run("记录A stimulus事件建立试次，窗口稍后补充；先算记录A SYNTH-C1在0到2秒的PSD。")
        self.assertEqual(result.stop_reason, "clarification_required", self.last_client.errors)
        self.assertEqual(a.working_memory.graph.nodes["continuous"].status, "TASK_COMPLETED")
        self.assertEqual(a.working_memory.graph.nodes["events"].status, "WAITING_INPUT")
        self.assertEqual([e.capability for e in a.working_memory.store.entries], ["psd"])

    def test_cropped_wrong_record_plan_scope_never_authorizes_numerics(self):
        a = self.agent([("plan_tasks", {"nodes": [node("wrong", [delivery("power", scope=LATER)])]}),
            ("psd", {"request_span": "SYNTH-C1在2到4秒计算PSD"}), finish("partial", unresolved=["A记录没有获授权使用B记录的2到4秒窗口"])])
        result = a.run("记录A SYNTH-C1在0到2秒计算PSD；记录B SYNTH-C1在2到4秒计算PSD。")
        self.assertEqual(result.stop_reason, "partial", self.last_client.errors)
        self.assertFalse(a.working_memory.store.entries)
        self.assertTrue(any(not r["success"] for r in result.tool_results))

    def test_declared_scientific_condition_diagnostics_available_to_strong_baseline(self):
        # Injected wrong completion, explicitly not a natural failure rate.
        source = "只有试次数至少4才认为该结果满足要求"
        criterion = {"path": ["valid_epoch_count"], "op": "gte", "value": 4, "source": source}
        for arm in ARMS:
            with self.subTest(arm=arm):
                def inspect(messages):
                    r = next(json.loads(m["content"])["data"] for m in reversed(messages) if m["role"] == "tool")
                    self.assertFalse(r["scientifically_accepted"])
                    self.assertTrue(r["all_outputs_present"])
                    return finish("partial", unresolved=["实际试次数不满足用户指定的至少4次要求"])
                a = self.agent([("plan_tasks", {"nodes": [node("epochs", [delivery("trials", "create_epochs", EVENT, rules=[criterion])])]}),
                    ("create_epochs", {}), ("check_deliveries", {"task_id": "epochs"}), inspect], arm)
                r = a.run(f"记录A stimulus事件后0到1秒建立试次；{source}。")
                self.assertEqual(r.stop_reason, "partial", self.last_client.errors)
                self.assertNotEqual(a.working_memory.graph.nodes["epochs"].status, "TASK_COMPLETED")

    def test_old_and_new_versions_feed_actual_comparison_without_recomputation(self):
        for arm in ARMS:
            with self.subTest(arm=arm):
                refs = [{**reference("window", "power", fields=[["SYNTH-C1", "alpha"]]), "revision": 1},
                        reference("window", "power", fields=[["SYNTH-C1", "alpha"]])]
                a = self.agent([("plan_tasks", {"nodes": [node("window", [delivery("power")])]}),
                    ("psd", {}), finish(),
                    ("revise_plan", {"task_id": "window", "updates": {
                        "required_outputs": [delivery("power", scope=REVISED)]}, "reason": "用户更改时间窗"}),
                    ("psd", {}),
                    ("plan_tasks", {"nodes": [node("compare", [delivery("change", "compare_results", {}, refs=refs)], deps=["window"])]}),
                    ("compare_results", {}), finish()], arm)
                self.assert_completed(a.run("记录A SYNTH-C1在0到2秒的alpha功率。"))
                self.assert_completed(a.continue_run("将记录A SYNTH-C1的窗口改成4到6秒重新计算alpha功率，并比较新旧结果差值和比值。"))
                c = a.working_memory
                self.assertEqual(len(c.store.entries), 2)
                comparison = c.comparisons[-1]
                old, new = c.store.entries
                self.assertEqual([o["result_id"] for o in comparison["operands"]], [old.task_id, new.task_id])
                self.assertAlmostEqual(comparison["right_minus_left"],
                    float(new.result["SYNTH-C1"]["alpha"])-float(old.result["SYNTH-C1"]["alpha"]), places=20)
                self.assertEqual(c.graph.nodes["compare"].status, "TASK_COMPLETED")

    def test_record_source_change_blocks_stale_dependency_in_every_arm(self):
        for arm in ARMS:
            with self.subTest(arm=arm):
                a = self.agent([("plan_tasks", {"nodes": [node("epochs", [delivery("trials", "create_epochs", EVENT)])]}),
                    ("create_epochs", {}), finish(),
                    ("plan_tasks", {"nodes": [node("power", [delivery("theta", "event_bandpower", EVENT,
                        refs=[reference("epochs", "trials")])], deps=["epochs"])]}),
                    ("select_task", {"task_id": "power"}),
                    ("read_dependency", {"task_id": "epochs", "key": "trials", "level": "result"}),
                    finish("partial", unresolved=["来源记录已更换，原试次不再适用"])], arm)
                self.assert_completed(a.run("记录A stimulus事件后0到1秒建立试次。"))
                c = a.working_memory
                original = c.store.entries[0]
                context = c.store.contexts["A"]
                context.record = replace(context.record, source="synthetic://replacement-record")
                r = a.continue_run("沿用原记录A stimulus试次计算theta功率，若来源已经变化请明确停止，不重建。")
                self.assertEqual(r.stop_reason, "partial", self.last_client.errors)
                self.assertFalse(c.graph.dependency_state("power")["ready"])
                errors = [row["error"]["code"] for row in r.tool_results if not row["success"]]
                self.assertIn("DEPENDENCY_NOT_READY", errors)
                self.assertIn("STALE_RESULT", errors)
                self.assertEqual(c._inputs(c.graph.nodes["power"])[0]["level"], "missing")
                self.assertEqual(c.store.entries, [original])

    def test_injected_wrong_completion_exposes_acceptance_automation_not_model_success(self):
        source = "只有试次数至少4才接受该试次结果"
        criterion = {"path": ["valid_epoch_count"], "op": "gte", "value": 4, "source": source}
        for arm in ARMS:
            with self.subTest(arm=arm):
                a = self.agent([("plan_tasks", {"nodes": [
                    node("epochs", [delivery("trials", "create_epochs", EVENT, rules=[criterion])]),
                    node("power", [delivery("theta", "event_bandpower", EVENT,
                        refs=[reference("epochs", "trials")])], deps=["epochs"])]}),
                    ("create_epochs", {}), ("check_deliveries", {"task_id": "epochs"}),
                    ("complete_node", {"task_id": "epochs"}),
                    finish("partial", unresolved=["实际3试次，不符合至少4试次的要求"])], arm)
                r = a.run(f"记录A stimulus事件后0到1秒建立试次，{source}，满足后计算theta功率。")
                self.assertEqual(r.stop_reason, "partial", self.last_client.errors)
                checked = next(x["data"] for x in r.tool_results if x["tool_name"] == "check_deliveries")
                self.assertTrue(checked["all_outputs_present"])
                self.assertFalse(checked["scientifically_accepted"])
                self.assertEqual(checked["outputs"][0]["predicates"][0]["value"], 3)
                completed = next(x for x in r.tool_results if x["tool_name"] == "complete_node")
                automatic = arm in {"C", "A-equivalent"}
                self.assertEqual(completed["success"], not automatic)
                self.assertEqual(a.working_memory.graph.dependency_state("power")["ready"], not automatic)
                if automatic:
                    self.assertEqual(completed["error"]["code"], "SCIENTIFIC_ACCEPTANCE_FAILED")
                self.assertEqual(len(a.working_memory.store.entries), 1)


if __name__ == "__main__":
    unittest.main()
