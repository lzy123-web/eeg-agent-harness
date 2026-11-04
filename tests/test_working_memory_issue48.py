"""Offline budget, attribution and frozen natural confirmation driver checks."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from eeg_harness.llm import LLMServiceError
from eeg_harness.research import working_memory_issue48 as stage
from eeg_harness.research.task_memory_issue39_budget import _rows, ledger_totals, StageBudgetExhausted


class FakeJournal:
    def __init__(self, failure=False):
        self.client = SimpleNamespace(max_tokens=1600, max_retries=0, timeout=45,
            last_usage={"prompt_tokens": 70, "completion_tokens": 30, "total_tokens": 100},
            last_response_model="offline", last_finish_reason="stop")
        self.model, self.request_count, self.total_usage = "offline", 0, {}
        self.failure = failure

    def complete(self, *args):
        self.request_count += 1
        if self.failure:
            raise RuntimeError("Synthetic network failure")
        return {"content": "offline"}


def seed(path, count, charged, phase, case):
    with path.open("a", encoding="utf8") as f:
        for i in range(count):
            f.write(json.dumps({"event": "reserved", "request_id": f"{phase}-{case}-{i}",
                               "reserved_tokens": charged, "context": {"phase": phase, "case": case}})+"\n")


class Issue48ProtocolTest(unittest.TestCase):
    def test_development_caps_survive_restart_and_preserve_confirmation(self):
        for count, charged in ((24, 1), (1, 150000)):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as d:
                p = Path(d)/"budget.jsonl"
                stage.Issue48Client(FakeJournal(), p, phase="development", case="development")
                seed(p, count, charged, "development", "development")
                raw = FakeJournal()
                c = stage.Issue48Client(raw, p, phase="development", case="development")
                with self.assertRaises(LLMServiceError):
                    c.complete([], [])
                self.assertEqual(raw.request_count, 0)
                self.assertEqual(ledger_totals(p)["attempts"], count)
                stage.Issue48Client(raw, p, phase="confirmation", case="C").complete([], [])
                self.assertEqual(raw.request_count, 1)

    def test_case_cap_is_cumulative_without_taking_other_case_reserve(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/"budget.jsonl"
            stage.Issue48Client(FakeJournal(), p, phase="confirmation", case="D")
            seed(p, 6, 100, "confirmation", "D")
            raw = FakeJournal()
            with self.assertRaises(LLMServiceError):
                stage.Issue48Client(raw, p, phase="confirmation", case="D").complete([], [])
            self.assertEqual(raw.request_count, 0)
            stage.Issue48Client(raw, p, phase="confirmation", case="B").complete([], [])
            self.assertEqual(raw.request_count, 1)
            self.assertEqual(_rows(p)[-3]["reason"], "confirmation_case_reserve")

    def test_failure_retains_conservative_charge_and_full_request_log(self):
        with tempfile.TemporaryDirectory() as d:
            p, journal = Path(d)/"budget.jsonl", Path(d)/"requests.jsonl"
            raw = FakeJournal(failure=True)
            client = stage.Issue48Client(raw, p, phase="development", case="development", request_journal=journal)
            with self.assertRaises(RuntimeError):
                client.complete([{"role": "user", "content": "合成请求"}], [])
            rows = _rows(p)
            self.assertEqual(rows[-1]["event"], "failed")
            self.assertEqual(ledger_totals(p)["charged_tokens"], rows[-2]["reserved_tokens"])
            logged = _rows(journal)[0]
            self.assertEqual(logged["messages"][0]["content"], "合成请求")
            self.assertNotIn("api_key", json.dumps(logged))
            self.assertEqual(logged["components"]["unit"], "serialized_utf8_bytes_not_api_tokens")

    def test_old_or_modified_limits_cannot_reset_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/"budget.jsonl"
            p.write_text(json.dumps({"event": "opened", "max_requests": 80, "max_tokens": 500000})+"\n")
            with self.assertRaises(StageBudgetExhausted):
                stage.Issue48Client(FakeJournal(), p, phase="development", case="development")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/"budget.jsonl"
            stage.Issue48Client(FakeJournal(), p, phase="confirmation", case="A")
            spec = json.loads(stage.SPEC.read_text(encoding="utf8"))
            spec["confirmation"]["A"]["token_cap"] += 1
            with self.assertRaises(StageBudgetExhausted):
                stage.Issue48Client(FakeJournal(), p, phase="confirmation", case="A", protocol=spec)

    def test_global_cap_prevents_network(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/"budget.jsonl"
            stage.Issue48Client(FakeJournal(), p, phase="confirmation", case="D")
            seed(p, 1, 500000, "development", "development")
            raw = FakeJournal()
            with self.assertRaises(LLMServiceError):
                stage.Issue48Client(raw, p, phase="confirmation", case="D").complete([], [])
            self.assertEqual(raw.request_count, 0)

    def test_components_and_data_are_structurally_different_from_development(self):
        payload = {"current_request": "查alpha", "user_requests": ["查alpha"],
                   "records": {"A": "synthetic"}, "active_subgoal": {"status": "active"},
                   "archived_summaries": [{"task_id": "old"}], "exact_evidence": [{"value": 1}],
                   "restored_trajectories": [{"action": "psd"}]}
        out = stage.input_components([{"role": "system", "content": "system"},
            {"role": "user", "content": json.dumps(payload)},
            {"role": "assistant", "content": "observation"}], [{"tool": "amplitude"}])
        self.assertTrue(all(out["parts"][k] > 0 for k in out["parts"]))
        self.assertGreaterEqual(out["serialization_envelope_bytes"], 0)
        old, new = stage.records_for("original"), stage.records_for("confirmation")
        for alias, record in new.items():
            self.assertTrue(record.metadata["is_synthetic"])
            self.assertTrue(record.source.startswith("synthetic://"))
            self.assertNotEqual([e.onset_seconds for e in record.events.events], [e.onset_seconds for e in old[alias].events.events])
            self.assertFalse(np.allclose(record.data, old[alias].data))
        spec = json.loads(stage.SPEC.read_text(encoding="utf8"))
        self.assertEqual(spec["confirmation_order"], ["D", "C", "A", "B"])
        self.assertEqual(sum(x["request_cap"] for x in spec["confirmation"].values()), 56)
        self.assertEqual(sum(x["token_cap"] for x in spec["confirmation"].values()), 350000)

    def test_clarification_reply_only_after_actual_clarification(self):
        for first_stop, expected in (("completed", 1), ("clarification_required", 2)):
            calls = []
            class Agent:
                def __init__(self, client, records, **kwargs):
                    self.kwargs = kwargs
                def run(self, text):
                    calls.append(text)
                    stop = first_stop if len(calls) == 1 else "completed"
                    state = {"stop_reason": stop, "tool_results": [], "working_memory": {"subgoals": [{
                        "record": "B", "status": "awaiting_input", "deliveries": [{"key": "p", "tool": "event_bandpower", "scope": {"labels": ["target"]}}],
                        "admission_issues": [{"delivery": "p", "field": key, "code": "MISSING_SCIENTIFIC_PARAMETER"} for key in ("tmin", "tmax")]}]}}
                    return SimpleNamespace(stop_reason=stop, rounds=1, tool_calls=0,
                        final_answer="offline", to_dict=lambda: state)
                continue_run = run
            with self.subTest(first_stop=first_stop), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                raw = SimpleNamespace(timeout=45)
                with patch.object(stage, "ROOT", root), patch.object(stage, "LEDGER", root/"budget.jsonl"), \
                     patch.object(stage.OpenAICompatibleClient, "from_env", return_value=raw), \
                     patch.object(stage, "WorkingMemoryEEGAgent", Agent):
                    stage.real_case("C", "offline-gate")
                self.assertEqual(len(calls), expected)
                self.assertTrue(all("evaluation_only" not in text for text in calls))
                self.assertTrue((root/"offline-gate"/"manifest.json").exists())

    def test_wrong_clarification_or_premature_analysis_does_not_unlock_reply(self):
        required = {"record": "B", "tool": "event_bandpower", "scope": {"labels": ["target"]}, "missing_fields": ["tmin", "tmax"]}
        pending = {"stop_reason": "clarification_required", "tool_results": [], "working_memory": {"subgoals": [{
            "record": "B", "status": "awaiting_input", "deliveries": [{"key": "p", "tool": "event_bandpower", "scope": {"labels": ["target"]}}],
            "admission_issues": [{"delivery": "p", "field": field, "code": "MISSING_SCIENTIFIC_PARAMETER"} for field in ("tmin", "tmax")]}]}}
        self.assertTrue(stage.relevant_clarification(pending, required))
        provisional = json.loads(json.dumps(pending))
        for issue in provisional["working_memory"]["subgoals"][0]["admission_issues"]:
            issue["code"] = "UNVERIFIED_PARAMETER_SOURCE"
        self.assertTrue(stage.relevant_clarification(provisional, required))
        for bad in ("record", "labels", "field", "premature"):
            altered = json.loads(json.dumps(pending))
            goal = altered["working_memory"]["subgoals"][0]
            if bad == "record": goal["record"] = "A"
            if bad == "labels": goal["deliveries"][0]["scope"]["labels"] = ["standard"]
            if bad == "field": goal["admission_issues"][0]["field"] = "channels"
            if bad == "premature": altered["tool_results"] = [{"success": True, "tool_name": "create_epochs"}]
            self.assertFalse(stage.relevant_clarification(altered, required), bad)


if __name__ == "__main__":
    unittest.main()
