"""Scientific output sets on actual synthetic EEG and the original Executor.

These tests verify deterministic mechanisms, not autonomous model performance.
"""
import json
import unittest

import numpy as np

from eeg_harness.research.task_memory import synthetic_records
from eeg_harness.research.task_memory_v2 import independent_oracle
from eeg_harness.working_memory_actions import ActionWorkingMemoryStore
from eeg_harness.working_memory_scientific_tasks import ScientificTaskStore


W = {"channels": ["SYNTH-C1"], "start": 0, "end": 2}
V = {"channels": ["SYNTH-C1"], "start": 2, "end": 4}
E = {"labels": ["stimulus"], "tmin": 0, "tmax": 1}


class ScientificTaskTest(unittest.TestCase):
    def setUp(self):
        self.s = ScientificTaskStore("scientific", synthetic_records())

    def request(self, text):
        self.s.user_requests.append(text)
        self.s.turn += 1

    def requirements(self, *rows):
        return [{"tool": tool, "record": record, "scope": scope} for tool,record,scope in rows]

    def test_frozen_first_failure_and_two_actual_windows(self):
        text = "记录A SYNTH-C1在0到2秒计算PSD；记录A SYNTH-C1在2到4秒计算PSD。"
        old = ActionWorkingMemoryStore("old-reproduction", synthetic_records())
        old.user_requests.append(text)
        old.turn = 1
        old.focus_task("两个窗", "A", ["psd", "psd"])
        first = old.execute_action("psd", W, request_span="记录A SYNTH-C1在0到2秒计算PSD")
        self.assertEqual(first["archive"]["status"], "completed")
        self.assertEqual(len(old.entries), 1)  # Preserve/reproduce the old failure.
        self.request(text)
        self.s.focus_task("两个窗", "A", self.requirements(("psd","A",W),("psd","A",V)))
        first = self.s.execute_action("psd", W)
        self.assertTrue(first["observation"]["result"]["success"])
        self.assertFalse(first["progress"]["ready"])
        self.assertIsNotNone(self.s.active)
        self.assertNotIn("archive", first)
        second = self.s.execute_action("psd", V)
        self.assertTrue(second["progress"]["ready"])
        self.assertIsNotNone(self.s.active)
        self.assertEqual(self.s.settle_active()["status"], "completed")
        self.assertEqual(len(self.s.subgoals), 1)
        self.assertEqual(self.s.entries[0].result, old.entries[0].result)
        for entry in self.s.entries:
            oracle = independent_oracle(self.s.records[entry.record],
                {"capability":"psd", "parameters":entry.parameters}, ["SYNTH-C1","alpha"])
            self.assertTrue(np.isclose(float(entry.result["SYNTH-C1"]["alpha"]),oracle,rtol=.005))

    def test_same_scope_distinct_records_are_distinct_outputs(self):
        self.request("记录A SYNTH-C1在0到2秒算幅值；记录B SYNTH-C1在0到2秒算幅值。")
        self.s.focus_task("两记录", "A", self.requirements(("amplitude","A",W),("amplitude","B",W)))
        a = self.s.execute_action("amplitude", W, record="A")
        b = self.s.execute_action("amplitude", W, record="B")
        self.assertFalse(a["progress"]["ready"])
        self.assertTrue(b["progress"]["ready"])
        self.assertEqual([e.record for e in self.s.entries], ["A","B"])
        self.assertEqual([o["record"] for o in self.s.active.observations], ["A","B"])
        self.assertEqual(len(self.s.active.deliveries), 2)
        card = self.s.goal_card(self.s.active)
        self.assertIsNone(card["record"])
        self.assertEqual(card["records"], ["A","B"])
        self.assertEqual(card["default_record"], "A")
        for entry in self.s.entries:
            oracle = independent_oracle(self.s.records[entry.record],
                {"capability":"amplitude", "parameters":W}, ["SYNTH-C1","rms"])
            self.assertTrue(np.isclose(float(entry.result["SYNTH-C1"]["rms"]),oracle,rtol=.005))
        json.dumps(self.s.settle_active(), allow_nan=False)

    def test_missing_event_scope_does_not_block_continuous_then_resume(self):
        self.request("记录A SYNTH-C1在0到2秒计算幅值和PSD；stimulus事件窗口稍后提供。")
        self.s.focus_task("连续与事件", "A", self.requirements(
            ("amplitude","A",W),("psd","A",W),("event_bandpower","A",{"labels":["stimulus"]})))
        missing = self.s.execute_action("create_epochs", {"labels":["stimulus"]})
        self.assertEqual(missing["code"], "MISSING_SCIENTIFIC_PARAMETER")
        for name in ("amplitude","psd"):
            out = self.s.execute_action(name,W)
            self.assertTrue(out["observation"]["result"]["success"])
        self.assertEqual(self.s.settle_active()["status"], "suspended")
        self.request("stimulus事件窗口0到1秒，连续结果沿用。")
        self.s.focus_task("连续与事件", "A")
        create = self.s.execute_action("create_epochs",E)
        artifact = create["observation"]["result"]["data"]["artifact_id"]
        done = self.s.execute_action("event_bandpower",{"artifact_id":artifact})
        self.assertTrue(done["progress"]["ready"])
        self.assertEqual(len(self.s.subgoals),1)
        self.assertEqual(len(self.s.entries),4)
        self.assertEqual(self.s.settle_active()["status"],"completed")

    def test_unfilled_scope_does_not_satisfy_from_any_historical_value(self):
        self.request("记录A SYNTH-C1在0到2秒计算PSD。")
        self.s.execute_action("psd", W)
        self.s.settle_active()
        self.s.focus_task("另一个目的", "A", self.requirements(("psd","A",{})))
        self.assertFalse(self.s.completion_check(self.s.active)["ready"])
        self.assertEqual(self.s.completion_check(self.s.active)["requirements"][0]["status"],"awaiting_parameter")
        # Deliberate actual action can reuse the valid result; merely having it
        # in storage cannot fill an unspecified requirement opportunistically.
        reused = self.s.execute_action("psd", W)
        self.assertEqual(reused["status"],"reused")
        self.assertTrue(reused["progress"]["ready"])
        self.assertEqual(len(self.s.entries),1)

    def test_identical_duplicate_requirement_rejected_not_silently_deduplicated(self):
        out = self.s.focus_task("duplicate","A",self.requirements(("psd","A",W),("psd","A",W)))
        self.assertEqual(out["code"],"INVALID_REQUIREMENTS")
        self.assertFalse(self.s.subgoals)

    def test_refocus_does_not_drop_pending_or_duplicate_filled_partial_scope(self):
        self.request("记录A SYNTH-C1在0到2秒计算PSD和幅值。")
        contract = self.requirements(("psd","A",{"channels":["SYNTH-C1"]}),("amplitude","A",W))
        self.s.focus_task("same","A",contract)
        self.s.execute_action("psd",W)
        self.s.focus_task("same","A",contract[:1])
        self.assertEqual(len(self.s.active.requirements),2)
        self.assertFalse(self.s.completion_check(self.s.active)["ready"])
        self.assertEqual(self.s.settle_active()["status"],"suspended")

    def test_cross_record_execution_cursor_cannot_change_resume_identity(self):
        self.request("记录A SYNTH-C1在0到2秒算幅值；记录B SYNTH-C1在0到2秒算幅值。")
        self.s.focus_task("两记录续接","A",self.requirements(("amplitude","A",W),("amplitude","B",W)))
        original = self.s.active.subgoal_id
        self.s.execute_action("amplitude",W,record="B")
        self.assertEqual(self.s.active.record,"B")
        self.s.settle_active()
        self.request("继续原来的两记录分析。")
        self.s.focus_task("两记录续接")
        self.assertEqual(self.s.active.subgoal_id,original)
        self.assertEqual(self.s.active.default_record,"A")
        self.assertEqual(len(self.s.subgoals),1)

    def test_actual_epoch_dependency_keeps_active_trace_and_restores_for_quality(self):
        self.request("记录A的stimulus事件，窗口0到1秒，测量质量并算频带功率。")
        self.s.focus_task("事件质量功率","A",self.requirements(
            ("epoch_quality","A",E),("event_bandpower","A",E)))
        create = self.s.execute_action("create_epochs",E)
        artifact = create["observation"]["result"]["data"]["artifact_id"]
        self.assertFalse(create["progress"]["ready"])
        self.s.execute_action("epoch_quality",{"artifact_id":artifact})
        final = self.s.execute_action("event_bandpower",{"artifact_id":artifact})
        self.assertTrue(final["progress"]["ready"])
        self.assertEqual(len(self.s.active.observations),3)
        goal_id = self.s.active.subgoal_id
        self.s.settle_active()
        restored = self.s.restore_subgoal(goal_id)
        self.assertEqual(len(restored["action_observations"]),3)
        self.request("沿用原来的stimulus事件和原窗口，追加试次数量。")
        out = self.s.execute_action("epoch_summary",{"artifact_id":restored["action_observations"][0]["result"]["data"]["artifact_id"]})
        self.assertTrue(out["observation"]["result"]["success"])
        self.assertEqual(len(self.s.contexts["A"].artifacts),1)

    def test_record_qualified_epoch_pins_do_not_mix_identical_scopes(self):
        self.request("记录A stimulus窗口0到1秒；记录B stimulus窗口0到1秒。")
        self.s.focus_task("两记录事件","A",self.requirements(
            ("event_bandpower","A",E),("event_bandpower","B",E)))
        ids = []
        for record in ("A","B"):
            create = self.s.execute_action("create_epochs",E,record=record)
            ident = create["observation"]["result"]["data"]["artifact_id"]
            ids.append(ident)
            out = self.s.execute_action("event_bandpower",{"artifact_id":ident},record=record)
            self.assertTrue(out["observation"]["result"]["success"])
        self.assertNotEqual(ids[0],ids[1])
        self.assertEqual(len(self.s.active.pinned_artifacts),2)
        self.assertTrue(self.s.completion_check(self.s.active)["ready"])

    def test_invalid_partial_scope_is_structured_error_not_exception(self):
        self.request("记录A做PSD。")
        out = self.s.execute_action("psd",{"nonexistent":1})
        self.assertEqual(out["code"],"INVALID_SCOPE")
        self.assertFalse(self.s.entries)

    def test_rejected_implicit_proposal_cannot_become_a_permanent_required_scope(self):
        self.request("记录A SYNTH-C1在0到2秒算PSD；记录B SYNTH-C1在2到4秒算PSD。")
        wrong = self.s.execute_action("psd",V,record="A",request_span="SYNTH-C1在2到4秒算PSD")
        self.assertEqual(wrong["status"],"rejected")
        self.assertFalse(self.s.active.requirements)
        corrected = self.s.execute_action("psd",W,record="A")
        self.assertTrue(corrected["progress"]["ready"])
        self.assertEqual(self.s.active.requirements,self.requirements(("psd","A",W)))
        self.assertEqual(self.s.settle_active()["status"],"completed")

    def test_raw_numeric_entry_cannot_skip_scientific_admission(self):
        self.assertEqual(self.s.execute_numeric("psd",W)["code"],"USE_SCIENTIFIC_ACTION")
        self.s.focus_task("not-authorized","A",self.requirements(("psd","A",W)))
        out = self.s.execute_numeric("psd",W)
        self.assertFalse(out["observation"]["result"]["success"])
        self.assertEqual(out["observation"]["result"]["error"]["code"],"ACTION_NOT_ADMITTED")
        self.assertFalse(self.s.entries)
        self.assertFalse(self.s.contexts["A"].history)

    def test_wrong_artifact_attempt_does_not_make_a_guessed_handle_permanent(self):
        self.request("记录A stimulus事件窗口0到1秒计算频带功率。")
        self.s.focus_task("recover","A",self.requirements(("event_bandpower","A",E)))
        created = self.s.execute_action("create_epochs",E)
        actual = created["observation"]["result"]["data"]["artifact_id"]
        wrong = self.s.execute_action("event_bandpower",{"artifact_id":"not-an-actual-artifact"})
        self.assertEqual(wrong["code"],"ARTIFACT_NOT_FOUND")
        corrected = self.s.execute_action("event_bandpower",{"artifact_id":actual})
        self.assertTrue(corrected["progress"]["ready"])
        self.assertEqual(len(self.s.entries),2)

    def test_scientifically_distinct_condition_is_not_fulfilled_by_existing_one(self):
        self.request("记录A stimulus和control事件都取0到1秒窗口。")
        other = {**E,"labels":["control"]}
        self.s.focus_task("两个条件","A",self.requirements(
            ("event_bandpower","A",E),("event_bandpower","A",other)))
        create = self.s.execute_action("create_epochs",E)
        out = self.s.execute_action("event_bandpower",{"artifact_id":create["observation"]["result"]["data"]["artifact_id"]})
        self.assertFalse(out["progress"]["ready"])
        self.assertEqual([r["status"] for r in out["progress"]["requirements"]],["satisfied","missing"])

    def test_changed_record_identity_invalidates_satisfied_output(self):
        self.request("记录A SYNTH-C1在0到2秒计算PSD。")
        self.s.focus_task("fingerprint","A",self.requirements(("psd","A",W)))
        self.assertTrue(self.s.execute_action("psd",W)["progress"]["ready"])
        self.s.contexts["A"].record = self.s.records["B"]
        check = self.s.completion_check(self.s.active)
        self.assertFalse(check["ready"])
        self.assertEqual(check["requirements"][0]["status"],"stale")


if __name__ == "__main__":
    unittest.main()
