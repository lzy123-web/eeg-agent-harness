"""Pre-frozen D1-D9 development checks on the real EEG tool chain."""

import json
import os
from pathlib import Path
import unittest

import numpy as np
from scipy.signal import welch

from eeg_harness.context import ExecutionContext
from eeg_harness.demo import (build_synthetic_event_record, build_synthetic_no_event_record,
                              build_synthetic_tuev_record)
from eeg_harness.executor import Executor
from eeg_harness.pipeline import load_config
from eeg_harness.profiles import EDF_NATIVE, TUEV_BIPOLAR_22
from eeg_harness.research.adaptive_orchestration import ScientificTask, run_adaptive
from eeg_harness.research.adaptive_orchestration_baselines import run_strong_expert
from eeg_harness.research.integrated_method.v3 import GoalInstance
from eeg_harness.tools import build_default_registry


CONFIG = load_config(Path(__file__).resolve().parents[1] / "config" / "baseline.json")


def context(*, events=True):
    record = build_synthetic_event_record() if events else build_synthetic_no_event_record()
    return ExecutionContext(record, EDF_NATIVE, Executor(build_default_registry(), CONFIG))


def psd_goal(channel="SYNTH-C1"):
    return GoalInstance("p", "psd", {"channels": [channel], "start": 0, "end": 2})


def event_goal(label="stimulus"):
    return GoalInstance("e", "event_bandpower", {"labels": [label], "tmin": 0, "tmax": 1})


def names(result):
    return [item["tool_name"] for item in result["tool_results"]]


