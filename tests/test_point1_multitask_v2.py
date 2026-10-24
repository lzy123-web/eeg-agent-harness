import json
import os
import contextlib
import io
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

import numpy as np
from scipy.signal import welch

from eeg_harness.context import ExecutionContext
from eeg_harness.agent_cli import main as agent_main
from eeg_harness.demo import (
    build_synthetic_event_record, build_synthetic_no_event_record,
    build_synthetic_tuev_record,
)
from eeg_harness.executor import Executor
from eeg_harness.edf import load_edf
from eeg_harness.pipeline import load_config
from eeg_harness.profiles import EDF_NATIVE, TUEV_BIPOLAR_22
from eeg_harness.research.integrated_method.fake import Point1FakeLLM
from eeg_harness.research.integrated_method.v2 import (
    ConstraintCarryingEEGAgentV2, MultiTaskContractGraphPlanner, MultiTaskRequest,
    compile_multitask, run_multitask,
)
from eeg_harness.tooling import ToolRequest
from eeg_harness.tools import build_default_registry


ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config(ROOT / "config" / "baseline.json")


def context(record=None, profile=EDF_NATIVE, resources=None, task_id="v2-test"):
    return ExecutionContext(
        record or build_synthetic_event_record(), profile,
        Executor(build_default_registry(), CONFIG, resources or {}), task_id,
    )


