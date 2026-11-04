"""Issue62 scope only: temporary TEST ledger, simulated prices, no funding."""
import tempfile,unittest
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from test_issue61_continuation_scope import fixture
from test_issue60_recovery import Faults
from test_issue60_convergence import compact_steps
from eeg_harness.research.working_memory_issue61_live import *
from eeg_harness.research.task_memory_issue39_budget import _rows,_append,StageBudgetExhausted
from eeg_harness.research.working_memory_issue55_live import run_session

def seed62(root):
    raw,p,a,prefix,source=fixture(root)
    with patch('eeg_harness.research.working_memory_issue61_live.candidate_manifest',return_value=source):
        register_candidate(raw,p,a,'TEST-61',rationale={'design':'TEST'},scope=CONTINUATION_SCOPE,test_only=True)
        _append(p,{'event':'session_started','candidate_id':'TEST-61','case':'M01','execution_id':'TEST-61-done','phase':'development'})
        _append(p,{'event':'recovery_session_finished','execution_id':'TEST-61-done'})
        register_candidate(raw,p,a,'TEST-61',rationale={'decision':'TEST'},scope=CONTINUATION_SCOPE,final=True,test_only=True)
    prefix=p.read_bytes();register_continuation(raw,p,a,scope=SIMPLIFICATION_SCOPE,test_only=True)
    source=deepcopy(source);source['files']['src/eeg_harness/agent.py']='TEST-62-new-science';source['sha256']=recovery.digest(source['files']);a['mechanism_gate']['source_sha256']=source['sha256']
    return raw,p,a,prefix,source
class SimplificationScopeTest(unittest.TestCase):
    def test_six_funds_idempotent_scope_old_freeze_and_safety(self):
        with tempfile.TemporaryDirectory() as td:
            raw,p,a,prefix,source=seed62(Path(td));before=p.read_bytes();register_continuation(raw,p,a,scope=SIMPLIFICATION_SCOPE,test_only=True);self.assertEqual(before,p.read_bytes());self.assertTrue(before.startswith(prefix));rows=_rows(p)
            self.assertEqual(sum(r['event']=='authorization_revised' for r in rows),6);self.assertEqual(sum(r['event']=='scope_permission' for r in rows),2)
            for event in ('safety_stop','stage_closed','confirmation_frozen'):
                q=Path(td)/event;q.write_bytes(before);_append(q,{'event':event,'request_id':'TEST-unhandled'})
                with self.assertRaises(StageBudgetExhausted):register_continuation(raw,q,a,scope=SIMPLIFICATION_SCOPE,test_only=True)
            q=Path(td)/'unsent';q.write_bytes(before);_append(q,{'event':'reserved','request_id':'TEST-unsettled','reserved_tokens':1,'context':{'phase':'development'}})
            with self.assertRaises(StageBudgetExhausted):register_continuation(raw,q,a,scope=SIMPLIFICATION_SCOPE,test_only=True)
    def test_fake_two_turns_final_same_science_no_resample(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);raw,p,a,prefix,source=seed62(root);raw=Faults(set(),[s for t in compact_steps('T05') for s in t])
            with patch('eeg_harness.research.working_memory_issue61_live.candidate_manifest',return_value=source),patch('eeg_harness.research.working_memory_issue55_live.candidate_manifest',return_value=source):
                register_candidate(raw,p,a,'TEST-62',rationale={'design':'TEST minimal delta'},scope=SIMPLIFICATION_SCOPE,test_only=True)
                case=next(c for c in development_cases() if c['id']=='T05');rs=run_session(raw,p,a,case,root/'run',candidate_id='TEST-62',test_only=True)
                self.assertEqual([r['stop_reason'] for r in rs],['completed','completed'])
                register_candidate(raw,p,a,'TEST-62',rationale={'no_revision':'TEST'},scope=SIMPLIFICATION_SCOPE,final=True,test_only=True)
                with self.assertRaises(StageBudgetExhausted):run_session(raw,p,a,case,root/'repeat',candidate_id='TEST-62',test_only=True)
            rows=_rows(p);self.assertEqual({r['request_id'] for r in rows if r['event']=='reserved'},{r['request_id'] for r in rows if r['event']=='money_settled'});self.assertTrue(any(r['event']=='final_lease_decision' for r in rows));self.assertEqual(sum(r['event']=='authorization_revised' for r in rows),6)
    def test_planning_reserve_and_hard_91_bound_not_new_budget(self):
        with tempfile.TemporaryDirectory() as td:
            raw,p,a,prefix,source=seed62(Path(td))
            with patch('eeg_harness.research.working_memory_issue61_live.candidate_manifest',return_value=source):
                register_candidate(raw,p,a,'TEST-62',rationale={'design':'TEST'},scope=SIMPLIFICATION_SCOPE,test_only=True)
            rows=_rows(p);pending,reserve=reserve_coverage(rows,[],True,scope=SIMPLIFICATION_SCOPE);self.assertEqual(reserve,{'calls':72,'tokens':1200000,'usd':'0.500'})
            self.assertFalse(continuation_request_fits(rows,'TEST-62',1,9000000,Decimal('2')));self.assertFalse(continuation_request_fits(rows,'TEST-62',1,1,Decimal('3.5')))
            rows+=[{'event':'session_started','candidate_id':'TEST-62','case':'T05','execution_id':'TEST-62-run'}]
            rows += [{'event':'reserved','request_id':f'TEST-62-{i}','context':{'phase':'development'},'reserved_tokens':0,'recovery':{'execution_id':'TEST-62-run'}} for i in range(91)]
            self.assertFalse(continuation_request_fits(rows,'TEST-62',1,1,Decimal('2')))
            self.assertEqual(sum(r['event']=='authorization_revised' for r in rows),6)
if __name__=='__main__':unittest.main()
