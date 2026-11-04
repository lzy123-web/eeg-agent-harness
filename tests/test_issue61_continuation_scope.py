"""Explicit TEST scope transitions on temporary original-format ledgers."""
import hashlib,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from decimal import Decimal
from copy import deepcopy
from test_issue61_authorization import seed
from test_issue60_recovery import Faults
from eeg_harness.research.working_memory_issue55_live import (apply_authorization_revision,run_session,
    candidate_manifest,development_cases,recovery)
from eeg_harness.research.working_memory_issue61_live import (register_candidate,register_continuation,
    admit_candidate_session,continuation_request_fits,CONTINUATION_SCOPE,CONTINUATION_PERMISSION)
from eeg_harness.research.task_memory_issue39_budget import _rows,_append,StageBudgetExhausted

def fixture(root):
    raw,p,a,proof=seed(root);apply_authorization_revision(raw,p,a,proof,test_only=True)
    register_candidate(raw,p,a,'TEST-old-final',rationale={'design':'TEST old scope'},final=True,test_only=True)
    prefix=p.read_bytes();register_continuation(raw,p,a,test_only=True)
    source=deepcopy(candidate_manifest());source['files']['src/eeg_harness/agent.py']='TEST-science-continuation'
    source['sha256']=recovery.digest(source['files']);a['mechanism_gate']['source_sha256']=source['sha256']
    return raw,p,a,prefix,source