class MultiTaskV2Test(unittest.TestCase):
    def test_real_llm_cli_rejects_non_synthetic_record_before_loading(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                agent_main(["--agent-mode", "point1-v2", "--edf", "not-read.edf",
                            "--request", "请分析这个记录"])
        self.assertEqual(caught.exception.code, 2)

    def test_no_event_continuous_multiple_goals_share_graph(self):
        ctx = context(build_synthetic_no_event_record())
        request = MultiTaskRequest(
            ("record_quality", "psd"),
            goal_arguments={"psd": {"channels": ["SYNTH-C1"], "start": 0, "end": 2}},
            forbidden_operations=("selection",),
        )
        _, ledger, check, run = run_multitask(ctx, request)
        self.assertTrue(check["valid"])
        self.assertEqual(run.status, "completed")
        self.assertTrue(run.evidence_check["closed"])
        self.assertEqual([item["tool_name"] for item in run.tool_results], ["record_quality", "psd"])
        self.assertEqual(set(run.scientific_state["graph"]["evidence"]), {"record_quality", "psd"})
        self.assertEqual(set(run.required_answer_tools), {"record_quality", "psd"})
        self.assertNotIn("create_epochs", json.dumps(run.to_dict()))
        json.dumps(ledger.to_dict(), allow_nan=False)
        power = next(item["data"] for item in run.tool_results if item["tool_name"] == "psd")
        signal = ctx.record.data[0, :256]
        frequencies, density = welch(signal, fs=128.0, nperseg=128.0)
        low, high = CONFIG["freq_bands"]["alpha"]
        selected = (frequencies >= low) & (frequencies <= high)
        expected = "{:.2e}".format(np.trapz(density[selected], frequencies[selected]))
        self.assertEqual(power["SYNTH-C1"]["alpha"], expected)

    def test_event_multistep_uses_same_frontier_and_evidence(self):
        ctx = context()
        request = MultiTaskRequest(
            ("epoch_quality", "event_bandpower"),
            event_arguments={"labels": ["stimulus"], "tmin": 0, "tmax": 1},
            forbidden_operations=("selection",),
        )
        _, _, check, run = run_multitask(ctx, request)
        self.assertTrue(check["valid"])
        self.assertEqual(run.status, "completed")
        self.assertTrue(run.evidence_check["closed"])
        self.assertEqual([item["tool_name"] for item in run.tool_results], [
            "list_events", "create_epochs", "epoch_quality", "event_bandpower",
        ])
        self.assertEqual(set(run.required_answer_tools), {"epoch_quality", "event_bandpower"})

    def test_mixed_record_and_event_goals_are_one_atomic_plan(self):
        ctx = context()
        request = MultiTaskRequest(
            ("record_quality", "event_bandpower"),
            event_arguments={"labels": ["stimulus"], "tmin": 0, "tmax": 1},
        )
        _, _, _, run = run_multitask(ctx, request)
        self.assertEqual(run.status, "completed")
        self.assertEqual([item["tool_name"] for item in run.tool_results], [
            "record_quality", "list_events", "create_epochs", "event_bandpower",
        ])
        self.assertTrue(run.evidence_check["closed"])

    def test_missing_event_label_rejects_every_goal_before_execution(self):
        ctx = context()
        request = MultiTaskRequest(
            ("record_quality", "event_bandpower"),
            event_arguments={"labels": ["absent"], "tmin": 0, "tmax": 1},
        )
        _, _, check, run = run_multitask(ctx, request)
        self.assertFalse(check["valid"])
        self.assertEqual(run.status, "rejected")
        self.assertFalse(ctx.history)

    def test_event_parameters_cannot_be_silently_ignored_for_record_goal(self):
        ctx = context(build_synthetic_no_event_record())
        request = MultiTaskRequest(
            ("psd",),
            goal_arguments={"psd": {"channels": ["SYNTH-C1"], "start": 0, "end": 2}},
            event_arguments={"labels": ["stimulus"], "tmin": 0, "tmax": 1},
        )
        _, _, check, run = run_multitask(ctx, request)
        self.assertEqual(check["code"], "UNREQUESTED_PARAMETERS")
        self.assertEqual(run.status, "rejected")
        self.assertFalse(ctx.history)

    def test_shared_contract_rejects_registered_input_type_mismatch(self):
        ctx = context(build_synthetic_no_event_record())
        registry = ctx.executor.registry
        spec = registry.get("psd")
        registry._tools["psd"] = replace(spec, consumes_artifact="epochs")
        request = MultiTaskRequest(("psd",), goal_arguments={
            "psd": {"channels": ["SYNTH-C1"], "start": 0, "end": 2},
        })
        _, _, check, run = run_multitask(ctx, request)
        self.assertEqual(check["code"], "GOAL_TOOL_CONTRACT_MISMATCH")
        self.assertEqual(run.status, "rejected")
        self.assertFalse(ctx.history)

    def test_shared_result_gate_rejects_wrong_declared_type(self):
        ctx = context(build_synthetic_no_event_record())
        registry = ctx.executor.registry
        spec = registry.get("record_info")
        registry._tools["record_info"] = replace(spec, handler=lambda *_: ["wrong-type"])
        _, _, _, run = run_multitask(ctx, MultiTaskRequest(("record_info",)))
        self.assertEqual(run.status, "scientifically_blocked")
        self.assertEqual(run.scientific_state["blocked"]["code"], "TOOL_RESULT_TYPE_MISMATCH")
        self.assertFalse(run.evidence_check["closed"])
        self.assertFalse(run.release_results)

    def test_missing_window_or_forbidden_goal_rejects_before_execution(self):
        ctx = context(build_synthetic_no_event_record())
        _, _, check, run = run_multitask(ctx, MultiTaskRequest(
            ("record_quality", "psd"), goal_arguments={"psd": {"channels": ["SYNTH-C1"]}},
        ))
        self.assertFalse(check["valid"])
        self.assertEqual(run.status, "rejected")
        self.assertFalse(ctx.history)
        other = context(task_id="v2-forbidden")
        _, _, check, run = run_multitask(other, MultiTaskRequest(
            ("epoch_quality", "trial_selection"),
            event_arguments={"labels": ["stimulus"], "tmin": 0, "tmax": 1,
                             "selection_authorized": True},
            forbidden_operations=("selection",),
        ))
        self.assertEqual(check["code"], "FORBIDDEN_OPERATION")
        self.assertFalse(other.history)

    def test_model_profile_and_resource_preflight(self):
        request = MultiTaskRequest(("seizure_detection",), goal_arguments={
            "seizure_detection": {"channels": ["FP1-F7"], "start": 0, "end": 1},
        })
        wrong = context(build_synthetic_no_event_record())
        _, _, check, _ = run_multitask(wrong, request)
        self.assertFalse(check["valid"])
        self.assertFalse(wrong.history)
        compatible = context(build_synthetic_tuev_record(), TUEV_BIPOLAR_22)
        _, _, check, run = run_multitask(compatible, request)
        self.assertFalse(check["valid"])
        self.assertEqual(run.status, "rejected")
        self.assertFalse(compatible.history)

    def test_model_file_change_blocks_before_cached_loader_can_run(self):
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "model.pth"
            model.write_bytes(b"synthetic-placeholder-one")
            ctx = context(build_synthetic_tuev_record(), TUEV_BIPOLAR_22,
                          {"seizure_model": str(model)})
            request = MultiTaskRequest(("seizure_detection",), goal_arguments={
                "seizure_detection": {"channels": ["FP1-F7"], "start": 0, "end": 1},
            })
            task, ledger, plan, check = compile_multitask(ctx, request)
            self.assertTrue(check["valid"])
            runner = MultiTaskContractGraphPlanner(ctx, task, ledger)
            model.write_bytes(b"synthetic-placeholder-two")
            run = runner.run(plan, check)
            self.assertEqual(run.status, "scientifically_blocked")
            self.assertEqual(run.scientific_state["blocked"]["code"], "MODEL_RESOURCE_CHANGED")
            self.assertFalse(ctx.history)

    def test_record_change_invalidates_prior_evidence_and_recomputes(self):
        ctx = context(build_synthetic_no_event_record())
        request = MultiTaskRequest(("record_info", "psd"), goal_arguments={
            "psd": {"channels": ["SYNTH-C1"], "start": 0, "end": 2},
        })
        task, ledger, plan, check = compile_multitask(ctx, request)
        runner = MultiTaskContractGraphPlanner(ctx, task, ledger)
        action = runner.next_action()
        self.assertEqual(action.kind, "record_info")
        result = ctx.execute(ToolRequest(action.tool_name, action.arguments, "initial-info"))
        runner.results.append(result.to_dict())
        runner.apply_result(action, result.to_dict())
        before = runner.evidence["record_info"].token_id
        ctx.record.data[0, 0] += 1e-6
        next_action = runner.next_action()
        self.assertEqual(next_action.kind, "record_info")
        self.assertNotIn("record_info", runner.evidence)
        self.assertTrue(any(item["event"] == "evidence_graph_invalidated"
                            for item in runner.transitions))
        self.assertNotEqual(before, runner._record_digest())

    def test_epoch_content_change_uses_same_graph_invalidation_core(self):
        ctx = context()
        request = MultiTaskRequest(
            ("epoch_quality", "event_bandpower"),
            event_arguments={"labels": ["stimulus"], "tmin": 0, "tmax": 1},
        )
        task, ledger, plan, check = compile_multitask(ctx, request)
        self.assertTrue(check["valid"])
        runner = MultiTaskContractGraphPlanner(ctx, task, ledger)
        for expected in ("observe_events", "create_epochs", "epoch_quality"):
            action = runner.next_action()
            self.assertEqual(action.kind, expected)
            result = ctx.execute(ToolRequest(action.tool_name, action.arguments, expected))
            self.assertTrue(result.success)
            rendered = result.to_dict()
            runner.results.append(rendered)
            runner.apply_result(action, rendered)
        source_id = runner.evidence["create_epochs"].output_binding.artifact_id
        ctx.artifacts[source_id].data[0, 0, 0] += 1e-6
        action = runner.next_action()
        self.assertEqual(action.kind, "create_epochs")
        self.assertNotIn("epoch_quality", runner.evidence)
        self.assertTrue(any(item["event"] == "evidence_graph_invalidated"
                            for item in runner.transitions))

    def test_unsupported_goal_rejects_without_crash(self):
        ctx = context()
        _, _, check, run = run_multitask(ctx, MultiTaskRequest(("asd_diagnosis",)))
        self.assertEqual(check["code"], "UNSUPPORTED_GOAL")
        self.assertEqual(run.status, "rejected")
        self.assertFalse(ctx.history)

    def test_contexts_do_not_share_goal_evidence(self):
        first = context(build_synthetic_no_event_record(), task_id="first")
        second = context(build_synthetic_no_event_record(), task_id="second")
        request = MultiTaskRequest(("psd",), goal_arguments={
            "psd": {"channels": ["SYNTH-C1"], "start": 0, "end": 2},
        })
        _, _, _, run_a = run_multitask(first, request)
        _, _, _, run_b = run_multitask(second, request)
        self.assertEqual(run_a.status, run_b.status)
        self.assertNotEqual(run_a.scientific_state["record_binding"], None)
        self.assertNotEqual(first.task_id, second.task_id)
        self.assertEqual(len(first.history), len(second.history))

    def test_fake_natural_language_continuous_and_event(self):
        cases = (
            (build_synthetic_no_event_record(),
             "请计算 SYNTH-C1 通道 0 秒到 2 秒的绝对频带功率。", ["psd"]),
            (build_synthetic_event_record(),
             "请分析 stimulus 事件后 0 秒到 1 秒的试次，测量质量并计算绝对频带功率，不要筛除试次。",
             ["list_events", "create_epochs", "epoch_quality", "event_bandpower"]),
        )
        for index, (record, prompt, tools) in enumerate(cases):
            with self.subTest(index=index):
                result = ConstraintCarryingEEGAgentV2(
                    Point1FakeLLM(), context(record, task_id=f"nl-{index}"),
                ).run(prompt).to_dict()
                self.assertEqual(result["stop_reason"], "completed")
                self.assertEqual([item["tool_name"] for item in result["execution"]["tool_results"]], tools)
                self.assertTrue(result["answer_check"]["valid"])
                json.dumps(result, allow_nan=False)


@unittest.skipUnless(
    os.environ.get("EEG_HARNESS_TEST_EDF") and os.environ.get("EEG_HARNESS_MODEL_PATH"),
    "Set EEG_HARNESS_TEST_EDF and EEG_HARNESS_MODEL_PATH for local resource test",
)
class MultiTaskV2RealResourceTest(unittest.TestCase):
    def test_existing_edf_and_weight_run_one_model_window_locally(self):
        record = load_edf(os.environ["EEG_HARNESS_TEST_EDF"], TUEV_BIPOLAR_22)
        ctx = context(record, TUEV_BIPOLAR_22,
                      {"seizure_model": os.environ["EEG_HARNESS_MODEL_PATH"]},
                      task_id="v2-local-model")
        _, _, check, run = run_multitask(ctx, MultiTaskRequest(
            ("seizure_detection",), goal_arguments={
                "seizure_detection": {"channels": ["FP1-F7"], "start": 0, "end": 1},
            },
        ))
        self.assertTrue(check["valid"])
        self.assertEqual(run.status, "completed")
        self.assertTrue(run.evidence_check["closed"])
        self.assertEqual(len(run.tool_results), 1)
        self.assertEqual(len(run.tool_results[0]["data"]), 1)
        self.assertIn("FP1-F7", run.tool_results[0]["data"][0])
        self.assertIsNotNone(run.scientific_state["model_input_binding"])
        json.dumps(run.to_dict(), allow_nan=False)


if __name__ == "__main__":
    unittest.main()
