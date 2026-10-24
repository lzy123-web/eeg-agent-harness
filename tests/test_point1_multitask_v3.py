"""Deterministic tests of parameterized goals on the real Registry/Executor."""

import json
import os
import contextlib
import io
from pathlib import Path
import unittest

import numpy as np
from scipy.signal import welch

from eeg_harness.context import ExecutionContext
from eeg_harness.agent_cli import main as agent_main
from eeg_harness.demo import (build_synthetic_event_record,
                              build_synthetic_no_event_record, build_synthetic_tuev_record)
from eeg_harness.executor import Executor
from eeg_harness.pipeline import load_config
from eeg_harness.profiles import EDF_NATIVE, TUEV_BIPOLAR_22
from eeg_harness.research.integrated_method.v3 import (
    GoalInstance, InstanceTaskRequest, capability_catalog, run_instances,
)
from eeg_harness.research.integrated_method.v3_agent import InstanceGoalEEGAgent, _decode_arguments
from eeg_harness.research.integrated_method.v3_application import render_auxiliary_evidence_note
from eeg_harness.research.integrated_method.v3 import compile_instances, InstanceEvidenceGraph
from eeg_harness.tooling import ToolRequest
from eeg_harness.tools import build_default_registry


CONFIG = load_config(Path(__file__).resolve().parents[1] / "config" / "baseline.json")


def context(*, events=False, task_id="v3-test"):
    record = build_synthetic_event_record() if events else build_synthetic_no_event_record()
    return ExecutionContext(record, EDF_NATIVE, Executor(build_default_registry(), CONFIG), task_id)


def goal(key, name, **params):
    return GoalInstance(key, name, params)


class FixtureLLM:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.messages = []

    def complete(self, messages, tools, tool_choice="auto"):
        self.messages.append((messages, tools))
        payload = self.payloads.pop(0)
        return {"tool_calls": [{"function": {
            "name": "submit_eeg_goals", "arguments": json.dumps(payload, ensure_ascii=False),
        }}]}