class ContinuationScopeTest(unittest.TestCase):
    def test_fake_full_agent_money_driver_two_turns_and_no_repeat(self):
        import json
        from test_issue61_continuation import original
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);raw,p,a,prefix,source=fixture(root)
            requests,responses=original('M01')
            actions=[]
            for response in responses[:4]:
                call=response['tool_calls'][0]['function']
                actions.append((call['name'],json.loads(call['arguments'])))
            actions.append(('finish_task',{'status':'partial','answer':'TEST bounded driver; revision not executed.',
                'unresolved':['TEST second turn not executed']}))
            raw=Faults(set(),actions)
            with patch('eeg_harness.research.working_memory_issue61_live.candidate_manifest',return_value=source),patch(
                    'eeg_harness.research.working_memory_issue55_live.candidate_manifest',return_value=source):
                register_candidate(raw,p,a,'TEST-driver',rationale={'design':'TEST'},scope=CONTINUATION_SCOPE,test_only=True)
                case=next(c for c in development_cases() if c['id']=='M01')
                results=run_session(raw,p,a,case,root/'driver',test_only=True,candidate_id='TEST-driver')
                self.assertEqual([r['stop_reason'] for r in results],['completed','partial'])
                register_candidate(raw,p,a,'TEST-driver',rationale={'decision':'TEST no revision'},scope=CONTINUATION_SCOPE,final=True,test_only=True)
                with self.assertRaises(StageBudgetExhausted):run_session(raw,p,a,case,root/'again',test_only=True,candidate_id='TEST-driver')
            rows=_rows(p)
            self.assertEqual(sum(r['event']=='authorization_revised' for r in rows),6)
            self.assertTrue(p.read_bytes().startswith(prefix))
            self.assertTrue(any(r['event']=='final_lease_decision' for r in rows))
            self.assertEqual({r['request_id'] for r in rows if r['event']=='reserved'},
                {r['request_id'] for r in rows if r['event']=='money_settled'})

    def test_scope_append_idempotent_six_funding_prefix_protection(self):
        with tempfile.TemporaryDirectory() as td:
            raw,p,a,prefix,source=fixture(Path(td));before=p.read_bytes()
            register_continuation(raw,p,a,test_only=True);self.assertEqual(before,p.read_bytes())
            self.assertTrue(before.startswith(prefix));rows=_rows(p)
            self.assertEqual(sum(r['event']=='authorization_revised' for r in rows),6)
            self.assertEqual(sum(r['event']=='scope_permission' for r in rows),1)
            self.assertEqual(sum(r['event']=='candidate_final_frozen' for r in rows),1)
            self.assertEqual(sum(r['event']=='reserved' and r.get('recovery',{}).get('ordinal',0)>0 for r in rows),1)
            self.assertEqual(rows[-1]['permission_id'],CONTINUATION_PERMISSION)
            for event in ('safety_stop','stage_closed','confirmation_frozen'):
                q=Path(td)/event;q.write_bytes(before);_append(q,{'event':event,'request_id':'TEST-uncovered'})
                with self.assertRaises(StageBudgetExhausted):register_continuation(raw,q,a,test_only=True)
            q=Path(td)/'pending';q.write_bytes(before);_append(q,{'event':'reserved','request_id':'TEST-unsent','context':{'phase':'development'},'reserved_tokens':1})
            with self.assertRaises(StageBudgetExhausted):register_continuation(raw,q,a,test_only=True)

    def test_two_candidates_original_scope_and_cross_scope_fingerprint_guard(self):
        with tempfile.TemporaryDirectory() as td:
            raw,p,a,prefix,source=fixture(Path(td))
            # Old behavior cannot gain a new attempt by a scope/id change.
            a['mechanism_gate']['source_sha256']=candidate_manifest()['sha256']
            with self.assertRaises(StageBudgetExhausted):register_candidate(raw,p,a,'TEST-renamed',rationale={'design':'TEST'},scope=CONTINUATION_SCOPE,test_only=True)
            a['mechanism_gate']['source_sha256']=source['sha256']
            with patch('eeg_harness.research.working_memory_issue61_live.candidate_manifest',return_value=source):
                with self.assertRaises(StageBudgetExhausted):register_candidate(raw,p,a,'TEST-new',rationale={'design':'TEST'},scope=CONTINUATION_SCOPE,final=True,test_only=True)
                c=register_candidate(raw,p,a,'TEST-new',rationale={'design':'TEST'},scope=CONTINUATION_SCOPE,test_only=True)
                with self.assertRaises(StageBudgetExhausted):register_candidate(raw,p,a,'TEST-new',rationale={'design':'TEST'},scope=CONTINUATION_SCOPE,final=True,test_only=True)
            manifest={k:c[k] for k in ('source','runtime','data')}
            cases={c['id']:c for c in development_cases()}
            with self.assertRaises(StageBudgetExhausted):admit_candidate_session(p,_rows(p),cases['T05'],manifest,a,'TEST-new',True)
            admit_candidate_session(p,_rows(p),cases['M01'],manifest,a,'TEST-new',True)
            _append(p,{'event':'session_started','candidate_id':'TEST-new','case':'M01','execution_id':'TEST-run','phase':'development'})
            _append(p,{'event':'recovery_session_finished','execution_id':'TEST-run'})
            with self.assertRaises(StageBudgetExhausted):admit_candidate_session(p,_rows(p),cases['M01'],manifest,a,'TEST-new',True)
            newer=deepcopy(source);newer['files']['src/eeg_harness/agent.py']='TEST-new-real-mechanism';newer['sha256']=recovery.digest(newer['files']);a['mechanism_gate']['source_sha256']=newer['sha256']
            with patch('eeg_harness.research.working_memory_issue61_live.candidate_manifest',return_value=newer):
                with self.assertRaises(StageBudgetExhausted):register_candidate(raw,p,a,'TEST-final',rationale={'new_real_root_cause_evidence':'TEST'},scope=CONTINUATION_SCOPE,test_only=True)
                register_candidate(raw,p,a,'TEST-final',rationale={'new_real_root_cause_evidence':'TEST'},scope=CONTINUATION_SCOPE,final=True,test_only=True)
            newer['files']['src/eeg_harness/agent.py']='TEST-third';newer['sha256']=recovery.digest(newer['files']);a['mechanism_gate']['source_sha256']=newer['sha256']
            with patch('eeg_harness.research.working_memory_issue61_live.candidate_manifest',return_value=newer):
                with self.assertRaises(StageBudgetExhausted):register_candidate(raw,p,a,'TEST-third',rationale={'new_real_root_cause_evidence':'TEST'},scope=CONTINUATION_SCOPE,final=True,test_only=True)
            old=next(r for r in _rows(p) if r.get('candidate_id')=='TEST-old-final');manifest={k:old[k] for k in ('source','runtime','data')}
            with self.assertRaises(StageBudgetExhausted):admit_candidate_session(p,_rows(p),cases['T05'],manifest,a,'TEST-old-final',True)

    def test_future_coverage_and_scope_attempt_hard_bound_without_new_pool(self):
        with tempfile.TemporaryDirectory() as td:
            raw,p,a,prefix,source=fixture(Path(td))
            with patch('eeg_harness.research.working_memory_issue61_live.candidate_manifest',return_value=source):
                c=register_candidate(raw,p,a,'TEST-new',rationale={'design':'TEST'},scope=CONTINUATION_SCOPE,test_only=True)
            rows=_rows(p)
            self.assertTrue(continuation_request_fits(rows,'TEST-new',1,1000,Decimal('2')))
            self.assertFalse(continuation_request_fits(rows,'TEST-new',1,3000000,Decimal('2')))
            self.assertFalse(continuation_request_fits(rows,'TEST-new',1,1000,Decimal('3.5')))
            rows+=[{'event':'session_started','candidate_id':'TEST-new','case':'M01','execution_id':'TEST-run'},
                {'event':'candidate_final_frozen','candidate_id':'TEST-new'}]
            rows += [{'event':'reserved','request_id':f'TEST-scope-{i}','context':{'phase':'development'},'reserved_tokens':0,
                'recovery':{'execution_id':'TEST-run'}} for i in range(120)]
            self.assertFalse(continuation_request_fits(rows,'TEST-new',1,1,Decimal('2')))

if __name__=='__main__':unittest.main()
