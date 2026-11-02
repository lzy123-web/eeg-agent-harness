"""Call-only v5 closeout amendment on temporary, explicitly TEST journals."""
from copy import deepcopy
from decimal import Decimal
import hashlib
from pathlib import Path
import tempfile
import unittest

from eeg_harness.llm import LLMServiceError
from eeg_harness.research.working_memory_issue55_live import (
    apply_authorization_revision, authorization_limits, run_session,
    SOURCE_REVISION, CLOSEOUT_GRANT, CLOSEOUT_REVISION, CLOSEOUT_CAPS)
from eeg_harness.research.task_memory_issue39_budget import _append, _rows, StageBudgetExhausted
from test_issue58_authorization import client
from test_issue59_authorization import source_seed


def closeout_seed(root, actions=None):
    raw,p,a,c,proof=source_seed(root,actions)
    apply_authorization_revision(raw,p,a,proof,test_only=True)
    c=client(raw,p,a,root)
    for i in range(117):
        tokens=1709305//117+(i<1709305%117);ident=f'TEST-closeout-history-{i}'
        _append(p,{'event':'reserved','request_id':ident,'context':{'phase':'development'},
            'reserved_tokens':20000,'output_cap':2200,**c.reservation_metadata(20000)})
        _append(p,{'event':'received','request_id':ident,'response_model_reported':raw.model,
            'total_tokens':tokens,'usage':{'prompt_tokens':tokens-20,'completion_tokens':20,'total_tokens':tokens}})
    c.settle_pending()
    proof.update(additional_grant=CLOSEOUT_GRANT,revision_id=CLOSEOUT_REVISION,
        new_limits=deepcopy(CLOSEOUT_CAPS),prefix_sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    return raw,p,a,c,proof


class CloseoutGrantTest(unittest.TestCase):
    def test_exact_increment_money_origin_idempotent_restart_and_two_turn_driver(self):
        from test_issue55_live import case_and_actions
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);case,actions=case_and_actions();raw,p,a,c,proof=closeout_seed(root,actions)
            prefix=p.read_bytes();receipt=apply_authorization_revision(raw,p,a,proof,test_only=True)
            self.assertTrue(p.read_bytes().startswith(prefix));self.assertEqual(receipt['prior_usage'],[284,3586423])
            c=client(raw,p,a,root);rows=_rows(p)
            source=next(r for r in rows if r.get('revision_id')==SOURCE_REVISION)
            self.assertEqual(c.stage_money_start,Decimal(source['prior_usd']))
            self.assertEqual(c.caps,CLOSEOUT_CAPS)
            self.assertTrue(c._fits(rows,48,1));self.assertFalse(c._fits(rows,49,1))
            self.assertTrue(c._fits(rows,1,1290695));self.assertFalse(c._fits(rows,1,1290696))
            costly=deepcopy(rows)+[{'event':'reserved','request_id':'TEST-cost',
                'context':{'phase':'development'},'reserved_tokens':1,'reserved_usd':'1.7'}]
            self.assertFalse(c._fits(costly,1,1))
            results=run_session(raw,p,a,case,root/'run',test_only=True)
            self.assertEqual([r['stop_reason'] for r in results],['completed','completed'])
            self.assertTrue(any(r['event']=='final_lease_decision' for r in _rows(p)))
            before=p.read_bytes();self.assertEqual(apply_authorization_revision(raw,p,a,proof,test_only=True),receipt)
            self.assertEqual(p.read_bytes(),before)
            self.assertEqual(client(raw,p,a,root).stage_money_start,c.stage_money_start)
            with self.assertRaises(StageBudgetExhausted):run_session(raw,p,a,{},root/'confirm',phase='confirmation',test_only=True)
            _append(p,receipt)
            with self.assertRaises(StageBudgetExhausted):authorization_limits(p,_rows(p))

    def test_conflicts_and_existing_stops_or_pending_cannot_be_cleared(self):
        for defect in ('prefix','calls','tokens','money','url','runtime','unsettled','safety_stop','stage_closed','confirmation_frozen'):
            with self.subTest(defect=defect),tempfile.TemporaryDirectory() as td:
                raw,p,a,c,proof=closeout_seed(Path(td))
                if defect=='prefix':proof['prefix_sha256']='wrong'
                elif defect=='calls':proof['new_limits']['development'][0]+=27
                elif defect=='tokens':proof['new_limits']['tokens']+=1
                elif defect=='money':proof['new_limits']['stage_usd']='3'
                elif defect=='url':proof['additional_grant']='TEST-unapproved'
                elif defect=='runtime':raw.timeout+=1
                elif defect=='unsettled':_append(p,{'event':'reserved','request_id':'TEST-unsettled',
                    'context':{'phase':'development'},'reserved_tokens':1000,'output_cap':2200,**c.reservation_metadata(1000)})
                else:_append(p,{'event':defect})
                before=p.read_bytes()
                with self.assertRaises(StageBudgetExhausted):apply_authorization_revision(raw,p,a,proof,test_only=True)
                self.assertTrue(p.read_bytes().startswith(before));self.assertEqual(raw.request_count,0)
                self.assertEqual(sum(r['event']=='authorization_revised' for r in _rows(p)),3)

    def test_unknown_usage_or_model_retains_reservation_and_blocks_following_call(self):
        for defect in ('usage','model'):
            with self.subTest(defect=defect),tempfile.TemporaryDirectory() as td:
                root=Path(td);raw,p,a,c,proof=closeout_seed(root)
                apply_authorization_revision(raw,p,a,proof,test_only=True);c=client(raw,p,a,root)
                if defect=='usage':raw.missing_usage=True
                else:raw.last_response_model='TEST-unapproved-model'
                with self.assertRaises(LLMServiceError):c.complete([{'role':'user','content':'TEST'}],[])
                rows=_rows(p);reserved=next(r for r in reversed(rows) if r['event']=='reserved')
                settled=next(r for r in reversed(rows) if r['event']=='money_settled')
                self.assertEqual(Decimal(settled['charged_usd']),Decimal(reserved['reserved_usd']))
                self.assertTrue(settled['reconciliation_required']);self.assertEqual(raw.request_count,1)
                self.assertFalse(c._fits(rows,1,1))
