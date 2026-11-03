"""Fifth grant, temporary TEST journals only."""
from copy import deepcopy
from decimal import Decimal
import hashlib,tempfile,unittest
from pathlib import Path
from eeg_harness.research.working_memory_issue55_live import *
from eeg_harness.research.task_memory_issue39_budget import _append,_rows,StageBudgetExhausted
from test_issue59_closeout_authorization import closeout_seed
from test_issue58_authorization import client

class GrantTest(unittest.TestCase):
    def test_fifth_grant_fixed_snapshot_limits_original_history_and_final_lease(self):
        from test_issue55_live import case_and_actions
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);case,actions=case_and_actions();raw,p,a,c,proof=closeout_seed(root,actions)
            apply_authorization_revision(raw,p,a,proof,test_only=True);c=client(raw,p,a,root)
            for i in range(21):
                tokens=292911//21+(i<292911%21);ident=f'TEST-issue60-history-{i}'
                _append(p,{'event':'reserved','request_id':ident,'context':{'phase':'development'},'reserved_tokens':20000,'output_cap':2200,**c.reservation_metadata(20000)})
                _append(p,{'event':'received','request_id':ident,'response_model_reported':raw.model,'total_tokens':tokens,'usage':{'prompt_tokens':tokens-20,'completion_tokens':20,'total_tokens':tokens}})
            c.settle_pending();prefix=p.read_bytes()
            proof.update(revision_id=INTERFACE_REVISION,additional_grant=INTERFACE_GRANT,new_limits=deepcopy(INTERFACE_CAPS),prefix_sha256=hashlib.sha256(prefix).hexdigest())
            bad=deepcopy(proof);bad['new_limits']['development'][0]+=27
            with self.assertRaises(StageBudgetExhausted):apply_authorization_revision(raw,p,a,bad,test_only=True)
            rec=apply_authorization_revision(raw,p,a,proof,test_only=True);c=client(raw,p,a,root)
            self.assertEqual(rec['prior_usage'],[305,3879334]);self.assertTrue(p.read_bytes().startswith(prefix))
            self.assertEqual(c.stage_money_start,Decimal(rec['prior_usd']))
            rows=_rows(p);self.assertTrue(c._fits(rows,192,1));self.assertFalse(c._fits(rows,193,1))
            self.assertFalse(c._fits(rows,1,3500001))
            costly=rows+[{'event':'reserved','request_id':'TEST-cost','context':{'phase':'development'},'reserved_tokens':1,'reserved_usd':'1.70'}]
            self.assertFalse(c._fits(costly,1,1))
            result=run_session(raw,p,a,case,root/'run',test_only=True)
            self.assertEqual([r['stop_reason'] for r in result],['completed','completed'])
            before=p.read_bytes();self.assertEqual(apply_authorization_revision(raw,p,a,proof,test_only=True),rec);self.assertEqual(before,p.read_bytes())
            with self.assertRaises(StageBudgetExhausted):run_session(raw,p,a,{},root/'confirm',phase='confirmation',test_only=True)
