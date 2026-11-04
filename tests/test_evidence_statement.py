import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from eeg_harness.applications.evidence_statement import make_statement, verify_statement
from eeg_harness.research.working_memory_deliveries_validation import run_example
from eeg_harness.working_memory_deliveries import MultiResultWorkingMemoryStore
from eeg_harness.research.task_memory import synthetic_records
from eeg_harness.working_memory_cli import new_stage_client

W = {"channels": ["SYNTH-C1"], "start": 0, "end": 2}


class StatementTest(unittest.TestCase):
    def setUp(self):
        self.store = MultiResultWorkingMemoryStore("claim", synthetic_records())
        self.store.execute_numeric("psd", W)
        self.claim = make_statement(self.store, "claim-t1", ["SYNTH-C1", "alpha"])

    def test_real_result_template_checked_not_arbitrary_natural_language(self):
        self.assertTrue(verify_statement(self.store, self.claim)["valid"])
        for key, changed in [("value", "999"), ("unit_or_kind", "mV"), ("record", "B"),
                             ("source", "synthetic://wrong"), ("revision_of", "invented"),
                             ("parameters", dict(W, end=3)), ("text", "诊断为 ASD")]:
            with self.subTest(key=key):
                bad = copy.deepcopy(self.claim)
                bad[key] = changed
                self.assertFalse(verify_statement(self.store, bad)["valid"])

    def test_historical_read_vs_current_version(self):
        self.store.begin_subgoal("修订", "A", deliveries=[{"key": "p", "tool": "psd", "scope": dict(W, end=3), "revision_of": "claim-t1"}])
        self.store.execute_numeric("psd", dict(W, end=3))
        self.store.close_subgoal("completed")
        self.assertTrue(verify_statement(self.store, self.claim)["valid"])
        current = make_statement(self.store, "claim-t1", ["SYNTH-C1", "alpha"], use="current")
        self.assertFalse(verify_statement(self.store, current)["valid"])

    def test_partial_goal_cannot_be_called_completed(self):
        self.store.begin_subgoal("尚缺幅值", "A", deliveries=[{"key": n, "tool": n, "scope": W} for n in ("psd", "amplitude")])
        self.store.execute_numeric("psd", W)
        statement = make_statement(self.store, "claim-t2", ["SYNTH-C1", "alpha"])
        self.assertEqual(statement["subgoal_status"], "active")
        self.assertEqual(len(statement["limitations"]), 2)
        statement["subgoal_status"] = "completed"
        self.assertFalse(verify_statement(self.store, statement)["valid"])

    def test_disabled_new_budget_never_reads_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "disabled.json"
            config.write_text(json.dumps({"enabled": False, "stage": "future-confirmation", "max_requests": 0, "max_tokens": 0}))
            with patch("eeg_harness.working_memory_cli.OpenAICompatibleClient.from_env") as raw:
                with self.assertRaises(ValueError):
                    new_stage_client(config)
                raw.assert_not_called()

    def test_complete_controlled_example_real_tools_no_api(self):
        evidence = run_example()
        self.assertEqual(evidence["stop_reasons"], ["completed", "completed"])
        self.assertEqual(len(evidence["independent_oracle_checks"]), 5)
        self.assertTrue(evidence["statement_check"]["valid"])
        self.assertEqual(evidence["external_completions"], 0)
        self.assertEqual(len(evidence["actual_decision_visibility"]), 21)


if __name__ == "__main__":
    unittest.main()
