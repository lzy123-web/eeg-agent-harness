import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from eeg_harness.llm import LLMServiceError
from eeg_harness.research.working_memory_issue47 import Issue47Client, records_for
from eeg_harness.research.task_memory_issue39_budget import ledger_totals, StageBudgetExhausted


class NoNetwork:
    client = SimpleNamespace(max_tokens=1200)
    def complete(self, *args):
        raise AssertionError("Must not call external service")


class Issue47BudgetTest(unittest.TestCase):
    def test_development_count_and_tokens_preserve_confirmation_across_restart(self):
        for count, charge in ((16, 1), (1, 100000)):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as d:
                p = Path(d)/"budget.jsonl"
                Issue47Client(NoNetwork(), p, phase="development")
                with p.open("a", encoding="utf8") as f:
                    for i in range(count):
                        f.write(json.dumps({"event": "reserved", "request_id": str(i), "reserved_tokens": charge,
                                            "context": {"phase": "development"}})+"\n")
                client = Issue47Client(NoNetwork(), p, phase="development")
                with self.assertRaises(LLMServiceError) as error:
                    client.complete([{"role": "user", "content": "next"}], [])
                self.assertEqual(error.exception.code, "STAGE_BUDGET_EXHAUSTED")
                self.assertEqual(ledger_totals(p)["attempts"], count)
                self.assertEqual(ledger_totals(p)["charged_tokens"], count*charge)

    def test_global_limit_and_incompatible_old_ledger_cannot_reset(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/"budget.jsonl"
            Issue47Client(NoNetwork(), p, phase="confirmation")
            with p.open("a", encoding="utf8") as f:
                f.write(json.dumps({"event": "reserved", "request_id": "prior", "reserved_tokens": 300000,
                                   "context": {"phase": "confirmation"}})+"\n")
            with self.assertRaises(LLMServiceError):
                Issue47Client(NoNetwork(), p, phase="confirmation").complete([], [])
            p.write_text(json.dumps({"event": "opened", "max_requests": 96, "max_tokens": 240000})+"\n")
            with self.assertRaises(StageBudgetExhausted):
                Issue47Client(NoNetwork(), p, phase="confirmation")

    def test_confirmation_is_synthetic_and_distinct(self):
        original, confirmation = records_for("original"), records_for("confirmation")
        for key, record in confirmation.items():
            self.assertTrue(record.metadata["is_synthetic"])
            self.assertTrue(record.source.startswith("synthetic://"))
            self.assertNotEqual(record.source, original[key].source)
            self.assertEqual(record.events.labels, ("rest", "tone"))


if __name__ == "__main__":
    unittest.main()
