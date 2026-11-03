"""Explicit TEST-only HTTP503 lifecycle, no service/credentials/formal ledger."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from eeg_harness.llm import LLMServiceError
from eeg_harness.research import working_memory_issue60_recovery as r
from eeg_harness.research.working_memory_issue55_live import (
    MoneyBudgetClient, register_http503_recovery, candidate_manifest, run_session,
    money_totals, actual_settings)
from eeg_harness.research.integrated_method.v2_validation import JournaledBudgetClient
from eeg_harness.research.task_memory_issue39_budget import _rows, _append, StageBudgetExhausted
from test_issue55_live import RawFake, setup, case_and_actions


class Faults(RawFake):
    def __init__(self, failures, actions=None, *, error_status=503, missing_usage=False):
        super().__init__(actions or [], missing_usage=missing_usage)
        self.has_script=bool(actions)
        self.failures=set(failures);self.error_status=error_status;self.inputs=[]

    def complete(self,messages,tools,tool_choice='auto'):
        self.inputs.append(deepcopy((messages,tools,tool_choice)))
        if self.request_count+1 in self.failures:
            self.request_count+=1
            raise LLMServiceError('SERVICE_UNAVAILABLE','TEST HTTP failure',status=self.error_status,retryable=True)
        if not self.has_script:
            self.request_count+=1
            self.last_usage={'prompt_tokens':100,'completion_tokens':20,'total_tokens':120}
            self.total_usage={'total_tokens':self.request_count*120}
            return {'role':'assistant','content':'TEST only'}
        return super().complete(messages,tools,tool_choice)


class RecoveryTest(unittest.TestCase):
    def fixture(self,root,raw):
        ledger,a=setup(root,raw)
        baseline={'source':candidate_manifest()}
        register_http503_recovery(raw,ledger,a,baseline=baseline,test_only=True)
        client=self.client(root,raw,ledger,a)
        return ledger,a,baseline,client

    def client(self,root,raw,ledger,a,*,resume=None,execution='TEST-session'):
        c=MoneyBudgetClient(JournaledBudgetClient(raw,root/'responses',max_requests=100,max_total_tokens=2000000),ledger,a,'development',
                            request_journal=root/'requests',test_only=True)
        c.enable_recovery({'execution_id':execution},lambda:'TEST-state')
        c._retry_of=resume
        c.set_context(case_id='T05',turn=1)
        return c

    def call(self,c,text='same'):
        return c.complete([{'role':'user','content':text}],[])

    @patch('eeg_harness.research.working_memory_issue55_live.time.sleep')
    def test_503_success_and_second_retry(self,sleep):
        for failures,expected in [({1},2),({1,2},3),({1,2,3},3)]:
            with self.subTest(failures=failures),tempfile.TemporaryDirectory() as td:
                raw=Faults(failures);ledger,a,b,c=self.fixture(Path(td),raw)
                if len(failures)==3:
                    with self.assertRaises(StageBudgetExhausted):self.call(c)
                else:self.call(c)
                rows=_rows(ledger);starts=[x for x in rows if x['event']=='reserved']
                self.assertEqual(raw.request_count,expected);self.assertEqual(len(starts),expected)
                self.assertEqual(len({s['request_id'] for s in starts}),expected)
                self.assertTrue(all(x==raw.inputs[0] for x in raw.inputs))
                self.assertEqual([x['recovery']['ordinal'] for x in starts],list(range(expected)))
                self.assertEqual(len([x for x in rows if x['event']=='money_settled']),expected)
                self.assertEqual(bool(r.active_stops(rows,r.SCOPE)),len(failures)==3)
                self.assertTrue(r.active_stops(rows)) # no-permission caller still stops
                original=next(x for x in rows if x['event']=='money_settled')
                self.assertEqual(Decimal(original['charged_usd']),Decimal(starts[0]['reserved_usd']))
                self.assertTrue(original['reconciliation_required'])
                self.assertEqual(len([x for x in _rows(Path(td)/'responses') if x['request_id']]),expected)
        self.assertIn(((45,),{}),sleep.call_args_list)

    @patch('eeg_harness.research.working_memory_issue55_live.time.sleep')
    def test_global_eight_retries_and_restart_not_reset(self,_sleep):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);raw=Faults(range(1,18,2));ledger,a,b,c=self.fixture(root,raw)
            for i in range(8):
                c.set_context(turn=i+1);self.call(c,str(i))
            c.set_context(turn=9)
            with self.assertRaises(StageBudgetExhausted):self.call(c,'ninth')
            self.assertEqual(raw.request_count,17)
            before=ledger.read_bytes()
            register_http503_recovery(raw,ledger,a,baseline=b,test_only=True)
            self.assertEqual(ledger.read_bytes(),before)
            last=[x for x in _rows(ledger) if x['event']=='reserved'][-1]['request_id']
            restarted=self.client(root,raw,ledger,a,resume=last);restarted.set_context(turn=9)
            with self.assertRaises(StageBudgetExhausted):self.call(restarted,'ninth')
            self.assertEqual(raw.request_count,17)

    @patch('eeg_harness.research.working_memory_issue55_live.time.sleep')
    def test_other_failures_and_success_missing_usage_not_covered(self,_sleep):
        for status in (None,429,500,502,504,401):
            with self.subTest(status=status),tempfile.TemporaryDirectory() as td:
                raw=Faults({1},error_status=status);ledger,a,b,c=self.fixture(Path(td),raw)
                with self.assertRaises(LLMServiceError):self.call(c)
                self.assertEqual(raw.request_count,1);self.assertTrue(r.active_stops(_rows(ledger),r.SCOPE))
        for defect in ('missing_usage','wrong_model','network'):
            with self.subTest(defect=defect),tempfile.TemporaryDirectory() as td:
                raw=RawFake([('inspect_plan',{})],missing_usage=defect=='missing_usage',fail=defect=='network')
                ledger,a,b,c=self.fixture(Path(td),raw)
                if defect=='wrong_model':raw.last_response_model='WRONG'
                with self.assertRaises((LLMServiceError,RuntimeError)):self.call(c)
                self.assertEqual(raw.request_count,1);self.assertTrue(r.active_stops(_rows(ledger),r.SCOPE))

    @patch('eeg_harness.research.working_memory_issue55_live.time.sleep')
    def test_caps_turn_time_and_final_lease(self,_sleep):
        for bound in ('calls','tokens','usd','turn','time','lease'):
            with self.subTest(bound=bound),tempfile.TemporaryDirectory() as td:
                raw=Faults({1});ledger,a,b,c=self.fixture(Path(td),raw)
                if bound=='calls':c.caps['development'][0]=1
                if bound=='tokens':c.caps['development'][1]=c.reservation([{'role':'user','content':'same'}],[])+1
                if bound=='usd':c.caps['usd']='0.003'
                if bound=='turn':c._turn_attempts=lambda rows:11
                if bound=='time':c._time_remaining=lambda:20
                if bound=='lease':c._lease={'reserved_tokens':1999999}
                with self.assertRaises((LLMServiceError,StageBudgetExhausted)):self.call(c)
                self.assertLessEqual(raw.request_count,1)

    @patch('eeg_harness.research.working_memory_issue55_live.time.sleep')
    def test_other_stop_or_freeze_does_not_unlock(self,_sleep):
        for event in ({'event':'stage_closed'},{'event':'confirmation_frozen'},
                      {'event':'safety_stop','request_id':'OTHER','reason':'scientific_execution_mismatch'}):
            with tempfile.TemporaryDirectory() as td:
                raw=Faults({1});ledger,a,b,c=self.fixture(Path(td),raw);_append(ledger,event)
                with self.assertRaises((StageBudgetExhausted,LLMServiceError)):self.call(c)
                self.assertEqual(raw.request_count,0)

    @patch('eeg_harness.research.working_memory_issue55_live.time.sleep')
    def test_crashes_do_not_grant_ambiguous_resend(self,_sleep):
        # Crash after reservation (no failed/received) conservatively stops.
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);raw=Faults({1});ledger,a,b,c=self.fixture(root,raw)
            with patch.object(c.client,'complete',side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):self.call(c)
            rows=_rows(ledger);ident=next(x['request_id'] for x in rows if x['event']=='reserved')
            restarted=self.client(root,raw,ledger,a,resume=ident)
            with self.assertRaises(StageBudgetExhausted):self.call(restarted)
            self.assertEqual(raw.request_count,0)
        # Crash after disposition but before reservation does not clear stop.
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);raw=Faults({1});ledger,a,b,c=self.fixture(root,raw)
            def crash(rows,ident,meta):
                MoneyBudgetClient.commit_attempt(c,rows,ident,meta)
                if meta.get('recovery',{}).get('retry_of'):raise KeyboardInterrupt
            with patch.object(c,'commit_attempt',side_effect=crash):
                with self.assertRaises(KeyboardInterrupt):self.call(c)
            rows=_rows(ledger);self.assertTrue(r.active_stops(rows,r.SCOPE))
            failed=next(x['request_id'] for x in rows if x['event']=='failed')
            restarted=self.client(root,raw,ledger,a,resume=failed)
            self.call(restarted);self.assertEqual(raw.request_count,2)
            self.assertFalse(r.active_stops(_rows(ledger),r.SCOPE))

    @patch('eeg_harness.research.working_memory_issue55_live.time.sleep')
    def test_mismatched_wire_state_runtime_and_consumed_request(self,_sleep):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);raw=Faults({1});ledger,a,b,c=self.fixture(root,raw)
            with patch.object(c,'_time_remaining',return_value=20):
                with self.assertRaises(LLMServiceError):self.call(c)
            old=next(x['request_id'] for x in _rows(ledger) if x['event']=='failed')
            for defect in ('wire','state','runtime'):
                retry=self.client(root,raw,ledger,a,resume=old)
                if defect=='state':retry.recovery_state=lambda:'changed'
                if defect=='runtime':raw.timeout=11
                with self.assertRaises((LLMServiceError,StageBudgetExhausted)):
                    self.call(retry,'changed' if defect=='wire' else 'same')
                raw.timeout=10
            self.assertEqual(raw.request_count,1)
            retry=self.client(root,raw,ledger,a,resume=old);self.call(retry)
            replay=self.client(root,raw,ledger,a,resume=old)
            with self.assertRaises(StageBudgetExhausted):self.call(replay)
            self.assertEqual(raw.request_count,2)

    @patch('eeg_harness.research.working_memory_issue55_live.time.sleep')
    def test_concurrent_retry_only_one_reserved(self,_sleep):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);raw=Faults({1});ledger,a,b,c=self.fixture(root,raw)
            with patch.object(c,'_time_remaining',return_value=20):
                with self.assertRaises(LLMServiceError):self.call(c)
            old=next(x['request_id'] for x in _rows(ledger) if x['event']=='failed')
            clients=[self.client(root,raw,ledger,a,resume=old) for _ in range(2)];errors=[]
            def attempt(c):
                try:self.call(c)
                except StageBudgetExhausted as e:errors.append(str(e))
            ts=[threading.Thread(target=attempt,args=(c,)) for c in clients]
            for t in ts:t.start()
            for t in ts:t.join()
            self.assertEqual(raw.request_count,2);self.assertEqual(len(errors),1)

    @patch('eeg_harness.research.working_memory_issue55_live.time.sleep')
    def test_actual_agent_retains_tools_before_failure_and_turn_budget(self,_sleep):
        case,actions=case_and_actions();case['id']='T05'
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);raw=Faults({1,4},actions);ledger,a,b,c=self.fixture(root,raw)
            result=run_session(raw,ledger,a,case,root/'run',test_only=True,recovery_scope=r.SCOPE)
            self.assertEqual(len(result),2)
            self.assertEqual(raw.request_count,8)
            self.assertEqual(raw.inputs[0],raw.inputs[1])
            self.assertEqual(raw.inputs[3],raw.inputs[4]) # after amplitude already executed
            wm=result[-1]['working_memory']
            entries=wm['subgoals']
            self.assertEqual(len(entries),2)
            self.assertFalse(r.active_stops(_rows(ledger),r.SCOPE))
            before=raw.request_count
            with self.assertRaises(StageBudgetExhausted):
                run_session(raw,ledger,a,case,root/'duplicate',test_only=True,recovery_scope=r.SCOPE)
            self.assertEqual(raw.request_count,before)

    @patch('eeg_harness.research.working_memory_issue55_live.time.sleep')
    def test_historical_empty_first_call_exact_resume_and_bad_evidence(self,_sleep):
        case,actions=case_and_actions();case['id']='T05'
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);failed=Faults({1},actions);ledger,a=setup(root,failed)
            baseline={'source':candidate_manifest()}
            original=run_session(failed,ledger,a,case,root/'original',test_only=True)
            self.assertEqual(original[0]['tool_calls'],0)
            before=ledger.read_bytes()
            raw=Faults(set(),actions)
            register_http503_recovery(raw,ledger,a,baseline=baseline,original_output=root/'original',test_only=True)
            registered=ledger.read_bytes();self.assertTrue(registered.startswith(before))
            register_http503_recovery(raw,ledger,a,baseline=baseline,original_output=root/'original',test_only=True)
            self.assertEqual(registered,ledger.read_bytes())
            results=run_session(raw,ledger,a,case,root/'resume',test_only=True,recovery_scope=r.SCOPE)
            self.assertEqual(len(results),2);self.assertEqual(raw.request_count,6)
            reqs=[x for x in _rows(root/'resume/requests.jsonl') if 'messages' in x]
            old=_rows(root/'original/requests.jsonl')[0]
            for k in ('messages','tools','tool_choice'):self.assertEqual(old[k],reqs[0][k])
            rows=_rows(ledger);starts=[x for x in rows if x['event']=='reserved']
            self.assertEqual(len(starts),7)
            self.assertEqual(starts[1]['recovery']['retry_of'],old['request_id'])
            self.assertEqual(starts[1]['recovery']['ordinal'],1)
            bad=json.loads((root/'original/turn-1.json').read_text(encoding='utf8'))
            bad['result']['llm']['error']['status']=502
            (root/'original/turn-1.json').write_text(json.dumps(bad),encoding='utf8')
            with self.assertRaises(StageBudgetExhausted):
                r.historical_initial_evidence(root/'original',rows,'bad',baseline['source'])

    def test_crash_after_money_settlement_repairs_stop_without_double_charge(self):
        for status in (503,502):
            with self.subTest(status=status),tempfile.TemporaryDirectory() as td:
                root=Path(td);raw=Faults({1},error_status=status);ledger,a,b,c=self.fixture(root,raw)
                def crash(path,row):
                    _append(path,row)
                    if row.get('event')=='money_settled':raise KeyboardInterrupt
                with patch('eeg_harness.research.working_memory_issue55_live._append',side_effect=crash):
                    with self.assertRaises(KeyboardInterrupt):self.call(c)
                prior=_rows(ledger);cost=money_totals(prior,Decimal('1.2'))
                self.assertFalse(any(x['event']=='safety_stop' for x in prior))
                restarted=self.client(root,raw,ledger,a)
                after=_rows(ledger)
                self.assertEqual(money_totals(after,Decimal('1.2')),cost)
                self.assertEqual(sum(x['event']=='money_settled' for x in after),1)
                self.assertEqual(sum(x['event']=='safety_stop' for x in after),1)
                with self.assertRaises(LLMServiceError):self.call(restarted)
                self.assertEqual(raw.request_count,1)

    @patch('eeg_harness.research.working_memory_issue55_live.time.sleep')
    def test_disposition_cannot_clear_wrong_request_or_duplicate_child(self,_sleep):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);raw=Faults({1});ledger,a,b,c=self.fixture(root,raw);self.call(c)
            rows=_rows(ledger);d=next(x for x in rows if x['event']=='http503_disposition')
            for mutation in ({'request_id':'wrong'},{'retry_request_id':'missing'}, {'scope_id':'other'}):
                changed=deepcopy(rows);next(x for x in changed if x['event']=='http503_disposition').update(mutation)
                try:active=r.active_stops(changed,r.SCOPE)
                except StageBudgetExhausted:continue
                self.assertTrue(active)
            original=next(x for x in rows if x['event']=='reserved')
            with self.assertRaises(StageBudgetExhausted):
                r.retry_metadata(rows,'another',original['request_id'],original['recovery'])

    def test_registration_crash_import_is_idempotent_and_prefix_is_protected(self):
        case,actions=case_and_actions();case['id']='T05'
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);raw=Faults({1},actions);ledger,a=setup(root,raw);baseline={'source':candidate_manifest()}
            run_session(raw,ledger,a,case,root/'old',test_only=True)
            def crash(path,row):
                _append(path,row)
                if row.get('event')=='http503_historical_evidence':raise KeyboardInterrupt
            with patch('eeg_harness.research.working_memory_issue55_live._append',side_effect=crash):
                with self.assertRaises(KeyboardInterrupt):
                    register_http503_recovery(raw,ledger,a,baseline=baseline,original_output=root/'old',test_only=True)
            self.assertIsNone(r.policy(_rows(ledger)));self.assertTrue(r.active_stops(_rows(ledger),r.SCOPE))
            register_http503_recovery(raw,ledger,a,baseline=baseline,original_output=root/'old',test_only=True)
            self.assertEqual(sum(x['event']=='http503_historical_evidence' for x in _rows(ledger)),1)
            text=ledger.read_text(encoding='utf8').replace('TEST SIMULATED PRICES','TEST ALTERED PRICES',1)
            ledger.write_text(text,encoding='utf8')
            with self.assertRaises(StageBudgetExhausted):self.client(root,raw,ledger,a)

    def test_baseline_file_map_cannot_retain_a_false_declared_hash(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);raw=Faults(set());ledger,a=setup(root,raw)
            baseline={'source':candidate_manifest()}
            baseline['source']['files']['src/eeg_harness/task_plan.py']='changed'
            before=ledger.read_bytes()
            with self.assertRaises(StageBudgetExhausted):
                register_http503_recovery(raw,ledger,a,baseline=baseline,test_only=True)
            self.assertEqual(before,ledger.read_bytes());self.assertEqual(raw.request_count,0)


if __name__=='__main__':unittest.main()