class InstanceGoalTests(unittest.TestCase):
    def test_real_llm_cli_rejects_non_synthetic_before_edf_read(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                agent_main(["--agent-mode", "point1-v3", "--edf", "not-read.edf",
                            "--request", "请看记录信息"])
        self.assertEqual(caught.exception.code, 2)

    def test_protocol_repair_is_one_syntactic_brace_only(self):
        self.assertEqual(_decode_arguments('{"goals": []}}'), ({"goals": []},
                                                                 "single_extra_final_brace"))
        with self.assertRaises(json.JSONDecodeError):
            _decode_arguments('{"goals": []}}}')

    def test_catalog_grounded_in_registry_without_resource_load(self):
        names = {item["name"] for item in capability_catalog(context())}
        self.assertIn("psd", names)
        self.assertNotIn("seizure_detection", names)

    def test_distinct_task_families_also_run_as_single_goal_requests(self):
        cases = (
            (False, goal("info", "record_info")),
            (False, goal("amplitude", "amplitude", channels=["SYNTH-C1"], start=0, end=1)),
            (True, goal("epochs", "epoch_summary", labels=["stimulus"], tmin=0, tmax=1)),
        )
        for events, instance in cases:
            with self.subTest(capability=instance.capability):
                result = run_instances(context(events=events), InstanceTaskRequest((instance,)))
                self.assertEqual(result["status"], "completed")
                self.assertEqual(result["evidence_bundle"]["goals"][0]["capability"],
                                 instance.capability)

    def test_repeated_psd_distinct_windows_and_independent_oracle(self):
        ctx = context()
        result = run_instances(ctx, InstanceTaskRequest((
            goal("quality", "record_quality"),
            goal("early", "psd", channels=["SYNTH-C1"], start=0, end=2),
            goal("late", "psd", channels=["SYNTH-C1"], start=2, end=4),
        ), ("selection",)))
        self.assertEqual(result["status"], "completed")
        self.assertEqual([item["tool_name"] for item in result["tool_results"]],
                         ["record_quality", "psd", "psd"])
        bundle = result["evidence_bundle"]
        self.assertEqual([item["instance_id"] for item in bundle["goals"]],
                         ["quality", "early", "late"])
        self.assertEqual([item["analysis_scope"] for item in bundle["goals"]],
                         ["whole_record", "continuous_window", "continuous_window"])
        self.assertNotEqual(bundle["goals"][1]["request_id"], bundle["goals"][2]["request_id"])
        for index, start in ((1, 0), (2, 2)):
            x = ctx.record.data[0, int(start * 128):int((start + 2) * 128)]
            frequency, density = welch(x, fs=128.0, nperseg=128.0)
            band = (frequency >= 8) & (frequency <= 13)
            expected = "{:.2e}".format(np.trapz(density[band], frequency[band]))
            self.assertEqual(bundle["goals"][index]["result"]["SYNTH-C1"]["alpha"], expected)
        json.dumps(bundle, allow_nan=False)

    def test_cross_family_shares_exact_event_scope_only(self):
        ctx = context(events=True)
        scope = {"labels": ["stimulus"], "tmin": 0, "tmax": 1}
        result = run_instances(ctx, InstanceTaskRequest((
            goal("continuous", "psd", channels=["SYNTH-C1"], start=0, end=2),
            goal("quality", "epoch_quality", **scope),
            goal("power", "event_bandpower", **scope),
        ), ("selection",)))
        self.assertEqual(result["status"], "completed")
        tools = [item["tool_name"] for item in result["tool_results"]]
        self.assertEqual(tools.count("list_events"), 1)
        self.assertEqual(tools.count("create_epochs"), 1)
        self.assertNotIn("select_quality_epochs", tools)
        bundle = result["evidence_bundle"]
        self.assertEqual(bundle["goals"][1]["input_binding"], bundle["goals"][2]["input_binding"])
        self.assertTrue(bundle["goals"][0]["input_binding"]["artifact_id"].startswith("record:"))
        artifact_id = bundle["goals"][2]["input_binding"]["artifact_id"]
        epochs = ctx.artifacts[artifact_id]
        values = []
        for index, label in enumerate(epochs.event_labels):
            if label != "stimulus":
                continue
            frequencies, density = welch(epochs.data[index, 0], fs=epochs.sfreq,
                                         nperseg=min(epochs.data.shape[-1], round(epochs.sfreq)))
            band = (frequencies >= 8) & (frequencies <= 13)
            values.append(float(np.trapz(density[band], frequencies[band])))
        observed = bundle["goals"][2]["result"]["conditions"]["stimulus"]["channels"]["SYNTH-C1"]["alpha"]
        self.assertAlmostEqual(observed, float(np.mean(values)), places=12)
        json.dumps(result, allow_nan=False)

    def test_distinct_event_scopes_do_not_share_epoch_artifact(self):
        result = run_instances(context(events=True), InstanceTaskRequest((
            goal("a", "epoch_summary", labels=["stimulus"], tmin=0, tmax=1),
            goal("b", "epoch_summary", labels=["control"], tmin=0, tmax=1),
        )))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(sum(item["tool_name"] == "create_epochs" for item in result["tool_results"]), 2)
        first, second = result["evidence_bundle"]["goals"]
        self.assertNotEqual(first["input_binding"]["artifact_id"], second["input_binding"]["artifact_id"])

    def test_identical_instance_parameters_reuse_evidence_not_window_variant(self):
        result = run_instances(context(), InstanceTaskRequest((
            goal("a", "psd", channels=["SYNTH-C1"], start=0, end=2),
            goal("b", "psd", channels=["SYNTH-C1"], start=0, end=2),
            goal("c", "psd", channels=["SYNTH-C1"], start=2, end=4),
        )))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(sum(item["tool_name"] == "psd" for item in result["tool_results"]), 2)
        a, b, c = result["evidence_bundle"]["goals"]
        self.assertEqual(a["request_id"], b["request_id"])
        self.assertNotEqual(a["request_id"], c["request_id"])
        self.assertNotEqual(a["evidence_token"], b["evidence_token"])

    def test_only_affected_event_evidence_invalidates_after_artifact_change(self):
        ctx = context(events=True)
        request = InstanceTaskRequest((
            goal("continuous", "psd", channels=["SYNTH-C1"], start=0, end=2),
            goal("event", "epoch_quality", labels=["stimulus"], tmin=0, tmax=1),
        ))
        compiled, failure = compile_instances(ctx, request)
        self.assertIsNone(failure)
        task, ledger, _, contracts, arguments, scopes, _ = compiled
        graph = InstanceEvidenceGraph(ctx, task, ledger, contracts, arguments, scopes)
        for _ in range(4):
            action = graph.next_action()
            result = ctx.execute(ToolRequest(action.tool_name, action.arguments, action.kind))
            self.assertTrue(result.success)
            graph.results.append(result.to_dict())
            graph.apply_result(action, result.to_dict())
        self.assertIn("continuous", graph.evidence)
        self.assertIn("event", graph.evidence)
        continuous_token = graph.evidence["continuous"].token_id
        source = graph.evidence[graph.dependencies["event"][0]].output_binding
        ctx.artifacts[source.artifact_id].data[0, 0, 0] += 1e-6
        action = graph.next_action()
        self.assertTrue(action.kind.startswith("_epochs_"))
        self.assertIn("continuous", graph.evidence)
        self.assertEqual(graph.evidence["continuous"].token_id, continuous_token)
        self.assertNotIn("event", graph.evidence)

    def test_synthetic_application_consumes_bundle_without_reanalysis(self):
        result = run_instances(context(), InstanceTaskRequest((
            goal("p", "psd", channels=["SYNTH-C1"], start=0, end=2),
        )))
        note = render_auxiliary_evidence_note(result["evidence_bundle"])
        self.assertIn("合成示例", note)
        self.assertIn(result["evidence_bundle"]["goals"][0]["evidence_token"], note)
        self.assertIn("不构成 ASD 诊断", note)

    def test_model_missing_resource_and_wrong_profile_rejected_atomically(self):
        no_weight = ExecutionContext(build_synthetic_tuev_record(), TUEV_BIPOLAR_22,
                                     Executor(build_default_registry(), CONFIG), "no-weight")
        request = InstanceTaskRequest((
            goal("info", "record_info"),
            goal("model", "seizure_detection", channels=["FP1-F7"], start=0, end=1),
        ))
        blocked = run_instances(no_weight, request)
        self.assertEqual(blocked["status"], "rejected")
        self.assertEqual(blocked["tool_results"], [])
        incompatible = run_instances(context(), request)
        self.assertEqual(incompatible["status"], "rejected")
        self.assertEqual(incompatible["tool_results"], [])

    @unittest.skipUnless(os.environ.get("EEG_HARNESS_MODEL_PATH"),
                         "Set EEG_HARNESS_MODEL_PATH for local synthetic model test")
    def test_existing_model_on_synthetic_verified_profile(self):
        ctx = ExecutionContext(
            build_synthetic_tuev_record(), TUEV_BIPOLAR_22,
            Executor(build_default_registry(), CONFIG,
                     {"seizure_model": os.environ["EEG_HARNESS_MODEL_PATH"]}), "model-synth")
        result = run_instances(ctx, InstanceTaskRequest((
            goal("info", "record_info"),
            goal("model", "seizure_detection", channels=["FP1-F7"], start=0, end=1),
        )))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["evidence_bundle"]["goals"][1]["result"]), 1)
        self.assertIn("FP1-F7", result["evidence_bundle"]["goals"][1]["result"][0])

    def test_atomic_preflight_rejects_bad_goal_without_partial_execution(self):
        ctx = context()
        result = run_instances(ctx, InstanceTaskRequest((
            goal("good", "record_info"), goal("bad", "event_bandpower", labels=["stimulus"], tmin=0, tmax=1),
        )))
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["tool_results"], [])
        self.assertEqual(ctx.trace.to_dict()["events"], [])

    def test_missing_parameters_clarify_without_execution(self):
        result = run_instances(context(), InstanceTaskRequest((goal("p", "psd", channels=["SYNTH-C1"]),)))
        self.assertEqual(result["status"], "clarification_required")
        self.assertEqual(result["details"]["p"]["fields"], ["start", "end"])

    def test_quality_scope_and_source_stage_preflight_are_atomic(self):
        quality_partial = run_instances(context(), InstanceTaskRequest((
            goal("good", "record_info"), goal("q", "record_quality", start=1),
        )))
        self.assertEqual(quality_partial["status"], "clarification_required")
        self.assertEqual(quality_partial["tool_results"], [])
        quality_range = run_instances(context(), InstanceTaskRequest((
            goal("good", "record_info"), goal("q", "record_quality", start=0, end=100),
        )))
        self.assertEqual(quality_range["status"], "rejected")
        self.assertEqual(quality_range["tool_results"], [])
        raw_goal = GoalInstance("raw", "record_info", source_stage="raw")
        raw_request = run_instances(context(), InstanceTaskRequest((raw_goal,)))
        self.assertEqual(raw_request["details"]["raw"]["code"], "SOURCE_STAGE_UNAVAILABLE")

    def test_independent_contexts_do_not_share_results(self):
        first = context(task_id="v3-first")
        second = context(task_id="v3-second")
        request = InstanceTaskRequest((goal("p", "psd", channels=["SYNTH-C1"], start=0, end=2),))
        a = run_instances(first, request)
        second.record.data[0, :] *= 2
        b = run_instances(second, request)
        self.assertNotEqual(a["evidence_bundle"]["goals"][0]["result"],
                            b["evidence_bundle"]["goals"][0]["result"])
        self.assertNotEqual(a["evidence_bundle"]["goals"][0]["input_binding"],
                            b["evidence_bundle"]["goals"][0]["input_binding"])

    def test_fake_llm_clarification_resume_and_no_raw_array_in_prompt(self):
        request = "请计算 SYNTH-C1 通道的频带功率。"
        first = {"goals": [{"instance_id": "g1", "capability": "psd",
                            "parameters": {"channels": ["SYNTH-C1"]},
                            "request_quote": "频带功率", "concept_quote": "频带功率",
                            "parameter_quotes": {"channels": "SYNTH-C1"}}],
                 "forbidden_operations": [], "unsupported_requests": []}
        second = {"goals": [{"instance_id": "g1", "capability": "psd",
                             "parameters": {"channels": ["SYNTH-C1"], "start": 0, "end": 2},
                             "request_quote": "频带功率",
                             "concept_quote": "频带功率",
                             "parameter_quotes": {"channels": "SYNTH-C1", "start": "0 秒", "end": "2 秒"}}],
                  "forbidden_operations": [], "unsupported_requests": []}
        fake = FixtureLLM([first, second])
        agent = InstanceGoalEEGAgent(fake, context())
        self.assertEqual(agent.run(request)["status"], "clarification_required")
        result = agent.resume("时间窗是 0 秒到 2 秒。")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["evidence_bundle"]["goals"][0]["instance_id"], "g1")
        self.assertNotIn("raw EEG", json.dumps(fake.messages[0][0], ensure_ascii=False))
        self.assertEqual(len(fake.messages), 2)

    def test_fake_llm_rejects_ungrounded_goal(self):
        fake = FixtureLLM([{"goals": [{"instance_id": "g1", "capability": "amplitude",
                                   "parameters": {"channels": ["SYNTH-C1"], "start": 0, "end": 2},
                                   "request_quote": "频带功率",
                                   "concept_quote": "频带功率",
                                   "parameter_quotes": {"channels": "SYNTH-C1", "start": "0 秒", "end": "2 秒"}}],
                            "forbidden_operations": [], "unsupported_requests": []}])
        result = InstanceGoalEEGAgent(fake, context()).run(
            "计算 SYNTH-C1 的 0 秒到 2 秒频带功率")
        self.assertEqual(result["status"], "clarification_required")
        self.assertEqual(result["tool_results"], [])

    def test_internal_epoch_prerequisite_is_allowed_but_extra_output_goal_is_not(self):
        request = "请测量 stimulus 事件后 0 秒到 1 秒的试次质量。"
        valid = {"instance_id": "q", "capability": "epoch_quality",
                 "parameters": {"labels": ["stimulus"], "tmin": 0, "tmax": 1},
                 "request_quote": "stimulus 事件后 0 秒到 1 秒的试次质量",
                 "concept_quote": "试次质量",
                 "parameter_quotes": {"labels": "stimulus", "tmin": "0 秒", "tmax": "1 秒"}}
        payload = lambda goals: {"goals": goals, "forbidden_operations": [],
                                 "unsupported_requests": []}
        completed = InstanceGoalEEGAgent(FixtureLLM([payload([valid])]),
                                         context(events=True)).run(request)
        self.assertEqual(completed["status"], "completed")
        self.assertEqual([item["tool_name"] for item in completed["tool_results"]],
                         ["list_events", "create_epochs", "epoch_quality"])
        extra = {**valid, "instance_id": "invented", "capability": "epoch_summary",
                 "concept_quote": "试次"}
        rejected = InstanceGoalEEGAgent(FixtureLLM([payload([valid, extra])]),
                                        context(events=True)).run(request)
        self.assertEqual(rejected["status"], "clarification_required")
        self.assertEqual(rejected["tool_results"], [])

    def test_coreferential_event_scope_only_inherits_equal_grounded_scope(self):
        request = ("请对 stimulus 事件后 0 秒到 1 秒的试次测量质量，"
                   "并计算同一事件试次的绝对频带功率。")
        quality = {"instance_id": "q", "capability": "epoch_quality",
                   "parameters": {"labels": ["stimulus"], "tmin": 0, "tmax": 1},
                   "request_quote": "stimulus 事件后 0 秒到 1 秒的试次测量质量",
                   "concept_quote": "测量质量",
                   "parameter_quotes": {"labels": "stimulus", "tmin": "0 秒", "tmax": "1 秒"}}
        power = {"instance_id": "p", "capability": "event_bandpower",
                 "parameters": {"labels": ["stimulus"], "tmin": 0, "tmax": 1},
                 "request_quote": "同一事件试次的绝对频带功率",
                 "concept_quote": "绝对频带功率",
                 "parameter_quotes": {"labels": "同一事件试次", "tmin": "0 秒", "tmax": "1 秒"}}
        payload = lambda items: {"goals": items, "forbidden_operations": [],
                                 "unsupported_requests": []}
        accepted = InstanceGoalEEGAgent(FixtureLLM([payload([quality, power])]),
                                        context(events=True)).run(request)
        self.assertEqual(accepted["status"], "completed")
        self.assertEqual(accepted["evidence_bundle"]["goals"][1]["parameter_sources"],
                         {"labels": "g1"})
        wrong = dict(power)
        wrong["parameters"] = {"labels": ["control"], "tmin": 0, "tmax": 1}
        rejected = InstanceGoalEEGAgent(FixtureLLM([payload([quality, wrong])]),
                                        context(events=True)).run(request)
        self.assertEqual(rejected["status"], "clarification_required")
        self.assertEqual(rejected["tool_results"], [])


if __name__ == "__main__":
    unittest.main()
