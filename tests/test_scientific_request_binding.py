"""Scientific admission counterexamples through the actual numerical Executor.

These are controlled interventions with independent sample oracles, not claims
that a real model autonomously attempted or avoided the crafted source crop.
"""
from dataclasses import replace
import json
import unittest

import numpy as np

from eeg_harness.events import EEGEvent, EventSet
from eeg_harness.research.task_memory import synthetic_records
from eeg_harness.research.task_memory_v2 import independent_oracle
from eeg_harness.working_memory_actions import ActionWorkingMemoryStore
from eeg_harness.working_memory_scientific_tasks import ScientificTaskStore


W = {"channels": ["SYNTH-C1"], "start": 0, "end": 2}
LATE = {"channels": ["SYNTH-C1"], "start": 2, "end": 4}
E = {"labels": ["stimulus"], "tmin": 0, "tmax": 1}


class ScientificRequestBindingTest(unittest.TestCase):
    def setUp(self):
        self.store = ScientificTaskStore("bound-source", synthetic_records())

    def request(self, text, store=None):
        store = store or self.store
        store.turn += 1
        store.user_requests.append(text)

    def assert_psd(self, store, record, scope):
        entry = store.entries[-1]
        self.assertEqual((entry.record, entry.parameters), (record, scope))
        for channel in scope["channels"]:
            raw = independent_oracle(store.records[record], {
                "capability": "psd", "parameters": scope}, [channel, "alpha"])
            self.assertTrue(np.isclose(float(entry.result[channel]["alpha"]), raw,
                                       rtol=.005, atol=1e-25))
        self.assertTrue(store._binding_valid(entry))

    def test_actual_old_executor_crop_failure_is_retained_and_new_path_rejects(self):
        text = "记录A的SYNTH-C1在0到2秒计算PSD；记录B的SYNTH-C1在2到4秒计算PSD。"
        crop = "SYNTH-C1在2到4秒计算PSD"
        old = ActionWorkingMemoryStore("frozen-issue50-repro", synthetic_records())
        self.request(text, old)
        old_out = old.execute_action("psd", LATE, record="A", request_span=crop)
        self.assertTrue(old_out["observation"]["result"]["success"])
        self.assertEqual(len(old.contexts["A"].trace.events), 1)
        self.assert_psd(old, "A", LATE)  # wrong authorization, correct A arithmetic
        self.request(text)
        out = self.store.execute_action("psd", LATE, record="A", request_span=crop)
        self.assertEqual(out["code"], "RECORD_SCOPE_CONFLICT")
        self.assertFalse(self.store.entries)
        self.assertFalse(self.store.contexts["A"].trace.events)
        legal = self.store.execute_action("psd", W, record="A")
        self.assertTrue(legal["observation"]["result"]["success"])
        self.assert_psd(self.store, "A", W)

    def test_explicit_records_each_execute_without_model_copied_quotes(self):
        self.request("记录A的SYNTH-C1在0到2秒计算PSD；记录B的SYNTH-C1在2到4秒计算PSD。")
        for record, scope in (("A", W), ("B", LATE)):
            out = self.store.execute_action("psd", scope, record=record)
            self.assertTrue(out["observation"]["result"]["success"])
            self.assert_psd(self.store, record, scope)
        self.assertEqual([len(c.trace.events) for c in self.store.contexts.values()], [1, 1])

    def test_shared_explicit_records_same_interval_are_legal(self):
        self.request("记录A和记录B的SYNTH-C1均在0到2秒计算PSD。")
        for record in ("A", "B"):
            out = self.store.execute_action("psd", W, record=record)
            self.assertTrue(out["observation"]["result"]["success"])
            self.assert_psd(self.store, record, W)
        self.assertNotEqual(self.store.entries[0].result, self.store.entries[1].result)

    def test_shared_records_with_multiple_intervals_require_explicit_pairing(self):
        self.request("记录A和记录B的SYNTH-C1分别在0到2秒和2到4秒计算PSD。")
        for record in ("A", "B"):
            for scope in (W, LATE):
                out = self.store.execute_action("psd", scope, record=record)
                self.assertEqual(out["code"], "SCIENTIFIC_SCOPE_UNGROUNDED")
        self.assertFalse(self.store.entries)

    def test_record_scoped_object_lists_cannot_be_cross_joined(self):
        self.request("记录A的SYNTH-C1和记录B的SYNTH-C2在0到2秒计算PSD。")
        wrong = self.store.execute_action("psd", W, record="B")
        self.assertEqual(wrong["code"], "SCIENTIFIC_SCOPE_UNGROUNDED")
        self.assertFalse(self.store.entries)
        valid = self.store.execute_action("psd", {**W, "channels": ["SYNTH-C2"]}, record="B")
        self.assertTrue(valid["observation"]["result"]["success"])

    def test_new_explicit_record_after_full_interval_does_not_need_punctuation(self):
        self.request("记录A SYNTH-C1在0到2秒计算PSD以及记录B SYNTH-C1在2到4秒计算PSD。")
        bad = self.store.execute_action("psd", LATE, record="A", request_span="2到4秒")
        self.assertEqual(bad["code"], "RECORD_SCOPE_CONFLICT")
        for record, scope in (("A", W), ("B", LATE)):
            self.assertEqual(self.store.execute_action("psd", scope, record=record)["status"], "observed")
            self.assert_psd(self.store, record, scope)

    def test_source_keeps_full_parent_record_offsets_and_time_reference(self):
        text = "记录A的SYNTH-C1在0到2秒计算PSD；记录B的SYNTH-C1在2到4秒计算PSD。"
        self.request(text)
        self.store.execute_action("psd", LATE, record="B", request_span="2到4秒")
        sources = self.store.entries[0].tool_trace[0]["scientific_sources"]
        for source in sources.values():
            self.assertEqual(source["binding"]["record"], "B")
            self.assertEqual(source["binding"]["time_reference"], "record_absolute")
            for parent in source["binding"]["parents"]:
                self.assertEqual(parent["span"], text[parent["start"]:parent["end"]])
                self.assertIn("记录B", parent["span"])
                self.assertEqual(parent["allowed_records"], ["B"])
        json.dumps(sources, ensure_ascii=False, allow_nan=False)

    def test_multi_object_range_cross_product_cannot_be_licensed_by_crop(self):
        self.request("记录A SYNTH-C1在0到2秒PSD；SYNTH-C2在2到4秒PSD。")
        self.store.execute_action("psd", W, record="A")
        wrong = self.store.execute_action("psd", LATE, record="A", request_span="2到4秒")
        self.assertEqual(wrong["code"], "SCIENTIFIC_SCOPE_UNGROUNDED")
        self.assertEqual(len(self.store.entries), 1)
        legal_scope = {**LATE, "channels": ["SYNTH-C2"]}
        self.assertEqual(self.store.execute_action("psd", legal_scope, record="A")["status"], "observed")
        self.assert_psd(self.store, "A", legal_scope)

    def test_same_object_two_windows_in_one_clause_are_two_legal_results(self):
        self.request("记录A SYNTH-C1分别在0到2秒和2到4秒计算PSD。")
        for scope in (W, LATE):
            self.assertEqual(self.store.execute_action("psd", scope, record="A")["status"], "observed")
            self.assert_psd(self.store, "A", scope)
        self.assertEqual(len(self.store.entries), 2)

    def test_first_request_does_not_silently_choose_one_of_two_records(self):
        self.request("SYNTH-C1在0到2秒计算PSD。")
        out = self.store.execute_action("psd", W, record="A")
        self.assertEqual(out["code"], "AMBIGUOUS_RECORD_SOURCE")
        self.assertFalse(self.store.entries)
        self.request("使用记录A，SYNTH-C1在0到2秒。")
        self.assertEqual(self.store.execute_action("psd", W, record="A")["status"], "observed")

    def test_unambiguous_user_record_and_historical_object_can_continue(self):
        self.request("记录A SYNTH-C1在0到2秒RMS；stimulus事件窗稍后提供。")
        self.store.execute_action("amplitude", W, record="A")
        self.request("事件窗口为0到1秒，其他条件沿用。")
        out = self.store.execute_action("create_epochs", E, record="A")
        self.assertTrue(out["observation"]["result"]["success"])
        source = self.store.entries[-1].tool_trace[0]["scientific_sources"]
        self.assertEqual(source["labels"]["turn"], 1)
        self.assertEqual(source["tmax"]["binding"]["record"], "A")
        self.assertEqual(source["tmax"]["binding"]["time_reference"], "event_relative")

    def test_unique_historical_event_survives_other_records_continuous_mentions(self):
        # Root cause exposed by the exact three-turn offline protocol witness:
        # the prefix refers to the one user-specified event object, whereas B
        # occurs only in another raw-data task. No event action/pending card is
        # needed to make that real user request exist.
        self.request("请在记录A的SYNTH-C1、0到2秒同时给出RMS和alpha；记录B的SYNTH-C1只看2到4秒的RMS。"
                     "另外我想了解记录A中stimulus事件的SYNTH-C2 theta绝对功率，事件相对窗口我稍后提供。")
        self.store.execute_action("amplitude", W, record="A")
        self.store.execute_action("amplitude", LATE, record="B")
        self.request("事件相对窗口使用发生后0到1.25秒，其余条件不变。记录A的SYNTH-C1连续分析再看4到6秒的alpha绝对功率，"
                     "与第一次0到2秒比较差值和新旧比值，保留原结果；不要改动记录B的窗口。")
        out = self.store.execute_action("create_epochs", {**E, "tmax": 1.25}, record="A")
        self.assertTrue(out["observation"]["result"]["success"])
        self.assertEqual(out["observation"]["result"]["data"]["valid_epoch_count"], 3)
        sources = self.store.entries[-1].tool_trace[0]["scientific_sources"]
        self.assertEqual(sources["labels"]["record"], "A")
        self.assertEqual(sources["labels"]["turn"], 1)
        self.assertEqual(sources["tmax"]["span"], "事件相对窗口使用发生后0到1.25秒")

    def test_multiple_historical_event_objects_are_not_resolved_by_model_pending_or_other_family(self):
        for old_request in ("记录A stimulus事件窗口稍后；control事件窗口稍后。",
                            "记录A stimulus事件窗口稍后；记录B stimulus事件窗口稍后。"):
            with self.subTest(old_request=old_request):
                store = ScientificTaskStore("ambiguous-science", synthetic_records())
                self.request(old_request, store)
                store.execute_action("create_epochs", {"labels": ["stimulus"]}, record="A")
                self.request("事件窗口0到1秒，其余不变。记录A SYNTH-C1在4到6秒计算PSD。", store)
                out = store.execute_action("create_epochs", E, record="A")
                self.assertIn(out["code"], {"SCIENTIFIC_SCOPE_UNGROUNDED", "AMBIGUOUS_RECORD_SOURCE"})
                self.assertFalse(store.contexts["A"].artifacts)

    def test_ambiguous_prior_records_need_actual_inheritance_or_clarification(self):
        self.request("记录A SYNTH-C1在0到2秒PSD；记录B SYNTH-C1在0到2秒PSD。")
        self.store.execute_action("psd", W, record="A")
        a_result = self.store.entries[-1].task_id
        self.store.execute_action("psd", W, record="B")
        self.request("把窗口改成2到4秒，其他沿用。")
        unclear = self.store.execute_action("psd", LATE, record="A")
        self.assertEqual(unclear["code"], "AMBIGUOUS_RECORD_SOURCE")
        out = self.store.execute_action("psd", LATE, record="A", inherit_result=a_result)
        self.assertEqual(out["status"], "observed")
        self.assert_psd(self.store, "A", LATE)
        self.assertEqual(self.store.entries[-1].revision_of, a_result)

    def test_explicit_current_other_record_cannot_be_overridden_by_old_result(self):
        self.request("记录A SYNTH-C1在0到2秒PSD。")
        self.store.execute_action("psd", W, record="A")
        original = self.store.entries[-1].task_id
        self.request("记录B SYNTH-C1在2到4秒PSD。")
        bad = self.store.execute_action("psd", LATE, record="A", inherit_result=original,
                                        request_span="2到4秒")
        self.assertEqual(bad["code"], "RECORD_SCOPE_CONFLICT")
        self.assertEqual(len(self.store.entries), 1)

    def test_continuous_and_event_ranges_remain_separate_and_legal_branches_continue(self):
        self.request("记录A SYNTH-C1在0到2秒PSD；stimulus事件后0到1秒创建试次。")
        for name, arguments, crop in (("psd", {**W, "end": 1}, "0到1秒"),
                                       ("create_epochs", {**E, "tmax": 2}, "0到2秒")):
            self.assertEqual(self.store.execute_action(name, arguments, record="A",
                request_span=crop)["code"], "SCIENTIFIC_SCOPE_UNGROUNDED")
        self.assertFalse(self.store.entries)
        self.assertEqual(self.store.execute_action("psd", W, record="A")["status"], "observed")
        epochs = self.store.execute_action("create_epochs", E, record="A")
        self.assertTrue(epochs["observation"]["result"]["success"])
        self.assertEqual(epochs["observation"]["result"]["data"]["valid_epoch_count"], 3)

    def test_adjacent_object_then_window_is_bound_without_task_keyword_rules(self):
        self.request("记录A的stimulus事件，窗口0到1秒，测量质量并算频带功率。")
        out = self.store.execute_action("create_epochs", E, record="A")
        self.assertTrue(out["observation"]["result"]["success"])
        source = self.store.entries[-1].tool_trace[0]["scientific_sources"]["tmax"]
        self.assertEqual(source["span"], "记录A的stimulus事件，窗口0到1秒")
        self.assertEqual(source["binding"]["parents"][0]["record_basis"], "adjacent_object_and_interval")

    def test_adjacent_window_cannot_cross_another_object_or_finished_interval(self):
        for text in ("记录A stimulus，SYNTH-C1窗口0到2秒，0到1秒。",
                     "记录A stimulus后0到2秒，0到1秒。"):
            with self.subTest(text=text):
                store = ScientificTaskStore("local-ownership", synthetic_records())
                self.request(text, store)
                out = store.execute_action("create_epochs", E, record="A")
                self.assertEqual(out["code"], "SCIENTIFIC_SCOPE_UNGROUNDED")
                self.assertFalse(store.contexts["A"].artifacts)

    def test_artifact_inheritance_retains_actual_record_and_identity(self):
        self.request("记录A stimulus事件后0到1秒创建试次；记录B stimulus事件后0到1秒创建试次。")
        results = {}
        for record in ("A", "B"):
            self.store.execute_action("create_epochs", E, record=record)
            results[record] = self.store.entries[-1]
        self.request("沿原试次追加质量测量。")
        a = results["A"]
        artifact = a.evidence["binding"]["artifact_id"]
        good = self.store.execute_action("epoch_quality", {"artifact_id": artifact},
                                         record="A", inherit_result=a.task_id)
        self.assertEqual(good["status"], "observed")
        bad = self.store.execute_action("epoch_quality", {"artifact_id": artifact},
                                        record="B", inherit_result=results["B"].task_id)
        self.assertEqual(bad["code"], "ARTIFACT_NOT_FOUND")
        self.assertEqual(len(self.store.entries), 3)

    def test_metadata_derived_labels_are_not_fixed_test_vocabulary(self):
        records = synthetic_records()
        for record, eeg in records.items():
            events = EventSet(tuple(EEGEvent("pulse" if i % 2 else "rest", e.onset_seconds,
                                            source_index=i) for i, e in enumerate(eeg.events.events)),
                              "synthetic://different-event-labels")
            records[record] = replace(eeg, events=events)
        store = ScientificTaskStore("metadata-binding", records)
        self.request("record A SYNTH-C1 between 0 to 2 seconds; record B rest 0 to 1 seconds.", store)
        bad = store.execute_action("create_epochs", {"labels": ["rest"], "tmin": 0, "tmax": 1},
                                   record="A", request_span="rest 0 to 1 seconds")
        self.assertEqual(bad["code"], "RECORD_SCOPE_CONFLICT")
        legal = store.execute_action("create_epochs", {"labels": ["rest"], "tmin": 0, "tmax": 1}, record="B")
        self.assertTrue(legal["observation"]["result"]["success"])

    def test_declared_scope_cannot_supply_missing_scientific_authorization(self):
        self.request("记录A的stimulus事件需要分析，但窗口未给。")
        self.store.focus_task("模型提出的事件目的", "A", [{"tool": "create_epochs", "record": "A", "scope": E}])
        out = self.store.execute_action("create_epochs", E, record="A")
        self.assertEqual(out["code"], "SCIENTIFIC_SCOPE_UNGROUNDED")
        self.assertFalse(self.store.contexts["A"].artifacts)
        self.assertFalse(self.store.completion_check(self.store.active)["ready"])

    def test_partial_requirement_does_not_match_an_unadmitted_guess(self):
        self.request("记录A的stimulus事件需要分析，但窗口未给。")
        self.store.focus_task("待补事件目的", "A", [{"tool": "create_epochs", "record": "A", "scope": {"labels": ["stimulus"]}}])
        self.store.execute_action("create_epochs", E, record="A")
        check = self.store.completion_check(self.store.active)
        self.assertEqual(check["requirements"][0]["status"], "awaiting_parameter")
        self.assertIsNone(check["requirements"][0]["result_id"])
        self.assertFalse(self.store.entries)

    def test_record_alias_prefix_does_not_change_record_ownership(self):
        records = synthetic_records()
        store = ScientificTaskStore("record-boundary", {"A": records["A"], "A-long": records["B"]})
        self.request("record A-long SYNTH-C1 0 to 2 seconds PSD.", store)
        bad = store.execute_action("psd", W, record="A", request_span="SYNTH-C1 0 to 2 seconds")
        self.assertEqual(bad["code"], "RECORD_SCOPE_CONFLICT")
        self.assertFalse(store.entries)
        self.assertEqual(store.execute_action("psd", W, record="A-long")["status"], "observed")


if __name__ == "__main__":
    unittest.main()
