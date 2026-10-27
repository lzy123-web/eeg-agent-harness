"""Action-local scientific admission on the original EEG numerical Executor.

These deterministic decisions verify mechanisms, never model autonomy.
"""
import json
import unittest

import numpy as np

from eeg_harness.research.task_memory import synthetic_records
from eeg_harness.research.task_memory_v2 import independent_oracle
from eeg_harness.working_memory_actions import ActionWorkingMemoryStore


W = {"channels": ["SYNTH-C1"], "start": 0, "end": 2}
E = {"labels": ["stimulus"], "tmin": 0, "tmax": 1}


class ActionMemoryTest(unittest.TestCase):
    def setUp(self):
        self.s = ActionWorkingMemoryStore("action", synthetic_records())

    def request(self, text):
        self.s.user_requests.append(text)
        self.s.turn += 1

    def test_missing_event_window_does_not_block_independent_results(self):
        self.request("记录A的SYNTH-C1在0到2秒RMS和功率；stimulus事件窗稍后提供。")
        focused = self.s.focus_task("连续与事件结果", "A", ["amplitude", "psd", "event_bandpower"])
        controls = focused["task"]["available_control"]
        self.assertIn("read_result", controls)
        for legacy_control in ("close_subgoal", "read_evidence", "restore_subgoal"):
            self.assertNotIn(legacy_control, controls)
        missing = self.s.execute_action("create_epochs", {"labels": ["stimulus"]})
        self.assertEqual(missing["code"], "MISSING_SCIENTIFIC_PARAMETER")
        for name in ("amplitude", "psd"):
            actual = self.s.execute_action(name, W)
            self.assertTrue(actual["observation"]["result"]["success"])
            self.assertFalse(actual["progress"]["valid"])
        expected = independent_oracle(self.s.records["A"], {"capability": "amplitude", "parameters": W}, ["SYNTH-C1", "rms"])
        self.assertTrue(np.isclose(float(self.s.entries[0].result["SYNTH-C1"]["rms"]), expected, rtol=.005))
        self.assertEqual(self.s.active.pending_actions[0]["tool"], "create_epochs")
        self.s.settle_active()
        self.request("事件窗口0到1秒，其他沿用。")
        self.s.focus_task("连续与事件结果", "A")
        epoch = self.s.execute_action("create_epochs", E)["observation"]["result"]["data"]
        final = self.s.execute_action("event_bandpower", {"artifact_id": epoch["artifact_id"]})
        self.assertEqual(final["archive"]["status"], "completed")
        self.assertEqual(len(self.s.subgoals), 1)
        self.assertEqual(len(self.s.entries), 4)
        self.assertEqual(len(self.s.contexts["A"].artifacts), 1)
        self.assertEqual(self.s.entries[-1].tool_trace[0]["scientific_sources"]["tmax"]["kind"], "artifact")
        json.dumps(final, allow_nan=False)

    def test_new_event_window_cannot_borrow_continuous_range(self):
        self.request("记录A SYNTH-C1在0到2秒算PSD；stimulus事件窗待定。")
        self.s.focus_task("混合", "A")
        self.s.execute_action("create_epochs", {"labels": ["stimulus"]})
        rejected = self.s.execute_action("create_epochs", {**E, "tmax": 2})
        self.assertEqual(rejected["code"], "SCIENTIFIC_SCOPE_UNGROUNDED")
        self.assertFalse(self.s.contexts["A"].artifacts)

    def test_punctuation_never_mixes_absolute_and_event_relative_scopes(self):
        # This failure was found in independent post-implementation review:
        # comma-delimited prose must get the same protection as semicolons.
        for separator in (",", "，", ";", "；"):
            for reverse in (False, True):
                with self.subTest(separator=separator, reverse=reverse):
                    s = ActionWorkingMemoryStore("clauses", synthetic_records())
                    text = ("记录A stimulus在0到1秒创建试次" + separator + "SYNTH-C1连续窗口待定。" if reverse else
                            "记录A SYNTH-C1在0到2秒PSD" + separator + "stimulus事件窗口待定。")
                    s.turn, s.user_requests = 1, [text]
                    s.focus_task("混合", "A", ["psd", "create_epochs"])
                    out = s.execute_action("psd", {**W, "end": 1}) if reverse else s.execute_action("create_epochs", {**E, "tmax": 2})
                    self.assertEqual(out["code"], "SCIENTIFIC_SCOPE_UNGROUNDED")
                    self.assertFalse(s.entries)
        self.request("记录A SYNTH-C1在0到2秒PSD同时stimulus事件窗口待定。")
        self.assertEqual(self.s.execute_action("create_epochs", {**E, "tmax": 2})["code"], "SCIENTIFIC_SCOPE_UNGROUNDED")
        # A cut-down span cannot erase the continuous object's identity after
        # the event label has already been admitted as a partial requirement.
        self.assertEqual(self.s.execute_action("create_epochs", {**E, "tmax": 2},
            request_span="0到2秒")["code"], "SCIENTIFIC_SCOPE_UNGROUNDED")

    def test_commas_preserve_real_object_lists_and_numeric_interval_pairs(self):
        self.request("记录A SYNTH-C1,SYNTH-C2 在[0, 2]秒做PSD。")
        out = self.s.execute_action("psd", {**W, "channels": ["SYNTH-C1", "SYNTH-C2"]})
        self.assertTrue(out["observation"]["result"]["success"])
        self.request("记录A stimulus，control 使用[0，1]秒创建试次。")
        out = self.s.execute_action("create_epochs", {**E, "labels": ["stimulus", "control"]})
        self.assertTrue(out["observation"]["result"]["success"])

    def test_independent_objects_cannot_form_cartesian_product_of_parameters(self):
        self.request("记录A SYNTH-C1在0到2秒PSD；SYNTH-C2在2到4秒PSD；稍后质量。")
        self.s.focus_task("多个PSD", "A", ["psd", "record_quality"])
        self.s.execute_action("psd", W)
        other = {"channels": ["SYNTH-C2"], "start": 2, "end": 4}
        self.s.execute_action("psd", other)
        rejected = self.s.execute_action("psd", {**W, "channels": ["SYNTH-C2"]})
        self.assertEqual(rejected["code"], "SCIENTIFIC_SCOPE_UNGROUNDED")
        self.assertEqual(len(self.s.entries), 2)
        self.assertIsNone(self.s.entries[1].revision_of)

    def test_pending_same_tool_other_object_survives_success(self):
        self.request("记录A SYNTH-C1在0到2秒PSD；SYNTH-C2的PSD时间窗待定。")
        self.s.focus_task("两通道分别PSD", "A", ["psd"])
        self.s.execute_action("psd", {"channels": ["SYNTH-C2"]})
        ok = self.s.execute_action("psd", W)
        self.assertEqual(ok["status"], "observed")
        self.assertFalse(ok["progress"]["valid"])
        self.assertEqual(self.s.active.pending_actions[0]["arguments"], {"channels": ["SYNTH-C2"]})

    def test_unexecuted_historical_object_can_receive_current_window_without_touch(self):
        self.request("记录A SYNTH-C1在0到2秒RMS；stimulus事件中SYNTH-C2功率，事件窗稍后提供。")
        self.s.execute_action("amplitude", W)
        self.s.execute_action("list_events", {})
        self.assertFalse(self.s.contexts["A"].artifacts)
        self.assertTrue(all(not g.pending_actions for g in self.s.subgoals))
        self.request("事件窗使用发生后0到1.25秒，其余事件条件不变。连续分析窗口改为4到6秒。")
        scope = {**E, "tmax": 1.25}
        ambiguous = self.s.execute_action("create_epochs", scope)
        self.assertEqual(ambiguous["code"], "SCIENTIFIC_SCOPE_UNGROUNDED")
        result = self.s.execute_action("create_epochs", scope,
            request_span="事件窗使用发生后0到1.25秒")
        self.assertTrue(result["observation"]["result"]["success"])
        sources = self.s.entries[-1].tool_trace[0]["scientific_sources"]
        self.assertEqual(sources["labels"]["turn"], 1)
        self.assertEqual(sources["labels"]["basis"], "unique_historical_object_identity")
        self.assertEqual(sources["tmax"]["turn"], 2)
        # Historical numerical values never supply the new event window.
        fabricated = self.s.execute_action("create_epochs", {**E, "tmax": 2},
            request_span="事件窗使用发生后0到1.25秒")
        self.assertEqual(fabricated["code"], "SCIENTIFIC_SCOPE_UNGROUNDED")

    def test_ambiguous_historical_objects_or_records_do_not_supply_missing_identity(self):
        for first in (
            "记录A stimulus事件窗待定；control事件窗也待定。",
            "记录A stimulus事件窗待定；记录B stimulus事件窗也待定。",
        ):
            with self.subTest(first=first):
                s = ActionWorkingMemoryStore("ambiguity", synthetic_records())
                s.user_requests, s.turn = [first, "使用0到1秒，其余不变。"], 2
                out = s.execute_action("create_epochs", E, record="A")
                self.assertEqual(out["code"], "SCIENTIFIC_SCOPE_UNGROUNDED")
                self.assertFalse(s.entries)
        # Merely existing in record metadata never authorizes an unused label.
        self.request("记录A SYNTH-C1在0到2秒算RMS。")
        self.request("使用0到1秒。")
        self.assertEqual(self.s.execute_action("create_epochs", E)["code"], "SCIENTIFIC_SCOPE_UNGROUNDED")

    def test_multi_record_source_span_is_once_per_action(self):
        a = "记录A SYNTH-C1在0到2秒PSD"
        b = "记录B SYNTH-C1在2到4秒PSD"
        self.request(a + "；" + b)
        rejected = self.s.execute_action("psd", W, record="A")
        self.assertEqual(rejected["code"], "RECORD_SCOPE_CONFLICT")
        self.assertEqual(self.s.execute_action("psd", W, record="A", request_span=a)["status"], "observed")
        wrong = self.s.execute_action("psd", W, record="B", request_span=a)
        self.assertEqual(wrong["code"], "RECORD_SCOPE_CONFLICT")
        self.assertEqual(self.s.execute_action("psd", W, request_span="invented")["code"], "INVALID_SOURCE_SPAN")

    def test_scope_swap_between_explicit_continuous_and_event_windows_refused(self):
        self.request("记录A SYNTH-C1在0到2秒PSD；stimulus事件后0到1秒功率。")
        self.s.focus_task("混合", "A")
        for name, args in (("psd", {**W, "end": 1}), ("create_epochs", {**E, "tmax": 2})):
            self.assertEqual(self.s.execute_action(name, args)["code"], "SCIENTIFIC_SCOPE_UNGROUNDED")
        self.assertFalse(self.s.entries)

    def test_inherited_result_revises_one_endpoint_without_repeating_sources(self):
        self.request("记录A SYNTH-C1在0到2秒PSD。")
        self.s.execute_action("psd", W)
        first = self.s.entries[0]
        self.request("将结束改成4秒，其他沿用。")
        out = self.s.execute_action("psd", {"end": 4}, inherit_result=first.task_id)
        self.assertEqual(out["status"], "observed")
        latest = self.s.entries[-1]
        self.assertEqual(latest.parameters, {**W, "end": 4})
        self.assertEqual(latest.revision_of, first.task_id)
        sources = latest.tool_trace[0]["scientific_sources"]
        self.assertEqual(sources["start"]["result_id"], first.task_id)
        self.assertEqual(sources["end"]["turn"], 2)
        wrong_record = self.s.execute_action("psd", W, record="B", inherit_result=first.task_id)
        self.assertEqual(wrong_record["code"], "INVALID_INHERITED_RESULT")

    def test_unchanged_scope_reuses_and_explicit_recompute_is_once(self):
        self.request("记录A SYNTH-C1在0到2秒PSD。")
        self.s.execute_action("psd", W)
        self.request("再告诉我原结果。")
        out = self.s.execute_action("psd", W, inherit_result=self.s.entries[0].task_id)
        self.assertEqual(out["status"], "reused")
        self.assertEqual(len(self.s.entries), 1)
        self.assertEqual(self.s.execute_action("psd", W, recompute=True)["code"], "UNAUTHORIZED_RECOMPUTATION")
        self.request("请重新计算记录A SYNTH-C1在0到2秒的PSD。")
        self.assertEqual(self.s.execute_action("psd", W, recompute=True)["status"], "observed")
        self.assertEqual(self.s.execute_action("psd", W, recompute=True)["status"], "reused")
        self.assertEqual(len(self.s.entries), 2)
        self.assertEqual(self.s.entries[1].revision_of, self.s.entries[0].task_id)

    def test_actual_artifact_identity_is_not_equal_content(self):
        self.request("记录A stimulus事件后0到1秒创建试次。")
        self.s.execute_action("create_epochs", E)
        original = self.s.entries[0]
        self.request("沿用原试次。")
        reused = self.s.execute_action("create_epochs", {}, inherit_result=original.task_id)
        self.assertEqual(reused["status"], "reused")
        self.assertEqual(len(self.s.contexts["A"].artifacts), 1)
        self.request("请重新计算记录A stimulus事件后0到1秒试次。")
        second = self.s.execute_action("create_epochs", E, recompute=True)["observation"]["result"]["data"]
        a = self.s.contexts["A"].artifacts[original.evidence["binding"]["artifact_id"]]
        b = self.s.contexts["A"].artifacts[second["artifact_id"]]
        self.assertEqual(a.content_fingerprint(), b.content_fingerprint())
        self.assertNotEqual(a.artifact_id, b.artifact_id)
        out = self.s.execute_action("epoch_quality", {"artifact_id": b.artifact_id}, inherit_result=original.task_id)
        self.assertEqual(out["code"], "ARTIFACT_IDENTITY_MISMATCH")
        self.assertEqual(self.s.execute_action("epoch_quality", {"artifact_id": a.artifact_id}, inherit_result=original.task_id)["status"], "observed")

    def test_forbidden_new_transform_and_malformed_source_are_not_missing_fields(self):
        self.request("记录A stimulus事件后0到1秒。")
        out = self.s.execute_action("create_epochs", {**E, "baseline": [0, .2]})
        self.assertEqual(out["code"], "INVALID_SCOPE")
        out = self.s.execute_action("create_epochs", E, request_span={"quote": self.s.user_requests[-1]})
        self.assertEqual(out["code"], "INVALID_SOURCE_SPAN")
        self.assertFalse(self.s.entries)

    def test_real_trace_restore_and_exact_read_preserve_scope_and_versions(self):
        self.request("记录A SYNTH-C1在0到2秒RMS。")
        first = self.s.execute_action("amplitude", W)
        entry = self.s.entries[0]
        restored = self.s.restore_subgoal(first["subgoal_id"])
        self.assertEqual(restored["status"], "restored")
        self.assertEqual(restored["action_observations"][0]["result_id"], entry.task_id)
        read = self.s.read_evidence(entry.task_id, "A", W)
        self.assertEqual(read["status"], "read")
        rms = next(f["value"] for f in read["evidence"]["fields"] if f["path"] == ["SYNTH-C1", "rms"])
        self.assertEqual(rms, entry.result["SYNTH-C1"]["rms"])
        rejected = self.s.read_evidence(entry.task_id, "B", W)
        self.assertEqual(rejected["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
