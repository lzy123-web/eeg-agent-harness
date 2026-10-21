import json
from pathlib import Path
import tempfile
import unittest

from eeg_harness.plan_cli import main


class PlanCLITest(unittest.TestCase):
    def test_window_and_event_demos_include_plan_results_and_trace(self):
        for demo in ("window", "event"):
            with self.subTest(demo=demo), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "result.json"
                main(["--demo", demo, "--output", str(output)])
                payload = json.loads(output.read_text(encoding="utf-8"))
                self.assertEqual(payload["result"]["status"], "completed")
                self.assertTrue(payload["result"]["plan"]["steps"])
                self.assertTrue(payload["result"]["tool_results"])
                self.assertTrue(payload["result"]["execution_trace"]["events"])

    def test_benchmark_cli_is_json_serializable(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "benchmark.json"
            main(["--benchmark", "--output", str(output)])
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["case_count"], 16)


if __name__ == "__main__":
    unittest.main()
