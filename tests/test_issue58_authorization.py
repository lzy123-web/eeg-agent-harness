"""Approved second amendment on TEST ledgers; no network or formal writes."""
from copy import deepcopy
from decimal import Decimal
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from eeg_harness.research.working_memory_issue55_live import (
    MoneyBudgetClient, apply_authorization_revision, authorization_limits,
    LIVE_GRANT, LIVE_REVISION, LIVE_CAPS, GRANT, run_session)
from eeg_harness.research.integrated_method.v2_validation import JournaledBudgetClient
from eeg_harness.research.task_memory_issue39_budget import _rows, _append, StageBudgetExhausted
from eeg_harness.llm import LLMServiceError
from test_issue57_authorization import seeded
from test_issue55_live import setup


def live_seed(root, actions=None):
    def prices(*args):
        p,a=setup(*args);a['input_usd_per_million']='0.3'
        return p,a
    with patch('test_issue57_authorization.setup',side_effect=prices):
        raw,p,a,c,proof=seeded(root,actions)
    apply_authorization_revision(raw,p,a,proof,test_only=True)
    for i in range(77):
        tokens=(1234297-5760)//77+(i<(1234297-5760)%77)
        ident=f'TEST-later-{i}'
        _append(p,{'event':'reserved','request_id':ident,'context':{'phase':'development'},
            'reserved_tokens':20000,'output_cap':2200,**c.reservation_metadata(20000)})
        _append(p,{'event':'received','request_id':ident,'response_model_reported':raw.model,
            'total_tokens':tokens,'usage':{'prompt_tokens':tokens-20,'completion_tokens':20,'total_tokens':tokens}})
    c.settle_pending()
    new={'grant':GRANT,'additional_grant':LIVE_GRANT,'revision_id':LIVE_REVISION,
         'new_limits':deepcopy(LIVE_CAPS),'test_only':True,'prefix_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    return raw,p,a,c,new


def client(raw,p,a,root):
    return MoneyBudgetClient(JournaledBudgetClient(raw,root/'responses'),p,a,'development',
                             request_journal=root/'requests',test_only=True)


class LiveContinuationGrantTest(unittest.TestCase):
    def test_chain_prefix_idempotence_restart_and_live_driver_final_lease(self):
        from test_issue55_live import case_and_actions
        with tempfile.TemporaryDirectory() as td:
            case,actions=case_and_actions()
            root=Path(td);raw,p,a,c,proof=live_seed(root,actions)
            prefix=p.read_bytes();r=apply_authorization_revision(raw,p,a,proof,test_only=True)
            self.assertEqual(r['prior_usage'],[125,1234297]);self.assertTrue(p.read_bytes().startswith(prefix))
            before=p.read_bytes();self.assertEqual(apply_authorization_revision(raw,p,a,proof,test_only=True),r)
            self.assertEqual(p.read_bytes(),before)
            results=run_session(raw,p,a,case,root/'run',test_only=True)
            self.assertEqual([r['stop_reason'] for r in results],['completed','completed'])
            self.assertTrue(any(r['event']=='final_lease_decision' for r in _rows(p)))
            self.assertEqual(client(raw,p,a,root).caps,LIVE_CAPS)
            before=p.read_bytes();self.assertEqual(apply_authorization_revision(raw,p,a,proof,test_only=True),r)
            self.assertEqual(p.read_bytes(),before)
            with self.assertRaises(StageBudgetExhausted):
                run_session(raw,p,a,{},root/'confirmation',phase='confirmation',test_only=True)

    def test_conflicts_prefix_safety_and_old_close_guards(self):
        for defect in ('url','id','cap','prefix','stage_closed','safety_stop','confirmation_frozen','unsettled','runtime'):
            with self.subTest(defect=defect),tempfile.TemporaryDirectory() as td:
                raw,p,a,c,proof=live_seed(Path(td))
                if defect=='url':proof['additional_grant']='TEST-unapproved'
                elif defect=='id':proof['revision_id']='TEST-unapproved'
                elif defect=='cap':proof['new_limits']['development'][0]+=19
                elif defect=='prefix':proof['prefix_sha256']='wrong'
                elif defect=='runtime':raw.timeout+=1
                elif defect=='unsettled':
                    _append(p,{'event':'reserved','request_id':'TEST-pending','context':{'phase':'development'},
                        'reserved_tokens':1000,'output_cap':2200,**c.reservation_metadata(1000)})
                else:_append(p,{'event':defect})
                with self.assertRaises(StageBudgetExhausted):apply_authorization_revision(raw,p,a,proof,test_only=True)
                self.assertEqual(sum(r['event']=='authorization_revised' for r in _rows(p)),1)
                self.assertEqual(raw.request_count,0)

    def test_absolute_calls_tokens_stage_money_and_duplicate_chain(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);raw,p,a,c,proof=live_seed(root)
            apply_authorization_revision(raw,p,a,proof,test_only=True);c=client(raw,p,a,root);rows=_rows(p)
            self.assertTrue(c._fits(rows,72,1));self.assertFalse(c._fits(rows,73,1))
            self.assertTrue(c._fits(rows,1,1000000));self.assertFalse(c._fits(rows,1,1000001))
            costly=deepcopy(rows)
            # Keep absolute $3 available: the stage $1.20 must still stop.
            costly.append({'event':'reserved','request_id':'TEST-expensive','context':{'phase':'development'},
                           'reserved_tokens':1,'reserved_usd':'1.20'})
            self.assertFalse(c._fits(costly,1,1))
            _append(p,deepcopy(next(r for r in reversed(rows) if r['event']=='authorization_revised')))
            with self.assertRaises(StageBudgetExhausted):authorization_limits(p,_rows(p))

    def test_unknown_usage_and_model_charge_reservation_and_stop(self):
        for mode in ('usage','model'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as td:
                root=Path(td);raw,p,a,c,proof=live_seed(root)
                apply_authorization_revision(raw,p,a,proof,test_only=True);c=client(raw,p,a,root)
                if mode=='usage':raw.missing_usage=True
                else:raw.last_response_model='TEST-unapproved'
                with self.assertRaises(LLMServiceError):c.complete([{'role':'user','content':'TEST'}],[])
                self.assertEqual(raw.request_count,1)
                rows=_rows(p);last=next(r for r in reversed(rows) if r['event']=='money_settled')
                reserved=next(r for r in reversed(rows) if r['event']=='reserved')
                self.assertEqual(Decimal(last['charged_usd']),Decimal(reserved['reserved_usd']))
                self.assertTrue(last['reconciliation_required'])
                with self.assertRaises(StageBudgetExhausted):apply_authorization_revision(raw,p,a,proof,test_only=True)

