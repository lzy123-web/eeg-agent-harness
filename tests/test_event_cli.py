import json
from pathlib import Path
import tempfile
import unittest

from eeg_harness.event_cli import main


class EventCLITest(unittest.TestCase):
    def test_synthetic_deterministic_demo(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "event.json"
            self.assertEqual(main(["--demo-synthetic", "--output", str(output)]), 0)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["source_kind"], "synthetic_mne_rawarray")
            self.assertEqual(payload["result"]["trace"]["termination_reason"], "completed")
            self.assertEqual(len(payload["result"]["results"]), 4)

    def test_synthetic_fake_agent_demo(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "agent.json"
            self.assertEqual(
                main(["--demo-synthetic", "--fake-agent", "--output", str(output)]), 0
            )
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["result"]["stop_reason"], "completed")
            self.assertEqual(payload["result"]["tool_calls"], 4)


if __name__ == "__main__":
    unittest.main()
