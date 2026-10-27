"""Read-only audit is not a success oracle and never upgrades indexes to facts."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from eeg_harness.research import working_memory_issue50 as stage
from eeg_harness.research import working_memory_issue50_audit as audit


def request(value):
    return {"messages":[{"role":"user","content":json.dumps(value)}]}


class EvidenceExposureTest(unittest.TestCase):
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
        agent=stage.build_agent(None,"managed-full","audit-fixture")
        seeded=stage.seed_controlled_history(agent)
        observed=next(a["result"] for a in seeded["actions"] if a["tool"]=="amplitude")
        records=stage.records_for()
        spec=stage.protocol()
        manifest={"phase":"layer1","arm":"managed-full","candidate_commit":"fixture",
            "protocol_sha256":"fixture-protocol","model_requested":"offline-test","model_settings":{},
            "data_sha256":{alias:hashlib.sha256(record.data.tobytes()).hexdigest() for alias,record in records.items()}}
        turn={"stop_reason":"completed","rounds":1,"tool_calls":1,
            "final_answer":"故意不完整的测试回答；completed不可等于科学验收通过。",
            "tool_results":[observed],"working_memory":{}}
        for name,data in (("manifest.json",manifest),("protocol.json",spec),("turn-1.json",turn)):
            (directory/name).write_text(json.dumps(data,ensure_ascii=False),encoding="utf8")
        req={"request_id":"request-one","context":{"turn":1},**request({"current_request":spec["layer1"]["requests"][0]})}
        resp={"raw_assistant_message":{"tool_calls":[{"id":observed["request_id"],"function":{"name":"amplitude","arguments":json.dumps({"channels":["SYNTH-C1"],"start":0,"end":2})}}]}}
        for name,row in (("requests.jsonl",req),("responses.jsonl",resp)):
            (directory/name).write_text(json.dumps(row,ensure_ascii=False)+"\n",encoding="utf8")
        ledger=[{"event":"opened","stage":"issue50"},
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
