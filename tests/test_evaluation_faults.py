import tempfile
from pathlib import Path
import unittest

from eeg_harness.evaluation_faults import FAULTS, FaultInjectingExecutor
from eeg_harness.executor import Executor
from eeg_harness.pipeline import load_config
from eeg_harness.planning_evaluation import make_synthetic_context
from eeg_harness.tooling import ToolRequest
from eeg_harness.tools import build_default_registry


class EvaluationFaultTest(unittest.TestCase):
    def test_all_declared_faults_have_fixed_trigger(self):
        self.assertEqual(set(FAULTS), {
            "artifact_expired", "events_removed", "model_resource_removed",
            "profile_mismatch", "transient_tool_failure",
        })
        self.assertTrue(all(item.before_tool for item in FAULTS.values()))

    def test_transient_failure_is_applied_once_then_recovers(self):
        config = load_config("config/baseline.json")
        context = make_synthetic_context("native_events", "fault", config)
        context.executor = FaultInjectingExecutor(
            context.executor, "transient_tool_failure"
        )
        request = ToolRequest(
            "amplitude", {"channels": ["C1"], "start": 0, "end": 1}
        )
        first = context.execute(request)
        second = context.execute(ToolRequest("amplitude", request.arguments))
        self.assertEqual(first.error_code, "INJECTED_TRANSIENT_FAILURE")
        self.assertTrue(second.success)

    def test_model_resource_change_is_observable_after_injection(self):
        config = load_config("config/baseline.json")
        context = make_synthetic_context("tuev", "resource-fault", config)
        with tempfile.TemporaryDirectory() as directory:
            resource = Path(directory) / "model.pth"
            resource.write_bytes(b"evaluation-placeholder")
            base = Executor(
                build_default_registry(), config, {"seizure_model": str(resource)}
            )
            context.executor = FaultInjectingExecutor(base, "model_resource_removed")
            result = context.execute(ToolRequest("seizure_detection", {
                "channels": [context.record.channel_names[0]], "start": 0, "end": 1,
            }))
            self.assertFalse(result.success)
            self.assertEqual(result.error_code, "MODEL_RESOURCE_MISSING")
            self.assertEqual(context.executor.resources["seizure_model"], "")

    def test_profile_mismatch_is_injected_before_model_load(self):
        config = load_config("config/baseline.json")
        context = make_synthetic_context("tuev", "profile-fault", config)
        with tempfile.TemporaryDirectory() as directory:
            resource = Path(directory) / "model.pth"
            resource.write_bytes(b"evaluation-placeholder")
            base = Executor(
                build_default_registry(), config, {"seizure_model": str(resource)}
            )
            context.executor = FaultInjectingExecutor(base, "profile_mismatch")
            result = context.execute(ToolRequest("seizure_detection", {
                "channels": [context.record.channel_names[0]], "start": 0, "end": 1,
            }))
            self.assertFalse(result.success)
            self.assertEqual(result.error_code, "INCOMPATIBLE_PROFILE")
            self.assertTrue(context.executor.applied)


if __name__ == "__main__":
    unittest.main()
