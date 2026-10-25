"""Deterministic scientific and fairness checks for Issue #41 (no API)."""

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from eeg_harness.research.task_memory_issue39_budget import StageBudgetExhausted
from eeg_harness.research.task_memory_issue41 import (
    LEDGER, _admit_pair, build_session, load_spec, protocol_records41,
    result_view, same_history_turn, score_turn, select_context41,
)


class FakeEvidence:
    def __init__(self, action, final=None):
        self.action = action
        self.final = final
        self.calls = []

    def complete(self, messages, tools, tool_choice="auto"):
        self.calls.append((messages, tools))
        if tools:
            return {"tool_calls": [{"function": {
                "name": "submit_evidence_action",
                "arguments": json.dumps(self.action)}}]}
        return {"content": self.final}


class Issue41Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec()
        cls.scripts = {item["id"]: item for item in cls.spec["confirmation_scripts"]}

    def test_frozen_protocol_has_complete_four_arm_pairs_and_real_tools(self):
        self.assertEqual(self.spec["policies"], ["F", "S", "H", "HC"])
        self.assertEqual(len(self.spec["development"]), 4)
        self.assertEqual(len(self.spec["confirmation"]), 4)
        for script in self.scripts.values():
            session, keys = build_session(script)
            self.assertEqual(len(keys), len(script["steps"]))
            self.assertTrue(all(entry.tool_trace for entry in session.entries))
            self.assertTrue(all(entry.evidence["source"].startswith("synthetic://issue41")
                                for entry in session.entries))

    def test_size_rule_retains_exact_small_result_and_indexes_large_result(self):
        continuous, ckeys = build_session(self.scripts["C-continuous"])
        event, ekeys = build_session(self.scripts["C-event"])
        self.assertEqual(result_view(ckeys["a_amp_old"])["result_view"], "exact")
        self.assertEqual(result_view(ckeys["a_amp_old"])["exact_result"],
                         ckeys["a_amp_old"].result)
        large = result_view(ekeys["b_flash_power"])
        self.assertEqual(large["result_view"], "indexed")
        self.assertNotIn("1.0e-", json.dumps(large))
        self.assertIn("alpha", large["field_index"]["conditions"]["flash"]
                      ["channels"]["SYNTH-C1"])
        selected = select_context41(continuous, "A 旧幅值是多少", "HC")
        self.assertTrue(any("exact_result" in card for card in
                            selected["payload"]["working_tasks"]))
        self.assertNotIn("scientific_object_groups", selected["payload"])

    def test_field_read_has_provenance_but_no_full_result_or_trace(self):
        session, keys = build_session(self.scripts["C-event"])
        task = keys["b_flash_power"]
        paths = [["conditions", "flash", "channels", "SYNTH-C1", "alpha"],
                 ["conditions", "flash", "channels", "SYNTH-C2", "alpha"]]
        result = session.read_task_fields(task.task_id, paths,
                                          "B 的 flash 事件窗两通道 alpha 功率")
        self.assertEqual(result["status"], "read_fields")
        self.assertEqual(result["record"], "B")
        self.assertEqual(result["unit_or_kind"], "V²")
        self.assertEqual(result["revision_of"], None)
        self.assertEqual(len(result["fields"]), 2)
        self.assertNotIn("result", result)
        self.assertNotIn("tool_trace", result)
        self.assertLess(session.read_payload_bytes,
                        len(json.dumps(task.result, ensure_ascii=False).encode("utf-8")) +
                        len(json.dumps(task.tool_trace, ensure_ascii=False).encode("utf-8")))

    def test_illegal_field_and_scope_fail_closed(self):
        session, keys = build_session(self.scripts["C-event"])
        task = keys["b_flash_power"]
        before = session.evidence_reads
        self.assertEqual(session.read_task_fields(task.task_id,
                          [["conditions", "flash", "channels"]],
                          "B 的 flash 事件功率")["code"], "FIELD_NOT_SCALAR")
        self.assertEqual(session.read_task_fields(task.task_id,
                          [["conditions", "unknown"]],
                          "B 的 flash 事件功率")["code"], "FIELD_NOT_FOUND")
        self.assertEqual(session.read_task_fields(task.task_id,
                          [["conditions", "flash", "epoch_count"]],
                          "A 的 flash 事件功率")["code"], "SCIENTIFIC_SCOPE_MISMATCH")
        self.assertEqual(session.evidence_reads, before)

    def test_direct_small_answer_and_projected_two_field_answer(self):
        continuous, ckeys = build_session(self.scripts["C-continuous"])
        q0 = self.scripts["C-continuous"]["queries"][0]
        rms = ckeys["a_amp_old"].result["SYNTH-C1"]["rms"]
        direct = FakeEvidence({"operation": "answer",
                               "task_id": ckeys["a_amp_old"].task_id,
                               "answer": f"A 旧窗口 0–2 秒 RMS {rms} V"})
        result = same_history_turn(deepcopy(continuous), "HC", q0["text"], direct)
        self.assertEqual(len(direct.calls), 1)
        self.assertTrue(score_turn(continuous, self.scripts["C-continuous"],
                                   q0, ckeys, result)["valid_screen"])

        event, ekeys = build_session(self.scripts["C-event"])
        query = self.scripts["C-event"]["queries"][0]
        task = ekeys["b_flash_power"]
        values = [task.result["conditions"]["flash"]["channels"][name]["alpha"]
                  for name in ("SYNTH-C1", "SYNTH-C2")]
        client = FakeEvidence({"operation": "read_fields", "task_id": task.task_id,
                               "field_paths": query["fields"]},
                              f"B flash 0–1 秒 SYNTH-C1={values[0]} V²；"
                              f"SYNTH-C2={values[1]} V²。")
        projected = same_history_turn(deepcopy(event), "HC", query["text"], client)
        self.assertEqual(len(client.calls), 2)
        self.assertTrue(score_turn(event, self.scripts["C-event"], query,
                                   ekeys, projected)["valid_screen"])
        wrong_unit = deepcopy(projected)
        wrong_unit["answer"] = wrong_unit["answer"].replace("V²", "V²/Hz")
        self.assertFalse(score_turn(event, self.scripts["C-event"], query,
                                    ekeys, wrong_unit)["valid_screen"])

    def test_ambiguous_request_must_clarify(self):
        event, keys = build_session(self.scripts["C-event"])
        query = self.scripts["C-event"]["queries"][1]
        output = same_history_turn(deepcopy(event), "HC", query["text"],
                                   FakeEvidence({"operation": "clarify",
                                                 "question": "请明确 oddball 或 standard 及版本。"}))
        self.assertTrue(score_turn(event, self.scripts["C-event"], query,
                                   keys, output)["valid_screen"])
        unsafe = same_history_turn(deepcopy(event), "HC", query["text"],
                                   FakeEvidence({"operation": "answer",
                                                 "task_id": keys["a_standard"].task_id,
                                                 "answer": "2 V²"}))
        self.assertFalse(score_turn(event, self.scripts["C-event"], query,
                                    keys, unsafe)["valid_screen"])

    def test_new_stage_ledger_rejects_repeated_whole_unit(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "budget.jsonl"
            with patch("eeg_harness.research.task_memory_issue41.LEDGER", path):
                _admit_pair(self.spec, "development", "development:v2:N-short:0")
                path.write_text(json.dumps({"event": "reserved", "request_id": "1",
                                            "reserved_tokens": 100,
                                            "context": {"unit_id": "development:v2:N-short:0"}}))
                with self.assertRaises(StageBudgetExhausted):
                    _admit_pair(self.spec, "development", "development:v2:N-short:0")


if __name__ == "__main__":
    unittest.main()
