import json
from pathlib import Path
import tempfile
import unittest

from eeg_harness.agent_cli import main as agent_main
from eeg_harness.context import ExecutionContext
from eeg_harness.demo import build_synthetic_event_record
from eeg_harness.executor import Executor
from eeg_harness.pipeline import load_config
from eeg_harness.profiles import EDF_NATIVE
from eeg_harness.research.integrated_method.agent import ConstraintCarryingEEGAgent
from eeg_harness.research.integrated_method.fake import Point1FakeLLM
from eeg_harness.tools import build_default_registry


CONFIG = load_config("config/baseline.json")


def make_context(task_id="point1-test"):
    return ExecutionContext(
        build_synthetic_event_record(), EDF_NATIVE,
        Executor(build_default_registry(), CONFIG, {}), task_id,
    )


class Point1IntegratedAgentTest(unittest.TestCase):
    def test_explicit_psd_runs_planner_executor_and_closes_evidence(self):
        context = make_context()
        result = ConstraintCarryingEEGAgent(Point1FakeLLM(), context).run(
            "计算 SYNTH-C1 从 1 秒到 3 秒的绝对频带功率"
        )
        self.assertEqual("completed", result.stop_reason)
        self.assertTrue(result.plan_check["valid"])
        self.assertTrue(result.evidence_check["closed"])
        self.assertEqual(["psd"], result.evidence_check["successful_tools"])
        event = result.execution["execution_trace"]["events"][0]
        self.assertEqual({"channels": ["SYNTH-C1"], "start": 1.0, "end": 3.0}, event["arguments"])
        json.dumps(result.to_dict(), ensure_ascii=False, allow_nan=False)

    def test_cli_point1_is_opt_in_and_serializable(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "point1.json"
            code = agent_main([
                "--demo-synthetic", "--fake", "--agent-mode", "point1",
                "--request", "计算 SYNTH-C2 从 0 秒到 2 秒的绝对频带功率",
                "--output", str(output),
            ])
            self.assertEqual(0, code)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("constraint_carrying_eeg_plan_v0", payload["method"])
            self.assertEqual("completed", payload["stop_reason"])


if __name__ == "__main__":
    unittest.main()
