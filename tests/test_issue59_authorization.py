"""Third direct-user authorization, exclusively on explicit TEST journals."""
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest
from decimal import Decimal
from eeg_harness.llm import LLMServiceError
from eeg_harness.research.working_memory_issue55_live import (
    apply_authorization_revision, SOURCE_GRANT, SOURCE_REVISION, SOURCE_CAPS, run_session)
from eeg_harness.research.task_memory_issue39_budget import _append, _rows, StageBudgetExhausted
from test_issue58_authorization import live_seed, client


def source_seed(root, actions=None):
    raw,p,a,c,proof=live_seed(root,actions)
    apply_authorization_revision(raw,p,a,proof,test_only=True)
    c=client(raw,p,a,root)
    for i in range(42):
        tokens=642821//42+(i<642821%42);ident=f'TEST-source-history-{i}'
        _append(p,{'event':'reserved','request_id':ident,'context':{'phase':'development'},
            'reserved_tokens':20000,'output_cap':2200,**c.reservation_metadata(20000)})
        _append(p,{'event':'received','request_id':ident,'response_model_reported':raw.model,
            'total_tokens':tokens,'usage':{'prompt_tokens':tokens-20,'completion_tokens':20,'total_tokens':tokens}})
    c.settle_pending()
    proof.update(additional_grant=SOURCE_GRANT,revision_id=SOURCE_REVISION,new_limits=deepcopy(SOURCE_CAPS),
                 prefix_sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    return raw,p,a,c,proof


class SourceGrantTest(unittest.TestCase):
    def test_unknown_usage_and_unexpected_model_keep_conservative_charge_and_stop(self):
        for defect in ('usage','model'):
            with self.subTest(defect=defect),tempfile.TemporaryDirectory() as td:
                root=Path(td);raw,p,a,c,proof=source_seed(root)
                apply_authorization_revision(raw,p,a,proof,test_only=True);c=client(raw,p,a,root)
                if defect=='usage':raw.missing_usage=True
                else:raw.last_response_model='TEST-unapproved-model'
                with self.assertRaises(LLMServiceError):c.complete([{'role':'user','content':'TEST'}],[])
                rows=_rows(p);reserved=next(r for r in reversed(rows) if r['event']=='reserved')
                settled=next(r for r in reversed(rows) if r['event']=='money_settled')
                self.assertEqual(Decimal(settled['charged_usd']),Decimal(reserved['reserved_usd']))
                self.assertTrue(settled['reconciliation_required']);self.assertEqual(raw.request_count,1)
                self.assertFalse(c._fits(rows,1,1))

    def test_preserves_chain_restart_driver_final_lease_and_absolute_limits(self):
        from test_issue55_live import case_and_actions
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);case,actions=case_and_actions();raw,p,a,c,proof=source_seed(root,actions)
            prefix=p.read_bytes();receipt=apply_authorization_revision(raw,p,a,proof,test_only=True)
            self.assertEqual(receipt['prior_usage'],[167,1877118]);self.assertTrue(p.read_bytes().startswith(prefix))
            c=client(raw,p,a,root);self.assertEqual(c.caps,SOURCE_CAPS)
            rows=_rows(p)
            self.assertTrue(c._fits(rows,144,1));self.assertFalse(c._fits(rows,145,1))
            self.assertFalse(c._fits(rows,1,3000001))
            costly=deepcopy(rows)+[{'event':'reserved','request_id':'TEST-expense',
                'context':{'phase':'development'},'reserved_tokens':1,'reserved_usd':'2.16'}]
            self.assertFalse(c._fits(costly,1,1))
            results=run_session(raw,p,a,case,root/'run',test_only=True)
            self.assertEqual([r['stop_reason'] for r in results],['completed','completed'])
            self.assertTrue(any(r['event']=='final_lease_decision' for r in _rows(p)))
            before=p.read_bytes();self.assertEqual(apply_authorization_revision(raw,p,a,proof,test_only=True),receipt)
            self.assertEqual(p.read_bytes(),before)
            with self.assertRaises(StageBudgetExhausted):run_session(raw,p,a,{},root/'confirm',phase='confirmation',test_only=True)

    def test_new_receipt_cannot_bypass_old_safety_or_pending_transactions(self):
        for defect in ('prefix','cap','url','runtime','unsettled','safety_stop','stage_closed'):
            with self.subTest(defect=defect),tempfile.TemporaryDirectory() as td:
                root=Path(td);raw,p,a,c,proof=source_seed(root)
                if defect=='prefix':proof['prefix_sha256']='wrong'
                elif defect=='cap':proof['new_limits']['development'][0]+=19
                elif defect=='url':proof['additional_grant']='TEST-unapproved'
                elif defect=='runtime':raw.timeout+=1
                elif defect=='unsettled':_append(p,{'event':'reserved','request_id':'TEST-unsettled',
                    'context':{'phase':'development'},'reserved_tokens':1000,'output_cap':2200,**c.reservation_metadata(1000)})
                else:_append(p,{'event':defect})
                before=p.read_bytes()
                with self.assertRaises(StageBudgetExhausted):apply_authorization_revision(raw,p,a,proof,test_only=True)
                self.assertTrue(p.read_bytes().startswith(before));self.assertEqual(raw.request_count,0)
                self.assertEqual(sum(r['event']=='authorization_revised' for r in _rows(p)),2)
                if defect=='unsettled':
                    self.assertTrue(any(r.get('reconciliation_required') for r in _rows(p)))
                else:self.assertEqual(p.read_bytes(),before)
