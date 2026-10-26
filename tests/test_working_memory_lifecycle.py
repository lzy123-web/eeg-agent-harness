"""Actual tools and state/source contracts, without paid model calls."""
from dataclasses import replace
import json
import unittest

from eeg_harness.events import EventSet
from eeg_harness.research.task_memory import synthetic_records
from eeg_harness.working_memory_lifecycle import ReliableWorkingMemoryStore, field_contract


W = {"channels": ["SYNTH-C1"], "start": 0, "end": 2}
E = {"labels": ["stimulus"], "tmin": 0, "tmax": 1}


def item(key, tool, scope, **extra):
    return {"key": key, "tool": tool, "scope": scope, **extra}


def user(quote, turn=1):
    return {"kind": "user", "quote": quote, "turn": turn}


class LifecycleTest(unittest.TestCase):
    def setUp(self):
        self.s = ReliableWorkingMemoryStore("life", synthetic_records())
        self.request("记录A SYNTH-C1 在0到2秒的幅值及功率；stimulus事件后0到1秒功率。")

    def request(self, text):
        self.s.user_requests.append(text)
        self.s.turn += 1

    def test_real_field_contracts_are_tool_specific(self):
        r = self.s.records["A"]
        self.assertEqual(field_contract("list_events", ["labels", "stimulus"], r, {}, self.s.config), "integer")
        self.assertIsNone(field_contract("list_events", ["stimulus"], r, {}, self.s.config))
        self.assertIsNone(field_contract("record_info", ["valid_epoch_count"], r, {}, self.s.config))
        self.assertIsNone(field_contract("epoch_summary", ["duration_seconds"], r, {}, self.s.config))
        self.assertIsNone(field_contract("psd", ["SYNTH-C10", "alpha"], r, W, self.s.config))

    def test_condition_path_type_and_unrequested_minimum_refused(self):
        ds = [item("n", "list_events", {})]
        c = {"delivery": "n", "path": ["stimulus"], "op": "gte", "value": 1}
        self.assertEqual(self.s.begin_subgoal("events", "A", deliveries=ds, criteria=[c])["code"], "UNKNOWN_RESULT_FIELD")
        c["path"], c["value"] = ["labels", "stimulus"], "one"
        self.assertEqual(self.s.begin_subgoal("events", "A", deliveries=ds, criteria=[c])["code"], "CRITERION_TYPE_MISMATCH")
        c["value"] = 1
        self.assertEqual(self.s.begin_subgoal("events", "A", deliveries=ds, criteria=[c])["code"], "UNGROUNDED_CRITERION")
        self.assertFalse(self.s.subgoals)

    def test_real_unmet_condition_distinct_and_cannot_relax(self):
        self.request("记录A事件总数至少99。")
        c = {"delivery": "n", "path": ["event_count"], "op": "gte", "value": 99}
        begun = self.s.begin_subgoal("检查实际事件总数", "A", deliveries=[item("n", "list_events", {})], criteria=[c],
            parameter_sources={"criteria": {"0": user(self.s.user_requests[-1], 2)}})
        self.assertEqual(begun["status"], "active")
        self.s.execute_numeric("list_events", {})
        self.assertEqual(self.s.completion_check(self.s.active)["code"], "DATA_CONDITION_NOT_MET")
        self.assertEqual(self.s.amend_subgoal("life-s1", criterion_paths={"0": ["labels", "stimulus"]})["code"], "NOT_TECHNICAL_CORRECTION")
        self.assertEqual(self.s.active.criteria[0]["value"], 99)

    def test_technical_path_repair_retains_actual_result_and_threshold(self):
        self.request("记录A的stimulus事件至少3个。")
        c = {"delivery": "n", "path": ["labels", "stimulus"], "op": "gte", "value": 3}
        self.s.begin_subgoal("事件条件", "A", deliveries=[item("n", "list_events", {})], criteria=[c],
            parameter_sources={"criteria": {"0": user(self.s.user_requests[-1], 2)}})
        self.s.execute_numeric("list_events", {})
        entry = self.s.entries[0]
        # Represents an already-stored legacy/malformed declaration, not a new
        # admission bypass: new declarations reject this path before execution.
        self.s.active.criteria[0]["path"] = ["stimulus"]
        self.assertEqual(self.s.completion_check(self.s.active)["code"], "UNKNOWN_RESULT_FIELD")
        amended = self.s.amend_subgoal("life-s1", criterion_paths={"0": ["labels", "stimulus"]})
        self.assertTrue(amended["progress"]["valid"])
        self.assertIs(self.s.entries[0], entry)
        self.assertEqual(len(self.s.entries), 1)
        self.assertEqual(self.s.active.criteria[0]["value"], 3)
        self.assertEqual(self.s.close_subgoal("completed")["status"], "completed")

    def test_zero_event_count_is_valid_delivery_without_invented_threshold(self):
        records = synthetic_records()
        records["A"] = replace(records["A"], events=EventSet((), "synthetic://empty-events"))
        s = ReliableWorkingMemoryStore("empty", records)
        out = s.execute_numeric("list_events", {})
        self.assertEqual(out["archive"]["status"], "completed")
        self.assertEqual(s.entries[0].result["event_count"], 0)

    def test_continuous_clarification_fills_window_keeps_known_channel(self):
        self.request("记录A SYNTH-C1的功率。")
        result = self.s.begin_subgoal("功率", "A", deliveries=[item("p", "psd", {"channels": ["SYNTH-C1"]})])
        self.assertEqual(result["status"], "awaiting_input")
        self.assertEqual({i["field"] for i in result["issues"]}, {"start", "end"})
        self.assertEqual(self.s.execute_numeric("psd", W)["code"], "SCIENTIFIC_PARAMETERS_UNCONFIRMED")
        self.assertFalse(self.s.entries)
        self.request("使用0到2秒。")
        result = self.s.amend_subgoal("life-s1", updates={"p": {"start": 0, "end": 2}})
        self.assertEqual(result["status"], "active", result)
        self.assertEqual(len(self.s.subgoals), 1)
        self.s.execute_numeric("psd", W)
        self.assertEqual(self.s.close_subgoal("completed")["status"], "completed")

    def test_event_clarification_same_object_then_artifact_continuation(self):
        self.request("记录A的stimulus事件功率。")
        result = self.s.begin_subgoal("事件功率", "A", deliveries=[item("p", "event_bandpower", {"labels": ["stimulus"]})])
        self.assertEqual(result["status"], "awaiting_input")
        self.assertEqual(self.s.execute_numeric("create_epochs", E)["code"], "SCIENTIFIC_PARAMETERS_UNCONFIRMED")
        self.request("事件后0到1秒。")
        self.assertEqual(self.s.amend_subgoal("life-s1", updates={"p": {"tmin": 0, "tmax": 1}})["status"], "active")
        created = self.s.execute_numeric("create_epochs", E)["observation"]["result"]["data"]
        args = {"artifact_id": created["artifact_id"], "expected_artifact_fingerprint": created["artifact_fingerprint"]}
        self.s.execute_numeric("event_bandpower", args)
        self.s.close_subgoal("completed")
        old_count = len(self.s.entries)
        self.request("在刚才的同一批事件试次上测量质量。")
        restored = self.s.restore_subgoal("life-s1")
        self.assertEqual(restored["action_observations"][0]["result"]["data"]["artifact_id"], args["artifact_id"])
        started = self.s.begin_subgoal("原工件质量", "A", deliveries=[item("q", "epoch_quality", E)],
            parameter_sources={"q": {"kind": "artifact", "artifact_id": args["artifact_id"]}})
        self.assertEqual(started["status"], "active")
        self.s.execute_numeric("epoch_quality", args)
        self.assertEqual(self.s.close_subgoal("completed")["status"], "completed")
        self.assertEqual(len(self.s.entries), old_count+1)
        self.assertEqual(len(self.s.contexts["A"].artifacts), 1)

    def test_guessed_scope_is_pending_not_numerically_executed(self):
        self.request("比较两个条件的事件频带功率。")
        result = self.s.begin_subgoal("比较", "A", deliveries=[item("p", "event_bandpower", {"labels": ["stimulus"], "tmin": -.5, "tmax": .5})])
        self.assertEqual(result["status"], "awaiting_input")
        self.assertEqual(self.s.execute_numeric("create_epochs", {"labels": ["stimulus"], "tmin": -.5, "tmax": .5})["code"], "SCIENTIFIC_PARAMETERS_UNCONFIRMED")
        self.assertFalse(self.s.contexts["A"].artifacts)

    def test_quote_wrong_record_clipped_record_and_substring_rejected(self):
        self.request("记录A SYNTH-C1 0到2秒；记录B SYNTH-C1 3到5秒。")
        bad = {"channels": ["SYNTH-C1"], "start": 3, "end": 5}
        result = self.s.begin_subgoal("错对象", "A", deliveries=[item("p", "psd", bad)],
            parameter_sources={"p": user("记录B SYNTH-C1 3到5秒", 2)})
        self.assertEqual(result["status"], "awaiting_input")
        self.s.active = None
        result = self.s.begin_subgoal("裁剪掉对象", "A", deliveries=[item("p", "psd", bad)],
            parameter_sources={"p": {"fields": {"channels": user("SYNTH-C1", 2), "start": user("3到5秒", 2), "end": user("3到5秒", 2)}}})
        self.assertEqual(result["status"], "awaiting_input")
        self.s.active = None
        self.request("记录A SYNTH-C10 0到2秒。")
        result = self.s.begin_subgoal("子串", "A", deliveries=[item("p", "psd", W)])
        self.assertTrue(any(i["field"] == "channels" for i in result["issues"]))

    def test_range_order_and_multiple_ranges_not_mere_scalar_occurrence(self):
        self.request("记录A SYNTH-C1 0到2秒和3到5秒。")
        wrong = dict(W, end=5)
        result = self.s.begin_subgoal("拼错范围", "A", deliveries=[item("p", "psd", wrong)])
        self.assertEqual(result["status"], "awaiting_input")
        self.s.active = None
        good = self.s.begin_subgoal("明确范围", "A", deliveries=[item("p", "psd", W)],
            parameter_sources={"p": user("记录A SYNTH-C1 0到2秒", 2)})
        self.assertEqual(good["status"], "active")

    def test_idempotent_pending_and_already_auto_linked_result(self):
        quote = "记录A SYNTH-C1 在0到2秒的幅值及功率"
        args = dict(deliveries=[item("p", "psd", W)], parameter_sources={"p": user(quote)})
        first = self.s.begin_subgoal("功率", "A", **args)
        again = self.s.begin_subgoal("功率", "A", **args)
        self.assertEqual(first["subgoal_id"], again["subgoal_id"])
        self.assertEqual(again["status"], "unchanged")
        self.s.execute_numeric("psd", W)
        count = len(self.s.events)
        self.assertEqual(self.s.reuse_result("p", "life-t1")["status"], "unchanged")
        self.assertEqual(len(self.s.events), count)
        self.assertEqual(len(self.s.entries), 1)

    def test_confirmed_scientific_revision_retains_old_result(self):
        source = user("记录A SYNTH-C1 在0到2秒的幅值及功率")
        self.s.begin_subgoal("原功率", "A", deliveries=[item("p", "psd", W)], parameter_sources={"p": source})
        self.s.execute_numeric("psd", W)
        self.assertEqual(self.s.amend_subgoal("life-s1", updates={"p": {"end": 3}})["code"], "SCIENTIFIC_REVISION_REQUIRED")
        self.s.close_subgoal("completed")
        old = self.s.entries[0]
        self.request("记录A SYNTH-C1改为0到3秒，并比较原值。")
        new = dict(W, end=3)
        self.s.begin_subgoal("修订", "A", deliveries=[item("p", "psd", new, revision_of=old.task_id)])
        self.s.execute_numeric("psd", new)
        self.assertEqual(self.s.entries[1].revision_of, old.task_id)
        self.assertIs(self.s.entries[0], old)

    def test_wrong_record_prior_result_cannot_ground_scope(self):
        self.s.execute_numeric("psd", W, parameter_sources=user("记录A SYNTH-C1 在0到2秒的幅值及功率"))
        self.request("记录B需要同样分析。")
        result = self.s.begin_subgoal("B功率", "B", deliveries=[item("p", "psd", W)],
            parameter_sources={"p": {"kind": "result", "result_id": "life-t1"}})
        self.assertEqual(result["status"], "awaiting_input")
        self.assertTrue(any(i["code"] == "UNVERIFIED_PARAMETER_SOURCE" for i in result["issues"]))

    def test_metadata_record_wrapper_is_real_selected_record(self):
        result = self.s.execute_numeric("record_info", {}, record="B")
        self.assertEqual(result["archive"]["status"], "completed")
        self.assertEqual(self.s.entries[0].record, "B")
        self.assertEqual(self.s.entries[0].evidence["source"], self.s.records["B"].source)
        json.dumps(result, allow_nan=False)

    def test_record_selection_issue_is_not_erased_by_window_supplement(self):
        begun = self.s.begin_subgoal("B功率", "B", deliveries=[item("p", "psd", {"channels": ["SYNTH-C1"]})])
        self.assertTrue(any(i["code"] == "UNVERIFIED_RECORD_SELECTION" for i in begun["issues"]))
        self.request("使用0到2秒。")
        amended = self.s.amend_subgoal("life-s1", updates={"p": {"start": 0, "end": 2}})
        self.assertTrue(any(i["code"] == "UNVERIFIED_RECORD_SELECTION" for i in amended["contract"]["admission_issues"]))
        self.assertEqual(amended["status"], "awaiting_input")

    def test_missing_actual_field_and_bad_value_differ_from_true_condition(self):
        self.request("记录A事件至少1个。")
        self.s.begin_subgoal("计数", "A", deliveries=[item("n", "list_events", {})],
            criteria=[{"delivery": "n", "path": ["event_count"], "op": "gte", "value": 1}],
            parameter_sources={"criteria": {"0": user(self.s.user_requests[-1], 2)}})
        self.s.execute_numeric("list_events", {})
        data = self.s.entries[0].result
        data["event_count"] = "corrupted"
        self.assertEqual(self.s.completion_check(self.s.active)["code"], "RESULT_FIELD_TYPE_MISMATCH")
        del data["event_count"]
        self.assertEqual(self.s.completion_check(self.s.active)["code"], "RESULT_FIELD_ABSENT")

    def test_technical_path_expansion_must_be_unique(self):
        self.request("记录A SYNTH-C1和SYNTH-C2在0到2秒；SYNTH-C1 rms至少0。")
        scope = dict(W, channels=["SYNTH-C1", "SYNTH-C2"])
        self.s.begin_subgoal("双通道幅值", "A", deliveries=[item("a", "amplitude", scope)],
            criteria=[{"delivery": "a", "path": ["SYNTH-C1", "rms"], "op": "gte", "value": 0}],
            parameter_sources={"criteria": {"0": user("SYNTH-C1 rms至少0", 2)}})
        self.s.execute_numeric("amplitude", scope)
        self.s.active.criteria[0]["path"] = ["rms"]
        self.assertEqual(self.s.amend_subgoal("life-s1", criterion_paths={"0": ["SYNTH-C1", "rms"]})["code"], "NOT_TECHNICAL_CORRECTION")
        self.assertEqual(len(self.s.entries), 1)

    def test_criterion_operator_not_silently_changed(self):
        self.request("记录A事件总数>=1。")
        result = self.s.begin_subgoal("计数", "A", deliveries=[item("n", "list_events", {})],
            criteria=[{"delivery": "n", "path": ["event_count"], "op": "eq", "value": 1}],
            parameter_sources={"criteria": {"0": user(self.s.user_requests[-1], 2)}})
        self.assertEqual(result["code"], "UNGROUNDED_CRITERION")


if __name__ == "__main__":
    unittest.main()
