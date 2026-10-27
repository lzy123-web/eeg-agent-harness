"""Shared DAG semantics, not an autonomous model or EEG numerical evaluator."""

import json
import unittest

from eeg_harness.task_plan import (InputRef, DeliveryItem, TaskSpec, PlanGraph,
                                   TASK_SPEC_SCHEMA, PLAN_NODES_SCHEMA)
from eeg_harness.executor import _validate_schema


def output(key="power", *, start=0, end=2, refs=None):
    return {"key": key, "capability": "psd", "record": "record-one",
            "scope": {"channels": ["C1"], "start": start, "end": end},
            "input_refs": refs or []}


def task(task_id="measure", *, outputs=None, deps=None):
    return {"task_id": task_id, "goal": "比较明确的科学结果",
            "dependencies": deps or [], "required_outputs": outputs or [output()]}


def ref(task_id="measure", key="power", level="result"):
    return {"task_id": task_id, "key": key, "fields": [["C1", "alpha"]], "level": level}


class TaskPlanTest(unittest.TestCase):
    def test_public_schema_and_structured_roundtrip(self):
        value = task(outputs=[output("first"), output("second", start=2, end=4)])
        _validate_schema(value, TASK_SPEC_SCHEMA)
        _validate_schema({"nodes": [value]}, {"type": "object", "properties": {"nodes": PLAN_NODES_SCHEMA},
                                              "required": ["nodes"], "additionalProperties": False})
        parsed = TaskSpec.from_dict(value)
        self.assertEqual(len(parsed.required_outputs), 2)
        restored = TaskSpec.from_dict(parsed.to_dict(), runtime=True)
        self.assertEqual(restored.to_dict(), parsed.to_dict())
        json.dumps(restored.to_dict(), ensure_ascii=False, allow_nan=False)

    def test_model_cannot_supply_execution_facts(self):
        for extra in ({"status": "TASK_COMPLETED"}, {"revision": 2},
                      {"outputs": {"power": "invented"}}, {"surprise": 1}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                TaskSpec.from_dict({**task(), **extra})

    def test_strict_fields_finite_values_paths_and_required_items(self):
        malformed = [
            {**output(), "unrecognized": True},
            {**output(), "required": 1},
            {**output(), "scope": {"start": float("nan")}},
            {**output(), "acceptance_rule": [{"path": ["x"], "op": "gt", "value": 3}]},
            {**output(), "acceptance_rule": [{"path": [], "op": "eq", "value": 3}]},
        ]
        for value in malformed:
            with self.subTest(value=value), self.assertRaises(ValueError):
                DeliveryItem.from_dict(value)
        with self.assertRaises(ValueError):
            InputRef.from_dict({**ref(), "fields": [["x"]] * 5})
        with self.assertRaises(ValueError):
            InputRef.from_dict({**ref(), "fields": [[True]]})
        with self.assertRaises(ValueError):
            TaskSpec.from_dict(task(outputs=[{**output(), "required": False}]))
        with self.assertRaises(ValueError):
            TaskSpec.from_dict(task(outputs=[output(), output()]))

    def test_submit_rejects_unknown_reference_cycle_and_undeclared_dependency_atomically(self):
        graph = PlanGraph()
        graph.submit([task()])
        before = graph.to_dict()
        for bad in (
            task("child", deps=["missing"]),
            task("child", outputs=[output(refs=[ref()])]),
            task("child", deps=["measure"], outputs=[output(refs=[ref(key="missing")])]),
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                graph.submit([bad])
            self.assertEqual(graph.to_dict(), before)
        with self.assertRaises(ValueError):
            PlanGraph().submit([task("a", deps=["b"]), task("b", deps=["a"])])
        with self.assertRaises(ValueError):
            graph.submit([task()])

    def test_ready_allows_real_key_from_partly_blocked_parent(self):
        graph = PlanGraph()
        graph.submit([task(outputs=[output(), output("later", start=2, end=4)]),
                      task("child", deps=["measure"], outputs=[output(refs=[ref()])]),
                      task("control", deps=["measure"]), task("independent")])
        self.assertEqual([n.task_id for n in graph.ready_nodes()], ["measure", "independent"])
        graph.mark_output("measure", "power", {"result_id": "actual-t1"}, status="TOOL_SUCCEEDED")
        self.assertFalse(graph.dependency_state("child")["ready"])
        graph.mark_output("measure", "power", {"result_id": "actual-t1"})
        graph.set_status("measure", "WAITING_INPUT", ["window for later result missing"])
        self.assertEqual([n.task_id for n in graph.ready_nodes()], ["child", "independent"])
        graph.set_status("measure", "TASK_COMPLETED", [])
        self.assertIn("control", [n.task_id for n in graph.ready_nodes()])

    def test_bound_metadata_is_copied_not_a_shared_mutable_result(self):
        graph = PlanGraph()
        declaration = task()
        graph.submit([declaration])
        declaration["required_outputs"][0]["scope"]["start"] = 55
        evidence = {"result_id": "actual-t1", "version": {"source": 1}}
        graph.mark_output("measure", "power", evidence)
        evidence["version"]["source"] = 99
        self.assertEqual(graph.nodes["measure"].required_outputs[0].scope["start"], 0)
        self.assertEqual(graph.nodes["measure"].outputs["power"]["version"]["source"], 1)

    def test_local_revision_preserves_stable_id_old_evidence_and_independent_work(self):
        graph = PlanGraph()
        graph.submit([task(), task("child", deps=["measure"], outputs=[output(refs=[ref()])]),
                      task("grandchild", deps=["child"], outputs=[output(refs=[ref("child")])]),
                      task("independent")])
        for ident in graph.nodes:
            graph.mark_output(ident, "power", {"result_id": f"actual-{ident}"})
            graph.set_status(ident, "TASK_COMPLETED")
        result = graph.revise("measure", {"required_outputs": [output(start=4, end=6)]}, "用户修订时间窗")
        self.assertEqual(result["revision"], 2)
        self.assertEqual(result["invalidated"], ["child", "grandchild"])
        self.assertEqual(graph.nodes["measure"].task_id, "measure")
        self.assertFalse(graph.nodes["measure"].outputs)
        self.assertEqual(graph.nodes["independent"].status, "TASK_COMPLETED")
        self.assertEqual(graph.nodes["measure"].revision_history[0]["snapshot"]["outputs"]["power"],
                         {"result_id": "actual-measure"})
        self.assertFalse(graph.dependency_state("grandchild")["ready"])
        self.assertEqual([n.task_id for n in graph.ready_nodes()], ["measure"])
        graph.mark_output("measure", "power", {"result_id": "actual-new"})
        self.assertIn("child", [n.task_id for n in graph.ready_nodes()])

    def test_revision_only_invalidates_consumed_changed_keys(self):
        graph = PlanGraph()
        graph.submit([task(outputs=[output("left"), output("right", start=2, end=4)]),
                      task("left-user", deps=["measure"], outputs=[output(refs=[ref(key="left")])]),
                      task("right-user", deps=["measure"], outputs=[output(refs=[ref(key="right")])])])
        for key in ("left", "right"):
            graph.mark_output("measure", key, {"result_id": f"actual-{key}"})
        for ident in ("left-user", "right-user"):
            graph.mark_output(ident, "power", {"result_id": ident})
            graph.set_status(ident, "TASK_COMPLETED")
        result = graph.revise("measure", {"required_outputs": [output("left", start=4, end=6),
                              output("right", start=2, end=4)]}, "只改左窗")
        self.assertEqual(result["invalidated"], ["left-user"])
        self.assertIn("right", graph.nodes["measure"].outputs)
        self.assertEqual(graph.nodes["right-user"].status, "TASK_COMPLETED")

    def test_renaming_is_same_identity_not_new_goal_or_recomputation(self):
        graph = PlanGraph()
        graph.submit([task()])
        graph.mark_output("measure", "power", {"result_id": "real"})
        graph.set_status("measure", "TASK_COMPLETED")
        change = graph.revise("measure", {"goal": "换个说法表达同一科学目的"}, "只改变描述")
        self.assertEqual(change["changed_keys"], [])
        self.assertEqual(graph.nodes["measure"].status, "TASK_COMPLETED")
        self.assertEqual(graph.nodes["measure"].outputs["power"], {"result_id": "real"})

    def test_failed_replan_does_not_mutate_graph_and_limits_are_bounded(self):
        graph = PlanGraph(max_nodes=2, max_revisions=2)
        graph.submit([task(), task("child", deps=["measure"])])
        before = graph.to_dict()
        with self.assertRaises(ValueError):
            graph.revise("measure", {"dependencies": ["child"]}, "creates cycle")
        self.assertEqual(graph.to_dict(), before)
        with self.assertRaises(ValueError):
            graph.submit([task("extra")])
        with self.assertRaises(ValueError):
            graph.submit([task("fresh")], replace=True)
        with self.assertRaises(ValueError):
            graph.revise("measure", {"status": "TASK_COMPLETED"}, "fake state")
        with self.assertRaises(ValueError):
            graph.revise("measure", {"goal": graph.nodes["measure"].goal}, "no op")
        graph.revise("measure", {"goal": "同一目的另一个名称"}, "rename")
        with self.assertRaises(ValueError):
            graph.revise("measure", {"goal": "再改"}, "over limit")

    def test_historical_and_current_versions_are_independent_dependencies(self):
        graph = PlanGraph()
        graph.submit([task()])
        graph.mark_output("measure", "power", {"result_id": "old-result", "scope": {"start": 0}})
        graph.set_status("measure", "TASK_COMPLETED")
        graph.revise("measure", {"required_outputs": [output(start=4, end=6)]}, "修改窗口保留旧版")
        graph.submit([task("compare", deps=["measure"], outputs=[output(refs=[
            {**ref(), "revision": 1}, ref()])])])
        self.assertFalse(graph.dependency_state("compare")["ready"])
        old = graph.resolve_ref({**ref(), "revision": 1})
        self.assertEqual(old["revision"], 1)
        self.assertEqual(old["output"]["result_id"], "old-result")
        graph.mark_output("measure", "power", {"result_id": "new-result", "scope": {"start": 4}})
        self.assertTrue(graph.dependency_state("compare")["ready"])
        self.assertEqual(graph.resolve_ref(ref())["output"]["result_id"], "new-result")
        old["output"]["result_id"] = "tamper"
        self.assertEqual(graph.resolve_ref({**ref(), "revision": 1})["output"]["result_id"], "old-result")
        before = graph.to_dict()
        with self.assertRaises(ValueError):
            graph.submit([task("future", deps=["measure"], outputs=[output(refs=[{**ref(), "revision": 3}])])])
        self.assertEqual(graph.to_dict(), before)

    def test_pinned_delivered_version_is_not_invalidated_by_later_revision(self):
        graph = PlanGraph()
        graph.submit([task(), task("pinned", deps=["measure"], outputs=[output(refs=[{**ref(), "revision": 1}])]),
                      task("following", deps=["measure"], outputs=[output(refs=[ref()])])])
        for ident in graph.nodes:
            graph.mark_output(ident, "power", {"result_id": ident})
            graph.set_status(ident, "TASK_COMPLETED")
        result = graph.revise("measure", {"required_outputs": [output(start=4, end=6)]}, "新的窗口")
        self.assertEqual(result["invalidated"], ["following"])
        self.assertEqual(graph.nodes["pinned"].status, "TASK_COMPLETED")
        self.assertTrue(graph.dependency_state("pinned")["ready"])
        self.assertFalse(graph.dependency_state("following")["ready"])


if __name__ == "__main__":
    unittest.main()
