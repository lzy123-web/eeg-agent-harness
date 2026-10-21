import json
import tempfile
from pathlib import Path
import unittest

import mne
import numpy as np

from eeg_harness.context import ExecutionContext
from eeg_harness.events import events_from_mne_raw
from eeg_harness.executor import Executor
from eeg_harness.pipeline import load_config
from eeg_harness.planning import ConstrainedPlanRunner, StateAwareConstrainedPlanner, TaskSpec
from eeg_harness.profiles import EDF_NATIVE, TUEV_BIPOLAR_22
from eeg_harness.record import EEGRecord
from eeg_harness.tooling import ToolRequest
from eeg_harness.tools import build_default_registry


CONFIG = load_config("config/baseline.json")


def make_context(with_events=True, task_id="planner", profile=EDF_NATIVE, resources=None):
    sfreq = profile.target_sfreq or 128.0
    channels = profile.required_channels or ("C1", "C2")
    samples = int(sfreq * 4)
    times = np.arange(samples) / sfreq
    data = np.vstack([
        np.sin(2 * np.pi * (index + 5) * times) for index in range(len(channels))
    ]).astype(np.float32)
    raw = mne.io.RawArray(data, mne.create_info(channels, sfreq, "eeg"), verbose=False)
    if with_events:
        raw.set_annotations(mne.Annotations([1.0, 2.5], [0, 0], ["A", "B"]))
    record = EEGRecord(
        data, sfreq, channels, profile.reference, profile.montage,
        f"synthetic://{task_id}", metadata={"profile_id": profile.profile_id},
        events=events_from_mne_raw(raw, f"synthetic://{task_id}"),
    )
    return ExecutionContext(
        record, profile, Executor(build_default_registry(), CONFIG, resources), task_id
    )


class ConstrainedPlannerTest(unittest.TestCase):
    def test_valid_window_task_plans_and_executes_one_tool(self):
        context = make_context()
        task = TaskSpec("tool", {
            "tool_name": "psd",
            "parameters": {"channels": ["C1"], "start": 0, "end": 1},
        })
        result = ConstrainedPlanRunner(context).run(task)
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(result.tool_results), 1)
        json.dumps(result.to_dict(), allow_nan=False)

    def test_event_goal_builds_artifact_dependency_chain(self):
        context = make_context()
        task = TaskSpec("event_bandpower", {
            "labels": ["A"], "tmin": -0.25, "tmax": 0.75, "baseline": [-0.25, 0],
        })
        result = ConstrainedPlanRunner(context).run(task)
        self.assertEqual(result.status, "completed")
        self.assertEqual([item["tool_name"] for item in result.tool_results], [
            "list_events", "create_epochs", "event_bandpower",
        ])

    def test_missing_label_invalid_channel_and_profile_are_preflight_rejections(self):
        missing = ConstrainedPlanRunner(make_context()).run(TaskSpec(
            "event_bandpower", {"labels": ["missing"], "tmin": 0, "tmax": 1}
        ))
        self.assertEqual(missing.status, "rejected")
        self.assertEqual(missing.plan["reason"]["code"], "UNSATISFIABLE_CONSTRAINTS")
        self.assertEqual(missing.tool_results, ())

        invalid_channel = ConstrainedPlanRunner(make_context()).run(TaskSpec(
            "tool", {"tool_name": "amplitude", "parameters": {
                "channels": ["missing"], "start": 0, "end": 1,
            }}
        ))
        self.assertEqual(invalid_channel.status, "rejected")
        native_model = ConstrainedPlanRunner(make_context()).run(TaskSpec(
            "tool", {"tool_name": "seizure_detection", "parameters": {
                "channels": ["C1"], "start": 0, "end": 1,
            }}
        ))
        self.assertEqual(native_model.status, "rejected")

    def test_missing_model_resource_is_rejected_before_tool_call(self):
        context = make_context(profile=TUEV_BIPOLAR_22)
        task = TaskSpec("tool", {"tool_name": "seizure_detection", "parameters": {
            "channels": [TUEV_BIPOLAR_22.required_channels[0]], "start": 0, "end": 1,
        }})
        result = ConstrainedPlanRunner(context).run(task)
        self.assertEqual(result.status, "rejected")
        self.assertIn("resource", result.plan["reason"]["message"].lower())

    def test_cross_context_artifact_is_rejected(self):
        owner = make_context(task_id="owner")
        created = owner.execute(ToolRequest(
            "create_epochs", {"labels": ["A"], "tmin": -0.25, "tmax": 0.75}
        ))
        other = make_context(task_id="other")
        result = ConstrainedPlanRunner(other).run(TaskSpec(
            "tool", {"tool_name": "event_bandpower", "parameters": {
                "artifact_id": created.data["artifact_id"],
            }}
        ))
        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.tool_results, ())

    def test_dynamic_replan_recovers_when_existing_artifact_disappears(self):
        context = make_context()
        created = context.execute(ToolRequest(
            "create_epochs", {"labels": ["A"], "tmin": -0.25, "tmax": 0.75}
        ))
        task = TaskSpec("event_bandpower", {
            "artifact_id": created.data["artifact_id"],
            "labels": ["A"], "tmin": -0.25, "tmax": 0.75,
        })
        runner = ConstrainedPlanRunner(context, max_replans=1)
        plan = runner.planner.plan(task)
        context.artifacts.clear()
        result = runner.execute_plan(task, plan)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.replans, 1)
        self.assertTrue(any(item["event"] == "replanned" for item in result.planning_trace))

    def test_unsupported_goal_stops_safely(self):
        result = ConstrainedPlanRunner(make_context()).run(TaskSpec("clinical_diagnosis"))
        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.plan["reason"]["code"], "UNSUPPORTED_GOAL")

    def test_heterogeneous_sequence_preserves_internal_artifact_references(self):
        task = TaskSpec(
            "sequence",
            subtasks=(
                TaskSpec("tool", {"tool_name": "amplitude", "parameters": {
                    "channels": ["C1"], "start": 0, "end": 1,
                }}),
                TaskSpec("event_bandpower", {
                    "labels": ["B"], "tmin": -0.5, "tmax": 0.5,
                }),
            ),
        )
        result = ConstrainedPlanRunner(make_context()).run(task)
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(result.tool_results), 4)


if __name__ == "__main__":
    unittest.main()
