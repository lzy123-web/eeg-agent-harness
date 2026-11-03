"""Sixth funding and candidate transition using TEST ledgers and simulated rates."""
from copy import deepcopy
from decimal import Decimal
import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from eeg_harness.research.working_memory_issue55_live import *
from eeg_harness.research.working_memory_issue61_live import register_candidate,behavior
from eeg_harness.research.task_memory_issue39_budget import _append,_rows,StageBudgetExhausted
from eeg_harness.research.working_memory_issue51 import _usage
from eeg_harness.task_plan_agent import TaskPlanEEGAgent
from eeg_harness.research.working_memory_issue52 import records_for
from test_issue59_closeout_authorization import closeout_seed
from test_issue58_authorization import client
from test_issue60_recovery import Faults
import test_issue60_recovery as recovery_tests
from test_issue60_convergence import compact_steps


def seed(root):
    raw,p,a,c,proof=closeout_seed(root)
    apply_authorization_revision(raw,p,a,proof,test_only=True)
    def history(count,tokens):
        c=client(raw,p,a,root)
        for i in range(count):
            n=tokens//count+(i<tokens%count);ident=f'TEST-history-{len(_rows(p))}'
            _append(p,{'event':'reserved','request_id':ident,'context':{'phase':'development'},'reserved_tokens':n,'output_cap':2200,**c.reservation_metadata(n)})
            _append(p,{'event':'received','request_id':ident,'response_model_reported':raw.model,'total_tokens':n,'usage':{'prompt_tokens':n-20,'completion_tokens':20,'total_tokens':n}})
        c.settle_pending()
    history(21,292911)
    proof.update(revision_id=INTERFACE_REVISION,additional_grant=INTERFACE_GRANT,new_limits=deepcopy(INTERFACE_CAPS),prefix_sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    apply_authorization_revision(raw,p,a,proof,test_only=True)
    # One actual Fake 503 disposition + successful retry, then settle the
    # remaining simulated historical calls to the fixed guard-token snapshot.
    raw=Faults({1})
    register_http503_recovery(raw,p,a,baseline={'source':candidate_manifest()},test_only=True)
    c=recovery_tests.RecoveryTest().client(root,raw,p,a)
    with patch('eeg_harness.research.working_memory_issue55_live.time.sleep'):c.complete([{'role':'user','content':'TEST historical 503'}],[])
    history(102,5328790-_usage(_rows(p))[1])
    proof.update(revision_id=REPAIR_REVISION,additional_grant=REPAIR_GRANT,new_limits=deepcopy(REPAIR_CAPS),prefix_sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    a['mechanism_gate']={'status':'passed','source_sha256':candidate_manifest()['sha256'],'evidence_sha256':'TEST'}
    a['readonly_review_sha256']='TEST'
    return raw,p,a,proof


class GrantTest(unittest.TestCase):
    def test_sixth_idempotent_prefix_fixed_usage_stops_and_limits(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);raw,p,a,proof=seed(root);prefix=p.read_bytes()
            receipt=apply_authorization_revision(raw,p,a,proof,test_only=True)
            self.assertEqual(receipt['prior_usage'],[409,5328790]);self.assertTrue(p.read_bytes().startswith(prefix))
            before=p.read_bytes();self.assertEqual(apply_authorization_revision(raw,p,a,proof,test_only=True),receipt);self.assertEqual(p.read_bytes(),before)
            c=client(raw,p,a,root);c.enable_recovery({'execution_id':'TEST-new'},lambda:'TEST')
            self.assertEqual(c.caps,REPAIR_CAPS);self.assertEqual(c.stage_money_start,Decimal(receipt['prior_usd']))
            rows=_rows(p)
            near=rows+[{'event':'reserved','request_id':f'TEST-future-{i}','context':{'phase':'development'},
                        'reserved_tokens':0,'reserved_usd':'0'} for i in range(239)]
            self.assertTrue(c._fits(near,1,1));self.assertFalse(c._fits(near,2,1))
            self.assertFalse(c._fits(rows,1,4000001))
            self.assertEqual(sum(r['event']=='reserved' and r.get('recovery',{}).get('ordinal',0)>0 for r in rows),1)
            self.assertFalse(recovery.active_stops(rows,recovery.SCOPE));self.assertTrue(recovery.active_stops(rows))
            for event in ('safety_stop','stage_closed','confirmation_frozen'):
                q=root/event;q.write_bytes(before);_append(q,{'event':event,'request_id':'TEST-uncovered'})
                with self.assertRaises(StageBudgetExhausted):apply_authorization_revision(raw,q,a,proof,test_only=True)
            with self.assertRaises(StageBudgetExhausted):run_session(raw,p,a,{},root/'confirm',phase='confirmation',test_only=True)

    def test_candidate_append_new_execution_no_old_import_and_one_shot_final(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);raw,p,a,proof=seed(root);apply_authorization_revision(raw,p,a,proof,test_only=True)
            freeze=register_candidate(raw,p,a,'TEST-c1',rationale={'design':'TEST'},test_only=True)
            before=p.read_bytes();register_candidate(raw,p,a,'TEST-c1',rationale={'design':'TEST'},test_only=True);self.assertEqual(before,p.read_bytes())
            with self.assertRaises(StageBudgetExhausted):register_candidate(raw,p,a,'TEST-hash-only',rationale={'new_real_root_cause_evidence':'TEST'},test_only=True)
            cases=development_cases();case=next(c for c in cases if c['id']=='T07')
            raw=Faults(set(),sum(compact_steps('T07'),[]))
            result=run_session(raw,p,a,case,root/'T07',test_only=True,candidate_id='TEST-c1')
            self.assertEqual([r['stop_reason'] for r in result],['completed','completed'])
            starts=[r for r in _rows(p) if r['event']=='session_started'];self.assertIsNone(starts[-1]['resumes_request'])
            with self.assertRaises(StageBudgetExhausted):run_session(raw,p,a,case,root/'again',test_only=True,candidate_id='TEST-c1')
            register_candidate(raw,p,a,'TEST-c1',rationale={'remaining_roots':'TEST','coverage':'TEST'},final=True,test_only=True)
            case=next(c for c in cases if c['id']=='T05');raw=Faults(set(),sum(compact_steps('T05'),[]))
            result=run_session(raw,p,a,case,root/'T05',test_only=True,candidate_id='TEST-c1')
            self.assertEqual([r['stop_reason'] for r in result],['completed','completed'])
            starts=[r for r in _rows(p) if r['event']=='session_started'];self.assertIsNone(starts[-1]['resumes_request'])
            self.assertNotEqual(starts[-1]['execution_id'],starts[-2]['execution_id'])
            self.assertEqual(sum(r['event']=='http503_recovery_permission' for r in _rows(p)),1)
            self.assertEqual(sum(r['event']=='authorization_revised' for r in _rows(p)),6)

    @patch('eeg_harness.research.working_memory_issue55_live.time.sleep')
    def test_retry_exhaustion_preserves_structured_stop_through_agent(self,_sleep):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);raw=Faults({1,2,3});p,a,b,c=recovery_tests.RecoveryTest().fixture(root,raw)
            agent=TaskPlanEEGAgent(c,records_for())
            result=agent.run('TEST record A inspect').to_dict()
            self.assertEqual(result['stop_reason'],'budget_exhausted')
            self.assertEqual(result['llm']['error']['code'],'STAGE_BUDGET_EXHAUSTED')
            self.assertIn('retry allowance exhausted',result['llm']['error']['message'])
            self.assertEqual(raw.request_count,3)
            self.assertTrue(recovery.active_stops(_rows(p),recovery.SCOPE))

if __name__=='__main__':unittest.main()
