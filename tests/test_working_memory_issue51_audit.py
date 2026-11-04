"""Read-only audit is not a success oracle and never upgrades indexes to facts."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from eeg_harness.research import working_memory_issue51 as stage
from eeg_harness.research import working_memory_issue51_audit as audit


def request(value):
    return {"messages":[{"role":"user","content":json.dumps(value)}]}


class EvidenceExposureTest(unittest.TestCase):
    def test_restore_ack_is_not_the_restored_process(self):
        ack={"success":True,"data":{"status":"restored","subgoal_id":"g1","action_observation_count":1}}
        self.assertEqual(audit.restored_processes_in_request(request(ack)),[])
        process={"subgoal":{"subgoal_id":"g1"},"action_observations":[{
            "record":"A","source":"synthetic://A","scope":{"labels":["event"]},
            "request":{"name":"event_bandpower","arguments":{"artifact_id":"epochs-real"}},
            "result":{"success":True,"data":{"artifact_id":"epochs-real"}}}]}
        visible=audit.restored_processes_in_request(request({"restored_trajectories":[process]}))
        self.assertEqual(visible[0]["artifact_ids"],["epochs-real"])
        self.assertEqual(visible[0]["observation_count"],1)
        self.assertEqual(audit.restored_processes_in_request(request({"success":False,"data":process})),[])

    def test_native_quantity_evidence_unit_conversion_is_visible_and_checkable(self):
        field={"path":["C1","alpha"],"value":2e-10,"semantics":{"unit":"V²"},
            "canonical_display":"2e-10 V²","scaled_display":"200 µV²"}
        value={"success":True,"data":{"quantity_evidence":{"task_id":"result-one","fields":[field]}}}
        rows=audit.quantity_displays_in_request(request(value))
        self.assertEqual(len(rows),1)
        self.assertTrue(rows[0]["canonical_display_valid"])
        self.assertTrue(rows[0]["scaled_display_valid"])
        self.assertEqual(rows[0]["expected_scaled_value"],200)
        field["scaled_display"]="0.200 µV²"
        self.assertFalse(audit.quantity_displays_in_request(request(value))[0]["scaled_display_valid"])

    def test_display_audit_never_promotes_failed_results_or_free_prose(self):
        value={"success":False,"data":{"task_id":"x","fields":[{
            "path":["C1","rms"],"value":1e-5,"semantics":{"unit":"V"},
            "canonical_display":"1e-5 V","scaled_display":"10 µV"}]}}
        self.assertEqual(audit.quantity_displays_in_request(request(value)),[])
        self.assertEqual(audit.quantity_displays_in_request({"messages":[{"role":"assistant","content":"200 µV²"}]}),[])

    def test_index_and_failed_reads_do_not_count_as_values(self):
        value={"index":{"task_id":"old","readable_fields":[["C1","rms"]]},
               "failed":{"success":False,"data":{"evidence":{"task_id":"old","fields":[{"path":["C1","rms"],"value":99}]}}}}
        facts, conflicts=audit.evidence_in_request(request(value))
        self.assertEqual(facts,{})
        self.assertEqual(conflicts,[])

    def test_native_success_and_compact_fields_merge_without_replacing_values(self):
        value={"native":{"result_id":"old","result":{"success":True,"data":{"C1":{"rms":2.5}}}},
               "compact":{"task_id":"old","fields":[{"path":["C1","mean"],"value":0.0}]}}
        facts, conflicts=audit.evidence_in_request(request(value))
        self.assertEqual(len(facts["old"]),2)
        self.assertTrue(audit._fields_present(facts,"old",[{"path":["C1","rms"],"value":2.5}]))
        self.assertFalse(audit._fields_present(facts,"old",[{"path":["C1","rms"],"value":25}]))
        self.assertEqual(conflicts,[])

    def test_conflicting_values_are_visible_as_audit_problem(self):
        value=[{"task_id":"old","fields":[{"path":["x"],"value":1}]},
               {"task_id":"old","fields":[{"path":["x"],"value":2}]}]
        _, conflicts=audit.evidence_in_request(request(value))
        self.assertEqual(conflicts,[{"result_id":"old","path":["x"]}])

    def test_empty_requested_fields_never_count_as_read_success(self):
        self.assertFalse(audit._fields_present({},"unknown",[]))


class AuditTest(unittest.TestCase):
    def _fixture(self,root):
        directory=root/"offline-fixture";directory.mkdir()
        agent=stage.build_agent(None,"scientific-full","audit-fixture")
        seeded=stage.controlled_history(agent)
        observed=next(a["result"] for a in seeded["actions"] if a["tool"]=="amplitude")
        records=stage.records_for()
        spec=stage.protocol()
        manifest={"phase":"confirmation","arm":"scientific-full","candidate_commit":"fixture",
            "protocol_sha256":hashlib.sha256(json.dumps(spec,ensure_ascii=False).encode("utf8")).hexdigest(),"model_requested":"offline-test","model_settings":{},
            "protocol_content_sha256":stage.digest(spec),
            "data_sha256":{alias:hashlib.sha256(record.data.tobytes()).hexdigest() for alias,record in records.items()}}
        turn={"stop_reason":"completed","rounds":1,"tool_calls":1,
            "final_answer":"故意不完整的测试回答；completed不可等于科学验收通过。",
            "tool_results":[observed],"working_memory":{}}
        for name,data in (("manifest.json",manifest),("protocol.json",spec),("turn-1.json",turn)):
            (directory/name).write_text(json.dumps(data,ensure_ascii=False),encoding="utf8")
        req={"request_id":"request-one","context":{"turn":1},**request({"current_request":spec["development"]["requests"][0]})}
        resp={"raw_assistant_message":{"tool_calls":[{"id":observed["request_id"],"function":{"name":"amplitude","arguments":json.dumps({"channels":["SYNTH-C1"],"start":0,"end":2})}}]}}
        for name,row in (("requests.jsonl",req),("responses.jsonl",resp)):
            (directory/name).write_text(json.dumps(row,ensure_ascii=False)+"\n",encoding="utf8")
        ledger=[{"event":"opened","stage":"issue51"},
            {"event":"reserved","request_id":"request-one","context":{"run_id":"offline-fixture"},"reserved_tokens":200},
            {"event":"received","request_id":"request-one","total_tokens":150,
             "usage":{"prompt_tokens":110,"completion_tokens":40},"response_model_reported":"offline-test"}]
        (root/"budget.jsonl").write_text("\n".join(json.dumps(row) for row in ledger)+"\n",encoding="utf8")
        return directory

    def test_real_tool_number_check_does_not_award_completed_task_success(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self._fixture(root)
            value=audit.build_audit(root)
            run=value["runs"][0]
            self.assertEqual(len(run["numeric_checks"]),1)
            self.assertTrue(run["numeric_checks"][0]["numeric_valid"])
            self.assertEqual(run["turns"][0]["stop_reason"],"completed")
            self.assertIn("REQUIRED",run["turns"][0]["semantic_review"])
            self.assertNotIn("success_rate",value)
            self.assertEqual(value["cost_total"]["api_input_tokens"],110)
            self.assertEqual(value["cost_total"]["api_output_tokens"],40)
            self.assertEqual(value["cost_total"]["charged_tokens"],150)
            self.assertEqual(run["restore_chains"],[])
            self.assertNotIn(str(root),json.dumps(value))

    def test_changed_data_cannot_relabel_old_results(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);directory=self._fixture(root)
            manifest=audit.read_json(directory/"manifest.json")
            manifest["data_sha256"]["A"]="different"
            (directory/"manifest.json").write_text(json.dumps(manifest),encoding="utf8")
            with self.assertRaises(ValueError):audit.audit_run(directory)

    def test_restore_ack_links_to_actual_next_input_then_real_quality_operation(self):
        with tempfile.TemporaryDirectory() as d:
            directory=self._fixture(Path(d))
            agent=stage.build_agent(None,"scientific-working","audit-restore")
            history=stage.controlled_history(agent,capture_views=True)
            restore=next(a for a in history["actions"] if a["tool"] == "restore_task")
            quality=next(a for a in history["actions"] if a["tool"] == "epoch_quality")
            self.assertNotIn("action_observations",restore["result"]["data"])
            turn=audit.read_json(directory/"turn-1.json")
            turn["tool_results"]=[restore["result"],quality["result"]]
            (directory/"turn-1.json").write_text(json.dumps(turn),encoding="utf8")
            inputs=[{"request_id":"r1","context":{"turn":1},**request({"current_request":"fixture"})},
                {"request_id":"r2","context":{"turn":1},**request({"restored_trajectories":list(agent.working_memory.restored.values())})}]
            outputs=[{"raw_assistant_message":{"tool_calls":[{"id":a["result"]["request_id"],"function":{
                "name":a["tool"],"arguments":json.dumps(a["arguments"])}}]}} for a in (restore,quality)]
            for name,rows in (("requests.jsonl",inputs),("responses.jsonl",outputs)):
                (directory/name).write_text("\n".join(json.dumps(row) for row in rows)+"\n",encoding="utf8")
            chain=audit.audit_run(directory)["restore_chains"][0]
            self.assertFalse(chain["reply_contains_process"])
            self.assertEqual(chain["visible_in_later_inputs"],[2])
            self.assertTrue(chain["temporal_exposure_then_execution"])
            self.assertEqual(chain["subsequent_real_same_artifact_execution"][0]["tool"],"epoch_quality")
            # Same successful acknowledgement and operation without a real
            # process in the intervening model input is not process exposure.
            inputs[1]=dict(inputs[1],**request({"restore_ack":restore["result"]["data"]}))
            (directory/"requests.jsonl").write_text("\n".join(json.dumps(row) for row in inputs)+"\n",encoding="utf8")
            chain=audit.audit_run(directory)["restore_chains"][0]
            self.assertFalse(chain["temporal_exposure_then_execution"])

    def test_minimal_focus_reply_retains_actual_accepted_model_grouping(self):
        with tempfile.TemporaryDirectory() as d:
            directory=self._fixture(Path(d))
            turn=audit.read_json(directory/"turn-1.json")
            turn["tool_results"].append({"request_id":"accepted-focus","tool_name":"focus_task","success":True,
                "data":{"status":"active","subgoal_id":"fixture-s1","title":"actual purpose"},"error":None})
            (directory/"turn-1.json").write_text(json.dumps(turn),encoding="utf8")
            response={"raw_assistant_message":{"tool_calls":[{"id":"accepted-focus","function":{
                "name":"focus_task","arguments":json.dumps({"title":"actual purpose","requirements":[
                    {"tool":"amplitude","record":"A","scope":{"start":0,"end":2}},
                    {"tool":"psd","record":"A","scope":{"start":0,"end":2}}]})}}]}}
            with (directory/"responses.jsonl").open("a",encoding="utf8") as stream:stream.write(json.dumps(response)+"\n")
            groups=audit.audit_run(directory)["autonomous_grouping_observations"]
            self.assertEqual(len(groups),1)
            self.assertEqual(groups[0]["declared_requirement_count"],2)
            self.assertEqual(groups[0]["accepted_proposal"]["subgoal_id"],"fixture-s1")

    def test_changed_frozen_protocol_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            directory=self._fixture(Path(d))
            spec=audit.read_json(directory/"protocol.json")
            spec["development"]["requests"][0]="altered"
            (directory/"protocol.json").write_text(json.dumps(spec),encoding="utf8")
            with self.assertRaises(ValueError):audit.audit_run(directory)

    def test_comparison_operands_and_arithmetic_are_separately_verified(self):
        agent=stage.build_agent(None,"scientific-working","audit-comparison")
        seed=stage.controlled_history(agent)
        comparison=next(r["result"]["data"] for r in seed["actions"] if r["tool"]=="compare_results")
        result=audit._comparison_checks(comparison,stage.records_for())
        self.assertTrue(result["difference_valid"] and result["ratio_valid"])
        self.assertTrue(all(c["numeric_valid"] and c["source_valid"] for c in result["operands"]))
        comparison["right_minus_left"] *= 100
        self.assertFalse(audit._comparison_checks(comparison,stage.records_for())["difference_valid"])

    def test_no_real_runs_produces_no_successful_artifact(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):audit.build_audit(Path(d))

    def test_failed_and_missing_usage_calls_keep_conservative_cost(self):
        ledger=[{"event":"reserved","request_id":"a","reserved_tokens":400,"context":{"run_id":"x"}},
            {"event":"failed","request_id":"a"},
            {"event":"reserved","request_id":"b","reserved_tokens":600,"context":{"run_id":"x"}},
            {"event":"received","request_id":"b","usage":{}}]
        cost=audit._costs(ledger)["x"]
        self.assertEqual(cost["attempts"],2)
        self.assertEqual(cost["charged_tokens"],1000)
        self.assertEqual(cost["api_input_tokens"],0)
        self.assertEqual(cost["failed"],1)


if __name__=="__main__":unittest.main()