class AdaptiveDevelopmentTests(unittest.TestCase):
    def test_d1_continuous_does_not_probe_events(self):
        result = run_adaptive(context(events=False), ScientificTask((psd_goal(),)))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(names(result), ["psd"])
        json.dumps(result, allow_nan=False)

    def test_d2_event_feedback_completes_and_matches_independent_oracle(self):
        ctx = context()
        result = run_adaptive(ctx, ScientificTask((event_goal(),), {"e": 2}))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(names(result), ["list_events", "create_epochs", "event_bandpower"])
        self.assertEqual(result["decisions"][1]["counts"], {"stimulus": 3})
        self.assertEqual(result["decisions"][3]["counts"], {"stimulus": 2})
        data = ctx.record.data[0]
        powers = []
        for onset in (1.0, 3.0):  # third annotated onset 7.8 s is out of bounds
            epoch = data[int(onset * 128):int((onset + 1) * 128)]
            freq, density = welch(epoch, fs=128, nperseg=128)
            mask = (freq >= 8) & (freq <= 13)
            powers.append(float(np.trapz(density[mask], freq[mask])))
        actual = result["evidence_bundle"]["goals"][0]["result"]["conditions"]["stimulus"]["channels"]["SYNTH-C1"]["alpha"]
        self.assertAlmostEqual(actual, float(np.mean(powers)), places=12)
        json.dumps(result, allow_nan=False)

    def test_d3_raw_event_count_stops_before_epoch(self):
        result = run_adaptive(context(), ScientificTask((event_goal("control"),), {"e": 2}))
        self.assertEqual(result["code"], "INSUFFICIENT_EVENT_COUNT")
        self.assertEqual(names(result), ["list_events"])
        self.assertEqual(result["evidence_bundle"]["publication"], "none")

    def test_d4_boundary_loss_stops_after_epoch(self):
        result = run_adaptive(context(), ScientificTask((event_goal(),), {"e": 3}))
        self.assertEqual(result["code"], "INSUFFICIENT_VALID_EPOCHS")
        self.assertEqual(names(result), ["list_events", "create_epochs"])

    def test_d5_atomic_mixed_task_avoids_unpublishable_psd(self):
        result = run_adaptive(context(), ScientificTask((psd_goal(), event_goal("control")), {"e": 2}))
        self.assertEqual(result["code"], "INSUFFICIENT_EVENT_COUNT")
        self.assertEqual(names(result), ["list_events"])
        self.assertEqual(result["evidence_bundle"]["goals"], [])

    def test_d6_mixed_task_completes_and_psd_oracle(self):
        ctx = context()
        result = run_adaptive(ctx, ScientificTask((psd_goal(), event_goal()), {"e": 2}))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(names(result), ["list_events", "create_epochs", "event_bandpower", "psd"])
        freq, density = welch(ctx.record.data[0, :256], fs=128, nperseg=128)
        mask = (freq >= 8) & (freq <= 13)
        expected = "{:.2e}".format(np.trapz(density[mask], freq[mask]))
        self.assertEqual(result["evidence_bundle"]["goals"][0]["result"]["SYNTH-C1"]["alpha"], expected)

    def test_d7_forbidden_observation_is_not_called(self):
        task = ScientificTask((event_goal(),), {"e": 2}, ("list_events",))
        result = run_adaptive(context(), task)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(names(result), ["create_epochs", "event_bandpower"])

    def test_d8_missing_label_clarifies_without_tools(self):
        goal = GoalInstance("e", "event_bandpower", {"tmin": 0, "tmax": 1})
        result = run_adaptive(context(), ScientificTask((goal,)))
        self.assertEqual(result["status"], "clarification_required")
        self.assertEqual(names(result), [])

    def test_invalid_baseline_is_rejected_before_group_serialization(self):
        goal = GoalInstance("e", "event_bandpower", {
            "labels": ["stimulus"], "tmin": 0, "tmax": 1, "baseline": object(),
        })
        result = run_adaptive(context(), ScientificTask((goal,)))
        self.assertEqual(result["code"], "INVALID_EVENT_BASELINE")
        self.assertEqual(names(result), [])

    def test_epoch_requirement_cannot_silently_attach_to_continuous_goal(self):
        result = run_adaptive(context(), ScientificTask((psd_goal(),), {"p": 2}))
        self.assertEqual(result["code"], "INVALID_REQUIREMENT")
        self.assertEqual(names(result), [])

    def test_d9_model_rejected_by_profile_without_tools(self):
        goal = GoalInstance("m", "seizure_detection", {"channels": ["SYNTH-C1"], "start": 0, "end": 1})
        result = run_adaptive(context(), ScientificTask((goal,)))
        self.assertEqual(result["code"], "INCOMPATIBLE_PROFILE")
        self.assertEqual(names(result), [])

    def test_posthoc_d10_all_event_scopes_are_gated_before_consumers(self):
        task = ScientificTask((
            GoalInstance("e1", "event_bandpower", {"labels": ["stimulus"], "tmin": 0, "tmax": 1}),
            GoalInstance("e2", "event_bandpower", {"labels": ["control"], "tmin": 0, "tmax": 1}),
        ), {"e1": 2, "e2": 2})
        for policy in (run_adaptive, run_strong_expert):
            with self.subTest(policy=policy.__name__):
                result = policy(context(), task)
                self.assertEqual(result["code"], "INSUFFICIENT_EVENT_COUNT")
                self.assertEqual(names(result), ["list_events"])
                self.assertEqual(result["evidence_bundle"]["publication"], "none")

    def test_optional_existing_model_on_legal_synthetic_profile(self):
        weight = os.environ.get("EEG_HARNESS_SEIZURE_MODEL")
        if not weight or not Path(weight).is_file():
            self.skipTest("Existing local model resource not configured")
        ctx = ExecutionContext(build_synthetic_tuev_record(), TUEV_BIPOLAR_22,
                               Executor(build_default_registry(), CONFIG,
                                        resources={"seizure_model": weight}))
        channel = ctx.record.channel_names[0]
        goal = GoalInstance("m", "seizure_detection", {
            "channels": [channel], "start": 0, "end": 1,
        })
        result = run_adaptive(ctx, ScientificTask((goal,)))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(names(result), ["seizure_detection"])
        output = result["evidence_bundle"]["goals"][0]["result"]
        self.assertEqual(len(output), 1)
        self.assertEqual(set(output[0][channel]), {"Non-seiz", "seiz"})
        json.dumps(result, allow_nan=False)

    def test_extra_readonly_continuous_goal_needs_no_policy_branch(self):
        amplitude = GoalInstance("a", "amplitude", {
            "channels": ["SYNTH-C1"], "start": 0, "end": 2,
        })
        task = ScientificTask((amplitude, event_goal()), {"e": 2})
        for policy in (run_adaptive, run_strong_expert):
            with self.subTest(policy=policy.__name__):
                ctx = context()
                result = policy(ctx, task)
                self.assertEqual(result["status"], "completed")
                self.assertEqual(names(result), ["list_events", "create_epochs",
                                                 "event_bandpower", "amplitude"])
                observed = result["evidence_bundle"]["goals"][0]["result"]["SYNTH-C1"]
                expected = "{:.2e}".format(np.mean(np.abs(ctx.record.data[0, :256])))
                self.assertEqual(observed["mean_abs"], expected)


if __name__ == "__main__":
    unittest.main()
