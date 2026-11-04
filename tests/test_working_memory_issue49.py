"""Issue49 actual-tool protocol and persistent shared-pool/final-input gates."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from eeg_harness.llm import LLMServiceError
from eeg_harness.research import working_memory_issue49 as stage
from eeg_harness.research.task_memory_issue39_budget import _rows, ledger_totals, StageBudgetExhausted


class FakeJournal:
    def __init__(self, failure=False, usage=True):
        self.client=SimpleNamespace(max_tokens=1600,max_retries=0,timeout=45,
            last_usage={"prompt_tokens":70,"completion_tokens":30,"total_tokens":100} if usage else {},
            last_response_model="offline",last_finish_reason="stop")
        self.model,self.request_count,self.total_usage="offline",0,{}
        self.failure=failure
    def complete(self,*args):
        self.request_count+=1
        if self.failure: raise RuntimeError("Synthetic network failure")
        return {"content":"offline"}


def seed(path,count,charged,phase,case):
    with path.open("a",encoding="utf8") as f:
        for i in range(count):
            f.write(json.dumps({"event":"reserved","request_id":f"{phase}-{case}-{i}","reserved_tokens":charged,
                               "context":{"phase":phase,"case":case}})+"\n")


class Issue49ProtocolTest(unittest.TestCase):
    def test_strong_summary_history_is_not_misattributed_as_current_state(self):
        history=[{"record":"B","facts":[{"value":1.5,"unit":"V²"}]}]
        payload={"current_request":"查历史","user_requests":["查历史"],"generic_summary":history,
                 "records":{"B":"synthetic"},"exact_evidence":[],"restored_trajectories":[]}
        parts=stage.input_components([{"role":"user","content":json.dumps(payload)}],[])
        self.assertEqual(parts["parts"]["history_index"],len(stage.encoded(history)))
        self.assertEqual(parts["parts"]["current_state"],len(stage.encoded({"records":{"B":"synthetic"}})))
        self.assertGreaterEqual(parts["serialization_envelope_bytes"],0)

    def test_science_actual_registry_positive_and_short_window_negative(self):
        data=stage.scientific_preflight()
        self.assertEqual(data["status"],"passed")
        self.assertTrue(all(x["valid"] for x in data["oracle_checks"]))
        failures=[op for op in data["operations"] if not op["result"]["success"]]
        self.assertEqual(len(failures),1)
        self.assertEqual(failures[0]["tool"],"event_bandpower")
        self.assertFalse(failures[0]["expected_success"])
        self.assertEqual(data["minimum_epoch_power_seconds"],1.0)
        observations={op["tool"]:op["result"]["data"] for op in data["operations"] if op["result"]["success"]}
        self.assertEqual(observations["event_bandpower"]["artifact_id"],observations["epoch_quality"]["artifact_id"])

    def test_budget_views_include_comparison_read_and_actual_restored_quality(self):
        data=stage.budget_preflight()
        self.assertEqual([r["case"] for r in data["samples"]],
            ["D","C","A","A_revised_comparison","A_history_value","B","B_restored_quality"])
        self.assertTrue(all(s["final_message_bytes"]<=96000 for s in data["samples"]))
        restore=data["samples"][-1]
        self.assertTrue(restore["same_artifact_used"])
        self.assertGreater(restore["final_components"]["parts"]["restored_trajectory"],2)
        self.assertGreater(restore["settled_final_reserve"],restore["final_message_bytes"]+1600)
        self.assertNotIn("token_cap",stage.protocol()["confirmation"]["D"])

    def test_confirmation_shared_pool_has_no_legacy_case_token_or_call_bin(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"budget.jsonl"
            stage.Issue49Client(FakeJournal(),p,phase="confirmation",case="D")
            seed(p,7,5000,"confirmation","D") # beyond old D's 6/30k limits
            raw=FakeJournal()
            stage.Issue49Client(raw,p,phase="confirmation",case="C").complete([],[])
            self.assertEqual(raw.request_count,1)
            self.assertEqual(ledger_totals(p)["attempts"],8)

    def test_development_pool_cumulative_and_does_not_take_confirmation(self):
        for count,charged in ((24,1),(1,150000)):
            with self.subTest(count=count),tempfile.TemporaryDirectory() as d:
                p=Path(d)/"budget.jsonl"
                stage.Issue49Client(FakeJournal(),p,phase="development",case="development")
                seed(p,count,charged,"development","development")
                raw=FakeJournal()
                with self.assertRaises(LLMServiceError):
                    stage.Issue49Client(raw,p,phase="development",case="development").complete([],[])
                self.assertEqual(raw.request_count,0)
                stage.Issue49Client(raw,p,phase="confirmation",case="D").complete([],[])
                self.assertEqual(raw.request_count,1)

    def test_pool_and_global_caps_stop_before_network(self):
        for phase,count,charged in (("confirmation",56,1),("confirmation",1,350000),("development",1,500000)):
            with self.subTest(phase=phase,count=count),tempfile.TemporaryDirectory() as d:
                p=Path(d)/"budget.jsonl"
                stage.Issue49Client(FakeJournal(),p,phase=phase,case="D" if phase=="confirmation" else "development")
                seed(p,count,charged,phase,"D")
                raw=FakeJournal()
                with self.assertRaises(LLMServiceError):
                    stage.Issue49Client(raw,p,phase=phase,case="D" if phase=="confirmation" else "development").complete([],[])
                self.assertEqual(raw.request_count,0)

    def test_early_final_reserves_full_input_and_rechecks_at_send(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"budget.jsonl"
            raw=FakeJournal(); client=stage.Issue49Client(raw,p,phase="development",case="development")
            seed(p,1,100000,"development","development")
            final=[{"role":"user","content":"已测得的合成结果"*20}]
            finish=[{"type":"function","function":{"name":"finish_task","parameters":{"type":"object"}}}]
            self.assertTrue(client.prepare_decision([{"role":"user","content":"继续"}],finish,final,finish))
            row=_rows(p)[-1]
            self.assertGreater(row["actual_final_reserve"],1600+len(stage.encoded(final)))
            self.assertGreater(row["bounded_next_final_reserve"],96000+1600)
            with self.assertRaises(LLMServiceError): client.complete([],finish)
            self.assertEqual(raw.request_count,0)
            client.complete(final,finish,stage.FINISH_CHOICE)
            self.assertEqual(raw.request_count,1)

    def test_short_two_request_path_fits_shared_pool_with_future_floors(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"budget.jsonl"
            raw=FakeJournal(); client=stage.Issue49Client(raw,p,phase="confirmation",case="D",
                future_floors=stage.protocol()["budget_policy"]["future_floors"])
            messages=[{"role":"user","content":"合成结果"*2000}]
            finish=[{"type":"function","function":{"name":"finish_task"}}]
            self.assertFalse(client.prepare_decision(messages,finish,messages,finish))
            client.complete(messages,finish)
            # Normal second decision remains possible, unlike Issue48 D.
            self.assertFalse(client.prepare_decision(messages,finish,messages,finish))
            client.complete(messages,finish,stage.FINISH_CHOICE)
            self.assertEqual(raw.request_count,2)

    def test_failed_missing_usage_and_unresolved_attempts_keep_reservation(self):
        for fail,usage in ((True,True),(False,False)):
            with self.subTest(fail=fail),tempfile.TemporaryDirectory() as d:
                p=Path(d)/"budget.jsonl"; log=Path(d)/"requests.jsonl"
                raw=FakeJournal(failure=fail,usage=usage)
                client=stage.Issue49Client(raw,p,phase="development",case="development",request_journal=log)
                if fail:
                    with self.assertRaises(RuntimeError): client.complete([{"role":"user","content":"合成"}],[])
                else: client.complete([{"role":"user","content":"合成"}],[])
                reserve=next(r["reserved_tokens"] for r in _rows(p) if r["event"]=="reserved")
                self.assertEqual(ledger_totals(p)["charged_tokens"],reserve)
                self.assertIn("actual_wire_payload_bytes",_rows(log)[0])
                self.assertNotIn("api_key",log.read_text())

    def test_old_ledger_or_modified_authorization_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"budget.jsonl"; p.write_text('{"event":"opened","stage":"issue48"}\n')
            with self.assertRaises(StageBudgetExhausted): stage.Issue49Client(FakeJournal(),p,phase="development",case="development")
        with tempfile.TemporaryDirectory() as d:
            spec=stage.protocol();spec["limits"]["api_tokens"]+=1
            with self.assertRaises(StageBudgetExhausted):
                stage.Issue49Client(FakeJournal(),Path(d)/"b.jsonl",phase="development",case="development",protocol=spec)

    def test_confirmation_once_order_and_frozen_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"budget.jsonl"
            stage.Issue49Client(FakeJournal(),p,phase="confirmation",case="D")
            m={"candidate_commit":"offline","protocol_sha256":"frozen"}
            with self.assertRaises(StageBudgetExhausted): stage._start_case(p,"C","wrong",m,{})
            stage._start_case(p,"D","first",m,{})
            with self.assertRaises(StageBudgetExhausted): stage._start_case(p,"D","again",m,{})
            with self.assertRaises(StageBudgetExhausted): stage._start_case(p,"C","early",m,{})
            stage._append(p,{"event":"case_ended","case":"D"})
            with self.assertRaises(StageBudgetExhausted): stage._start_case(p,"C","changed",dict(m,candidate_commit="changed"),{})
            stage._start_case(p,"C","second",m,{})


if __name__=="__main__": unittest.main()
