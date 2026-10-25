"""Deterministic checks for the Issue #40 shared read/answer protocol."""

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from eeg_harness.research.task_memory_issue40 import (
    HISTORY_PATH, _admit_unit, load_spec, run_closed, same_history_turn, score_turn,
)
from eeg_harness.research.task_memory_issue39_budget import StageBudgetExhausted
from eeg_harness.research.task_memory_v2 import build_protocol_session, protocol_records
from eeg_harness.research.task_memory_v3 import EpisodeMemorySession
from eeg_harness.research.task_memory import live_turn


class FakeEvidenceClient:
    def __init__(self, action, answer=None):
        self.action = action
        self.answer = answer
        self.calls = []

    def complete(self, messages, tools, tool_choice="auto"):
        self.calls.append((messages, tools))
        if tools:
            return {"tool_calls": [{"function": {
                "name": "submit_evidence_action",
                "arguments": json.dumps(self.action)}}]}
        return {"content": self.answer}


class FakeActionClient:
    def __init__(self, action):
        self.action = action

    def complete(self, messages, tools, tool_choice="auto"):
        return {"tool_calls": [{"function": {
            "name": "submit_memory_action",
            "arguments": json.dumps(self.action)}}]}


class ClosedFake:
    def __init__(self):
        self.request_count = 0
        self.total_usage = {"total_tokens": 0}
        self.context = {}

    def set_context(self, **values):
        self.context = values

    def complete(self, messages, tools, tool_choice="auto"):
        self.request_count += 1
        self.total_usage["total_tokens"] += 10
        if not tools:
            return {"content": "A 的 SYNTH-C1 连续 alpha 功率为 2.00e-10 V²。"}
        kind = tools[0]["function"]["name"]
        if kind == "submit_evidence_action":
            action = ({"operation": "answer", "task_id": "N-short-t1",
                       "answer": "A 的 SYNTH-C1 连续 alpha 功率为 2.00e-10 V²。"}
                      if self.context["policy"] == "F" else
                      {"operation": "read", "task_id": "N-short-t1"})
        else:
            script = Issue40Tests.scripts["N-short"]
            step = script["steps"][int(self.context["unit_id"].split(":")[-1])]
            action = {"operation": "analyze", "record": step["record"],
                      "capability": step["capability"],
                      "parameters": step["parameters"]}
        return {"tool_calls": [{"function": {
            "name": kind, "arguments": json.dumps(action)}}]}


class Issue40Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scripts = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))["sessions"]
        cls.scripts = {item["id"]: item for item in scripts}

    def test_frozen_pairs_cover_three_histories_and_no_overlap(self):
        spec = load_spec()
        self.assertEqual(spec["policies"], ["F", "S", "H", "HE"])
        self.assertEqual({item["session"] for item in spec["development"]},
                         set(self.scripts))
        self.assertEqual({item["session"] for item in spec["confirmation"]},
                         set(self.scripts))
        self.assertFalse({(item["session"], item["query_index"])
                          for item in spec["development"]} &
                         {(item["session"], item["query_index"])
                          for item in spec["confirmation"]})

    def test_same_snapshot_direct_answer_and_read_have_equal_scientific_access(self):
        script = self.scripts["N-short"]
        base, keys = build_protocol_session(script, session_class=EpisodeMemorySession)
        query = script["queries"][0]
        target = keys[query["target"]]
        value = float(target.result["SYNTH-C1"]["alpha"])
        direct = FakeEvidenceClient({"operation": "answer", "task_id": target.task_id,
                                     "answer": f"A 连续功率 alpha 为 {value:.9e} V²/Hz"})
        read = FakeEvidenceClient({"operation": "read", "task_id": target.task_id},
                                  f"A 连续功率 alpha 为 {value:.9e} V²/Hz")
        f = same_history_turn(deepcopy(base), "F", query["text"], direct)
        h = same_history_turn(deepcopy(base), "H", query["text"], read)
        self.assertEqual(len(direct.calls), 1)
        self.assertEqual(len(read.calls), 2)
        self.assertEqual(h["read"]["task_id"], target.task_id)
        self.assertTrue(score_turn(base, script, query, keys, f)["valid_screen"])
        self.assertTrue(score_turn(base, script, query, keys, h)["valid_screen"])
        self.assertNotIn("target_key", json.dumps(direct.calls))

    def test_wrong_evidence_with_same_numeric_value_is_not_accepted(self):
        script = self.scripts["N-short"]
        base, keys = build_protocol_session(script, session_class=EpisodeMemorySession)
        query = script["queries"][0]
        expected = keys[query["target"]].result["SYNTH-C1"]["alpha"]
        wrong = keys["b_power"]
        observed = same_history_turn(deepcopy(base), "F", query["text"],
                                     FakeEvidenceClient({"operation": "answer",
                                                         "task_id": wrong.task_id,
                                                         "answer": str(expected)}))
        self.assertFalse(score_turn(base, script, query, keys, observed)["valid_screen"])

    def test_budget_admits_whole_unit_and_rejects_duplicate(self):
        spec = load_spec()
        with TemporaryDirectory() as folder:
            ledger = Path(folder) / "budget.jsonl"
            with patch("eeg_harness.research.task_memory_issue40.LEDGER", ledger):
                _admit_unit(spec, "development", "development:N-short:0")
                ledger.write_text(json.dumps({"event": "reserved", "request_id": "1",
                                              "reserved_tokens": 100,
                                              "context": {"unit_id": "development:N-short:0"}}))
                with self.assertRaises(StageBudgetExhausted):
                    _admit_unit(spec, "development", "development:N-short:0")

    def test_revision_inherits_parent_capability_but_conflict_rejected(self):
        script = self.scripts["N-long"]
        session = EpisodeMemorySession("revise", protocol_records(script))
        old, revised = script["steps"][0], script["steps"][6]
        parent = session.analyze("A", old["capability"], old["parameters"], old["text"])
        omitted = live_turn(session, "F", revised["text"],
                            FakeActionClient({"operation": "revise",
                                              "parent_task_id": parent["task_id"],
                                              "parameters": revised["parameters"]}))
        self.assertEqual(omitted["outcome"]["status"], "completed")
        conflicting = live_turn(session, "F", "错误地改成幅值", FakeActionClient({
            "operation": "revise", "parent_task_id": parent["task_id"],
            "capability": "amplitude", "parameters": revised["parameters"]}))
        self.assertEqual(conflicting["outcome"]["code"], "INVALID_REVISION_PARENT")

    def test_corrected_closed_interface_allows_full_history_direct_answer(self):
        with TemporaryDirectory() as folder:
            with patch("eeg_harness.research.task_memory_issue40.LEDGER",
                       Path(folder) / "budget.jsonl"):
                rows = run_closed(ClosedFake(), save=lambda _: None,
                                  direct_history=True)
        self.assertEqual(len(rows), 8)
        self.assertEqual(rows[3]["llm_completions"], 1)
        self.assertEqual(rows[7]["llm_completions"], 2)
        self.assertTrue(rows[3]["score"]["valid_screen"])
        self.assertTrue(rows[7]["score"]["valid_screen"])


if __name__ == "__main__":
    unittest.main()
