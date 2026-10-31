"""Issue #39 hard budget and frozen synthetic protocol checks (no API)."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from eeg_harness.research.task_memory_issue39 import load_stage_protocol
from eeg_harness.research.task_memory_issue39_budget import (
    Issue39BudgetClient, StageBudgetExhausted, ledger_totals,
)
from eeg_harness.research.task_memory_v2 import protocol_records, score_read_semantics
from eeg_harness.research.task_memory_v3 import EpisodeMemorySession


class FakeRaw:
    max_tokens = 20
    last_usage = {"total_tokens": 7}
    last_response_model = "fake-reported"
    last_finish_reason = "stop"


class FakeJournal:
    def __init__(self, *, fail=False):
        self.client = FakeRaw()
        self.fail = fail
        self.request_count = 0
        self.total_usage = {"total_tokens": 0}
        self.model = "fake-requested"

    def complete(self, messages, tools, tool_choice="auto"):
        self.request_count += 1
        if self.fail:
            raise RuntimeError("simulated network failure")
        self.total_usage["total_tokens"] += 7
        return {"content": "ok"}


class Issue39Tests(unittest.TestCase):
    def test_shared_ledger_survives_client_restart_and_phase_cap(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "budget.jsonl"
            first = Issue39BudgetClient(FakeJournal(), path, max_requests=3,
                                        max_tokens=200, phase="smoke",
                                        phase_request_cap=1)
            first.complete([], [])
            second = Issue39BudgetClient(FakeJournal(), path, max_requests=3,
                                         max_tokens=200, phase="smoke",
                                         phase_request_cap=1)
            with self.assertRaises(StageBudgetExhausted):
                second.complete([], [])
            self.assertEqual(ledger_totals(path)["attempts"], 1)
            self.assertEqual(ledger_totals(path)["charged_tokens"], 7)
            third = Issue39BudgetClient(FakeJournal(), path, max_requests=3,
                                        max_tokens=200, phase="initial",
                                        phase_request_cap=2)
            third.complete([], [])
            self.assertEqual(ledger_totals(path)["attempts"], 2)

    def test_failures_are_charged_and_limits_cannot_reset(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "budget.jsonl"
            client = Issue39BudgetClient(FakeJournal(fail=True), path,
                                         max_requests=1, max_tokens=200,
                                         phase="smoke")
            with self.assertRaises(RuntimeError):
                client.complete([], [])
            totals = ledger_totals(path)
            self.assertEqual(totals["attempts"], 1)
            self.assertGreater(totals["charged_tokens"], 20)
            with self.assertRaises(StageBudgetExhausted):
                Issue39BudgetClient(FakeJournal(), path, max_requests=2,
                                    max_tokens=200)

    def test_frozen_confirmation_oracle_runs_real_tools(self):
        spec = load_stage_protocol()
        self.assertEqual(set(spec["confirmation_session_ids"]),
                         {script["id"] for script in spec["confirmation_sessions"]})
        for script in spec["confirmation_sessions"]:
            session = EpisodeMemorySession(script["id"], protocol_records(script))
            completed = {}
            for step in script["steps"]:
                parent = completed.get(step.get("revision_of"))
                result = session.analyze(step["record"], step["capability"],
                                         step["parameters"], step["text"],
                                         revision_of=parent)
                self.assertEqual(result["status"], "completed",
                                 (script["id"], step["key"], result))
                completed[step["key"]] = result["task_id"]
            for query in script["queries"]:
                read = session.read_task(completed[query["target"]], query["text"])
                self.assertEqual(read["status"], "read", query)
                value = read["result"]
                for key in query["field"]:
                    value = value[key]
                self.assertGreaterEqual(float(value), 0, (query, value))
                entries = {step_key: next(entry for entry in session.entries
                                          if entry.task_id == task_id)
                           for step_key, task_id in completed.items()}
                independent = score_read_semantics(
                    session, script, query, entries, completed[query["target"]],
                    observed_read=read)
                self.assertTrue(independent["valid"], independent)
            json.dumps([item.result for item in session.entries], allow_nan=False)


if __name__ == "__main__":
    unittest.main()
