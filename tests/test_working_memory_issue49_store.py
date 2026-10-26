"""Issue49 common scientific contract and evidence reuse, real EEG tools."""
from dataclasses import replace
import json
import unittest

import numpy as np

from eeg_harness.events import create_epoch_set
from eeg_harness.research.task_memory import synthetic_records
from eeg_harness.tooling import ToolRequest
from eeg_harness.working_memory_lifecycle import ReliableWorkingMemoryStore


W = {"channels": ["SYNTH-C1"], "start": 0, "end": 2}
E = {"labels": ["stimulus"], "tmin": 0, "tmax": 1}


def item(key, tool, scope, **extra):
    return {"key": key, "tool": tool, "scope": scope, **extra}


def user(text, turn=1):
    return {"kind": "user", "turn": turn, "quote": text}


class Issue49StoreTest(unittest.TestCase):
    def setUp(self):
        self.s = ReliableWorkingMemoryStore("contract49", synthetic_records())
        self.request("记录A SYNTH-C1在0到2秒的幅值及功率；记录A stimulus事件后0到1秒功率，不做基线校正。")

    def request(self, text):
        self.s.turn += 1
        self.s.user_requests.append(text)

    def continuous(self, title="连续分析", key="p", **kwargs):
        return self.s.begin_subgoal(title, "A", deliveries=[item(key, "psd", W)],
            parameter_sources={key: user("记录A SYNTH-C1在0到2秒的幅值及功率")}, **kwargs)

    def test_real_baseline_transform_is_refused_on_begin_amend_and_execute(self):
        record = self.s.records["A"]
        constant = replace(record, data=np.ones_like(record.data))
        # The original numerical algorithm really changes scientific data.
        raw = create_epoch_set(constant, ["stimulus"], 0, 1)
        transformed = create_epoch_set(constant, ["stimulus"], 0, 1, [0, .5])
        self.assertEqual(float(raw.data.mean()), 1.0)
        self.assertEqual(float(transformed.data.mean()), 0.0)
        scope = dict(E, baseline=[0, .5])
        rejected = self.s.begin_subgoal("事件", "A", deliveries=[item("e", "create_epochs", scope)])
        self.assertEqual(rejected["code"], "INVALID_SCOPE")
        self.assertFalse(self.s.subgoals)
        self.s.begin_subgoal("事件", "A", deliveries=[item("e", "create_epochs", E)],
            parameter_sources={"e": user("记录A stimulus事件后0到1秒功率，不做基线校正")})
        before = json.dumps(self.s.goal_card(self.s.active), sort_keys=True)
        events = json.dumps(self.s.events, sort_keys=True)
        self.assertEqual(self.s.amend_subgoal("contract49-s1", updates={"e": {"baseline": [0, .5]}})["code"], "INVALID_SCOPE")
        self.assertEqual(json.dumps(self.s.goal_card(self.s.active), sort_keys=True), before)
        self.assertEqual(json.dumps(self.s.events, sort_keys=True), events)
        self.assertEqual(self.s.execute_numeric("create_epochs", scope)["code"], "INVALID_SCOPE")
        self.assertFalse(self.s.contexts["A"].artifacts)
        created = self.s.execute_numeric("create_epochs", E)
        self.assertTrue(created["observation"]["result"]["success"])
        artifact = self.s.contexts["A"].artifacts[created["observation"]["result"]["data"]["artifact_id"]]
        self.assertIsNone(artifact.baseline)

    def test_unknown_continuous_fields_and_types_use_same_atomic_contract(self):
        for extra in ({"reference": "average"}, {"baseline": [0, .5]}, {"start": True}):
            with self.subTest(extra=extra):
                s = ReliableWorkingMemoryStore("bad", synthetic_records())
                s.turn, s.user_requests = self.s.turn, list(self.s.user_requests)
                self.assertEqual(s.begin_subgoal("分析", "A", deliveries=[item("p", "psd", {**W, **extra})])["code"], "INVALID_SCOPE")
                s.begin_subgoal("分析", "A", deliveries=[item("p", "psd", W)], parameter_sources={"p": user("记录A SYNTH-C1在0到2秒的幅值及功率")})
                before = json.dumps(s.goal_card(s.active), sort_keys=True)
                rejected = s.amend_subgoal("bad-s1", updates={"p": extra})
                self.assertIn(rejected["code"], {"INVALID_SCOPE", "SCIENTIFIC_REVISION_REQUIRED"})
                self.assertEqual(json.dumps(s.goal_card(s.active), sort_keys=True), before)
                self.assertFalse(s.entries)

    def test_explicit_algorithm_parameter_needs_source_on_begin_and_amend(self):
        self.request("记录A SYNTH-C1在0到2秒进行质量测量。")
        scope = dict(W, line_frequency=60)
        result = self.s.begin_subgoal("质量", "A", deliveries=[item("q", "record_quality", scope)])
        self.assertEqual(result["status"], "awaiting_input")
        self.assertIn("line_frequency", [i["field"] for i in result["issues"]])
        self.assertEqual(self.s.execute_numeric("record_quality", scope)["code"], "SCIENTIFIC_PARAMETERS_UNCONFIRMED")
        self.request("记录A工频指定为60 Hz。")
        amended = self.s.amend_subgoal("contract49-s1", parameter_sources={"q": {"line_frequency": user("记录A工频指定为60 Hz", 3)}})
        self.assertEqual(amended["status"], "active")
        self.assertTrue(self.s.execute_numeric("record_quality", scope)["observation"]["result"]["success"])

    def test_completed_equivalence_ignores_title_key_and_dictionary_order(self):
        self.continuous()
        self.s.execute_numeric("psd", W)
        self.s.close_subgoal("completed")
        old = self.s.entries[0]
        again = self.continuous(title="另一个包装标题", key="renamed")
        self.assertEqual(again["status"], "reused_completed")
        self.assertEqual(again["subgoal_id"], "contract49-s1")
        self.assertEqual(self.s.last_owner, "contract49-s1")
        self.assertIsNone(self.s.active)
        self.assertEqual(len(self.s.subgoals), 1)
        self.assertIs(self.s.entries[0], old)
        direct = self.s.execute_numeric("psd", {"end": 2, "start": 0, "channels": ["SYNTH-C1"]},
            parameter_sources=user("记录A SYNTH-C1在0到2秒的幅值及功率"))
        self.assertEqual(direct["status"], "reused_completed")
        self.assertEqual(len(self.s.entries), 1)

    def test_extra_acceptance_condition_rechecks_same_result_without_recalculation(self):
        self.s.user_requests[0] += "记录A SYNTH-C1的alpha功率至少0。"
        self.continuous()
        self.s.execute_numeric("psd", W)
        self.s.close_subgoal("completed")
        criteria = [{"delivery": "checked", "path": ["SYNTH-C1", "alpha"], "op": "gte", "value": 0}]
        begun = self.s.begin_subgoal("检查实际结果", "A", deliveries=[item("checked", "psd", W)], criteria=criteria,
            parameter_sources={"checked": user("记录A SYNTH-C1在0到2秒的幅值及功率"),
                               "criteria": {"0": user("记录A SYNTH-C1的alpha功率至少0")}})
        self.assertEqual(begun["status"], "active")
        self.assertTrue(begun["progress"]["valid"])
        self.assertEqual(self.s.execute_numeric("psd", W)["status"], "reused")
        self.assertEqual(len(self.s.entries), 1)
        self.assertEqual(self.s.close_subgoal("completed")["status"], "completed")
        renamed = [{**criteria[0], "delivery": "another"}]
        reused = self.s.begin_subgoal("相同条件的新标题", "A", deliveries=[item("another", "psd", W)], criteria=renamed,
            parameter_sources={"another": user("记录A SYNTH-C1在0到2秒的幅值及功率"),
                               "criteria": {"0": user("记录A SYNTH-C1的alpha功率至少0")}})
        self.assertEqual(reused["status"], "reused_completed")
        self.assertEqual(len(self.s.entries), 1)

    def test_explicit_recompute_is_permitted_once_not_a_repeat_bypass(self):
        self.s.user_requests[0] += "请重新计算一次。"
        self.continuous()
        self.s.execute_numeric("psd", W)
        self.s.close_subgoal("completed")
        permission = user("请重新计算一次")
        self.assertEqual(self.continuous("显式重算", recompute_source=permission)["status"], "active")
        self.assertEqual(self.s.goal_card(self.s.active)["prior_equivalent_results"], {"p": ["contract49-t1"]})
        fresh = self.s.execute_numeric("psd", W)
        self.assertEqual(fresh["status"], "observed")
        self.assertEqual(len(self.s.entries), 2)
        self.assertEqual(self.s.execute_numeric("psd", W)["status"], "reused")
        self.s.close_subgoal("completed")
        self.assertEqual(self.continuous("再换标题", recompute_source=permission)["status"], "reused_completed")
        self.assertEqual(len(self.s.entries), 2)

    def test_recompute_cannot_be_granted_by_negated_or_unrelated_quote(self):
        self.s.user_requests[0] += "不需要重新计算。"
        for quote in ("重新计算", "记录A SYNTH-C1在0到2秒的幅值及功率"):
            self.assertEqual(self.continuous(recompute_source=user(quote))["code"], "UNVERIFIED_RECOMPUTATION")
        self.assertFalse(self.s.subgoals)

    def test_changed_window_revision_and_changed_config_produce_fresh_results(self):
        self.continuous()
        self.s.execute_numeric("psd", W)
        self.s.close_subgoal("completed")
        old = self.s.entries[0]
        self.s.contexts["A"].executor.config["freq_bands"]["alpha"] = [9, 11]
        self.assertFalse(self.s._binding_valid(old))
        self.assertEqual(self.continuous("新配置")["status"], "active")
        self.assertEqual(self.s.execute_numeric("psd", W)["status"], "observed")
        self.s.close_subgoal("completed")
        self.request("记录A SYNTH-C1分析窗口改为2到4秒。")
        scope = dict(W, start=2, end=4)
        self.s.begin_subgoal("新窗口", "A", deliveries=[item("p", "psd", scope, revision_of=old.task_id)])
        self.assertEqual(self.s.execute_numeric("psd", scope)["status"], "observed")
        self.assertEqual(self.s.entries[-1].revision_of, old.task_id)
        self.assertIs(self.s.entries[0], old)
        self.assertEqual(len(self.s.entries), 3)

    def test_automatic_archive_feedback_does_not_request_another_close(self):
        result = self.s.execute_numeric("record_info", {})
        self.assertEqual(result["archive"]["status"], "completed")
        self.assertIsNone(self.s.active)
        self.assertIn("Already archived", result["next_action"])
        again = self.s.execute_numeric("record_info", {})
        self.assertEqual(again["status"], "reused_completed")
        self.assertEqual(len(self.s.entries), 1)
        other = self.s.execute_numeric("record_info", {}, record="B")
        self.assertEqual(other["observation"]["record"], "B")
        self.assertEqual(len(self.s.entries), 2)

    def test_changed_record_samples_invalidate_old_equivalent_binding(self):
        self.continuous()
        self.s.execute_numeric("psd", W)
        self.s.close_subgoal("completed")
        old = self.s.entries[0]
        original_value = float(old.result["SYNTH-C1"]["alpha"])
        context = self.s.contexts["A"]
        context.record = replace(context.record, data=context.record.data * 2)
        self.assertFalse(self.s._binding_valid(old))
        self.assertEqual(self.continuous("更新后的数据")["status"], "active")
        out = self.s.execute_numeric("psd", W)
        self.assertEqual(out["status"], "observed")
        self.assertAlmostEqual(float(self.s.entries[-1].result["SYNTH-C1"]["alpha"]), 4 * original_value, delta=1e-15)
        self.assertEqual(float(old.result["SYNTH-C1"]["alpha"]), original_value)

    def test_identical_content_epoch_is_not_the_declared_original_artifact(self):
        self.s.begin_subgoal("原试次", "A", deliveries=[item("e", "create_epochs", E)],
            parameter_sources={"e": user("记录A stimulus事件后0到1秒功率，不做基线校正")})
        original = self.s.execute_numeric("create_epochs", E)["observation"]
        self.s.close_subgoal("completed")
        context = self.s.contexts["A"]
        second = context.execute(ToolRequest("create_epochs", E, "independent-object"))
        first_id, second_id = original["result"]["data"]["artifact_id"], second.data["artifact_id"]
        self.assertNotEqual(first_id, second_id)
        self.assertEqual(context.artifacts[first_id].content_fingerprint(), context.artifacts[second_id].content_fingerprint())
        self.s.begin_subgoal("原试次质量", "A", deliveries=[item("q", "epoch_quality", E)], dependencies=["contract49-t1"],
            parameter_sources={"q": {"kind": "result", "result_id": "contract49-t1"}})
        wrong = self.s.execute_numeric("epoch_quality", {"artifact_id": second_id})
        self.assertEqual(wrong["observation"]["result"]["error"]["code"], "ARTIFACT_IDENTITY_MISMATCH")
        correct = self.s.execute_numeric("epoch_quality", {"artifact_id": first_id})
        self.assertTrue(correct["observation"]["result"]["success"])
        self.assertEqual(self.s.entries[-1].evidence["binding"]["artifact_id"], first_id)

    def test_original_binding_rejects_incidental_rebuild_but_allows_new_scope(self):
        self.s.begin_subgoal("原试次", "A", deliveries=[item("e", "create_epochs", E)],
            parameter_sources={"e": user("记录A stimulus事件后0到1秒功率，不做基线校正")})
        first = self.s.execute_numeric("create_epochs", E)["observation"]
        self.s.close_subgoal("completed")
        first_id = first["result"]["data"]["artifact_id"]
        self.request("沿用刚才的原试次测量质量，不重建。")
        self.s.begin_subgoal("原质量", "A", deliveries=[item("q", "epoch_quality", E)],
            dependencies=["contract49-t1"], parameter_sources={"q": {"kind": "artifact", "artifact_id": first_id}})
        blocked = self.s.execute_numeric("create_epochs", E)
        self.assertEqual(blocked["observation"]["result"]["error"]["code"], "ORIGINAL_ARTIFACT_ALREADY_BOUND")
        self.assertEqual(len(self.s.contexts["A"].artifacts), 1)
        self.assertTrue(self.s.execute_numeric("epoch_quality", {"artifact_id": first_id})["observation"]["result"]["success"])
        self.s.close_subgoal("completed")
        self.request("记录A stimulus事件后0到1.5秒测量质量。")
        scope = dict(E, tmax=1.5)
        begun = self.s.begin_subgoal("新科学窗口", "A", deliveries=[item("q", "epoch_quality", scope)],
            dependencies=["contract49-t1"], parameter_sources={"q": user(self.s.user_requests[-1], 3)})
        self.assertEqual(begun["status"], "active")
        new = self.s.execute_numeric("create_epochs", scope)["observation"]
        self.assertTrue(new["result"]["success"])
        new_id = new["result"]["data"]["artifact_id"]
        self.assertNotEqual(new_id, first_id)
        self.assertTrue(self.s.execute_numeric("epoch_quality", {"artifact_id": new_id})["observation"]["result"]["success"])
        self.assertTrue(self.s.completion_check(self.s.active)["valid"])

    def test_explicit_declared_epoch_rebuild_rebinds_once_and_later_user_can_repeat(self):
        self.s.begin_subgoal("原试次", "A", deliveries=[item("e", "create_epochs", E)],
            parameter_sources={"e": user("记录A stimulus事件后0到1秒功率，不做基线校正")})
        first = self.s.execute_numeric("create_epochs", E)["observation"]
        self.s.close_subgoal("completed")
        first_id, old_result = first["result"]["data"]["artifact_id"], "contract49-t1"
        for turn in (2, 3):
            self.request("记录A stimulus事件后0到1秒重新计算试次和质量。")
            permission = user(self.s.user_requests[-1], turn)
            begun = self.s.begin_subgoal("授权重建", "A", deliveries=[item("e", "create_epochs", E, revision_of=old_result),
                item("q", "epoch_quality", E)], dependencies=[old_result], recompute_source=permission,
                parameter_sources={"e": permission, "q": permission})
            self.assertEqual(begun["status"], "active")
            created = self.s.execute_numeric("create_epochs", E)["observation"]
            self.assertTrue(created["result"]["success"])
            new_id = created["result"]["data"]["artifact_id"]
            self.assertNotEqual(new_id, first_id)
            measured = self.s.execute_numeric("epoch_quality", {"artifact_id": new_id})
            self.assertTrue(measured["observation"]["result"]["success"])
            self.assertTrue(self.s.completion_check(self.s.active)["valid"])
            blocked = self.s.execute_numeric("create_epochs", E)
            self.assertEqual(blocked["observation"]["result"]["error"]["code"], "ORIGINAL_ARTIFACT_ALREADY_BOUND")
            # The failed repeated required action stays visible. Explicitly
            # acknowledge its already valid result instead of deleting failure
            # or recomputing. The legitimate rebuild/measurement above has
            # already proved valid before exercising this recovery branch.
            self.assertFalse(self.s.completion_check(self.s.active)["valid"])
            self.assertEqual(self.s.reuse_result("e", created["result_id"])["status"], "reused")
            self.assertTrue(self.s.completion_check(self.s.active)["valid"])
            self.s.close_subgoal("completed")
            first_id, old_result = new_id, created["result_id"]


if __name__ == "__main__":
    unittest.main()
