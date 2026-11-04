"""Explicit amended grant on TEST-only cumulative ledgers; no service calls."""
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest
from eeg_harness.research.working_memory_issue55_live import (
    MoneyBudgetClient, apply_authorization_revision, authorization_limits, GRANT,
    ADDITIONAL_GRANT, REVISION_ID, ORIGINAL_CAPS, REVISED_CAPS, run_session)
from eeg_harness.research.task_memory_issue39_budget import _append, _rows, StageBudgetExhausted
from eeg_harness.research.integrated_method.v2_validation import JournaledBudgetClient
from eeg_harness.llm import LLMServiceError
from test_issue55_live import RawFake, setup, case_and_actions
from test_working_memory import finish


def seeded(root,actions=None):
    raw=RawFake(actions or [finish()]);ledger,a=setup(root,raw)
    c=MoneyBudgetClient(JournaledBudgetClient(raw,root/'seed-responses'),ledger,a,'development',request_journal=root/'seed-requests',test_only=True)
    for i in range(48):
        _append(ledger,{'event':'reserved','request_id':f'TEST-history-{i}','context':{'phase':'development'},
            'reserved_tokens':1000,'output_cap':2200,**c.reservation_metadata(1000)})
        _append(ledger,{'event':'received','request_id':f'TEST-history-{i}','response_model_reported':raw.model,
            'total_tokens':120,'usage':{'prompt_tokens':100,'completion_tokens':20,'total_tokens':120}})
    c.settle_pending()
    _append(ledger,{'event':'diagnostic_review','status':'failed'})
    proof={'grant':GRANT,'additional_grant':ADDITIONAL_GRANT,'revision_id':REVISION_ID,'new_limits':deepcopy(REVISED_CAPS),
        'test_only':True,'prefix_sha256':hashlib.sha256(ledger.read_bytes()).hexdigest()}
    return raw,ledger,a,c,proof


class AuthorizationTest(unittest.TestCase):
    def test_old_limit_explicit_revision_restart_and_real_agent_end_to_end(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);case,actions=case_and_actions();raw,p,a,c,proof=seeded(root,actions)
            with self.assertRaises(LLMServiceError):c.complete([],[])
            self.assertEqual(raw.request_count,0)
            # A rejected reservation is real audit history; pin the new prefix.
            proof['prefix_sha256']=hashlib.sha256(p.read_bytes()).hexdigest();prefix=p.read_bytes()
            revised=apply_authorization_revision(raw,p,a,proof,test_only=True)
            self.assertEqual(revised['prior_usage'],[48,5760]);self.assertTrue(p.read_bytes().startswith(prefix))
            before=p.read_bytes();self.assertEqual(apply_authorization_revision(raw,p,a,proof,test_only=True),revised)
            self.assertEqual(p.read_bytes(),before)
            run_session(raw,p,a,case,root/'run',test_only=True)
            self.assertEqual(raw.request_count,6)
            self.assertEqual(sum(r['event']=='reserved' for r in _rows(p)),54)
            self.assertTrue(any(r['event']=='final_lease_decision' for r in _rows(p)))
            restarted=MoneyBudgetClient(JournaledBudgetClient(raw,root/'restart'),p,a,'development',request_journal=root/'req',test_only=True)
            self.assertEqual(restarted.caps,REVISED_CAPS)
            self.assertEqual(apply_authorization_revision(raw,p,a,proof,test_only=True),revised)
            with self.assertRaises(StageBudgetExhausted):run_session(raw,p,a,case,root/'forbidden',phase='confirmation',test_only=True)

    def test_conflicts_stop_markers_and_unchanged_runtime_cannot_be_bypassed(self):
        for defect in ('grant','limits','prefix','closed','safety','freeze','unsettled','runtime'):
            with self.subTest(defect=defect),tempfile.TemporaryDirectory() as td:
                raw,p,a,c,proof=seeded(Path(td))
                if defect=='grant':proof['additional_grant']='TEST wrong grant'
                if defect=='limits':proof['new_limits']['development'][0]=145
                if defect=='prefix':proof['prefix_sha256']='wrong'
                if defect in ('closed','safety','freeze'):
                    _append(p,{'event':{'closed':'stage_closed','safety':'safety_stop','freeze':'confirmation_frozen'}[defect]})
                if defect=='unsettled':_append(p,{'event':'reserved','request_id':'TEST-pending','context':{'phase':'development'},'reserved_tokens':1000,'output_cap':2200,**c.reservation_metadata(1000)})
                if defect=='runtime':raw.timeout+=1
                with self.assertRaises(StageBudgetExhausted):apply_authorization_revision(raw,p,a,proof,test_only=True)
                self.assertFalse(any(r['event']=='authorization_revised' for r in _rows(p)))
                self.assertEqual(raw.request_count,0)

    def test_cumulative_caps_and_prefix_integrity(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);raw,p,a,c,proof=seeded(root)
            apply_authorization_revision(raw,p,a,proof,test_only=True)
            c=MoneyBudgetClient(JournaledBudgetClient(raw,root/'r'),p,a,'development',request_journal=root/'q',test_only=True)
            rows=_rows(p)
            self.assertTrue(c._fits(rows,96,1));self.assertFalse(c._fits(rows,97,1))
            self.assertTrue(c._fits(rows,1,2000000-5760));self.assertFalse(c._fits(rows,1,2000000-5760+1))
            costly=deepcopy(rows);next(r for r in costly if r['event']=='money_settled')['charged_usd']='3'
            self.assertFalse(c._fits(costly,1,1))
            for phase,calls,tokens in [('confirmation',193,0),('confirmation',1,6000000)]:
                self.assertFalse(c._fits(rows+[{'event':'reserved','request_id':'TEST-other-pool','context':{'phase':phase},'reserved_tokens':tokens,'reserved_usd':'0'}],calls,1))
            _append(p,deepcopy(next(r for r in rows if r['event']=='authorization_revised')))
            with self.assertRaises(StageBudgetExhausted):authorization_limits(p,_rows(p))

    def test_amendment_keeps_unknown_usage_and_unexpected_model_hard_stops(self):
        for mode in ('usage','model'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as td:
                root=Path(td);raw,p,a,c,proof=seeded(root)
                apply_authorization_revision(raw,p,a,proof,test_only=True)
                c=MoneyBudgetClient(JournaledBudgetClient(raw,root/'r'),p,a,'development',request_journal=root/'q',test_only=True)
                if mode=='usage':raw.missing_usage=True
                else:raw.last_response_model='TEST-UNAUTHORIZED'
                with self.assertRaises(LLMServiceError):c.complete([{'role':'user','content':'TEST'}],[])
                self.assertEqual(raw.request_count,1)
                self.assertTrue(any(r['event']=='safety_stop' for r in _rows(p)))
                last=[r for r in _rows(p) if r['event']=='money_settled'][-1]
                self.assertTrue(last['reconciliation_required'])
                with self.assertRaises(StageBudgetExhausted):apply_authorization_revision(raw,p,a,proof,test_only=True)


if __name__=='__main__':unittest.main()
