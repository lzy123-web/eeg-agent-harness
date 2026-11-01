"""Offline end-to-end Issue55 live-driver gates; no real credentials or ledger."""
import json
from pathlib import Path
import tempfile
import unittest
from eeg_harness.research.working_memory_issue55_live import GRANT, MoneyBudgetClient, run_session, money_totals
from eeg_harness.research.task_memory_issue39_budget import _append,_rows,StageBudgetExhausted
from eeg_harness.research.integrated_method.v2_validation import JournaledBudgetClient
from eeg_harness.llm import LLMServiceError
from eeg_harness.research.working_memory_issue50 import FINISH_CHOICE
from eeg_harness.research.working_memory_issue52 import protocol as development_protocol, controlled_steps
from eeg_harness.research.working_memory_issue55_live import scored_case
from test_task_plan_agent import InspectableScriptedClient,node,delivery
from test_working_memory import finish

class RawFake:
    is_test_client=True
    model='TEST-ONLY-NOT-A-SERVICE'
    max_tokens=2200
    max_retries=0
    timeout=10
    thinking='disabled'
    def __init__(self,actions,fail=False,missing_usage=False):
        self.inner=InspectableScriptedClient(actions)
        self.request_count=0
        self.total_usage={}
        self.finish_reasons=[]
        self.last_usage={}
        self.last_response_model=self.model
        self.last_finish_reason='tool_calls'
        self.fail,self.missing_usage=fail,missing_usage
    def complete(self,messages,tools,tool_choice='auto'):
        self.request_count+=1
        if self.fail:raise RuntimeError('TEST failure after reservation')
        result=self.inner.complete(messages,tools)
        self.last_usage={} if self.missing_usage else {'prompt_tokens':100,'completion_tokens':20,'total_tokens':120}
        self.total_usage={'total_tokens':self.request_count*120}
        return result


def setup(root,raw,rate='1.2'):
    ledger=root/'TEST-budget.jsonl'
    _append(ledger,{'event':'opened','stage':'issue55','test_only':True,'grant':GRANT,'reconciled':True,'rate_ceiling':rate})
    a={'grant':GRANT,'test_only':True,'model':raw.model,'accepted_response_models':[raw.model],
       'input_usd_per_million':rate,'output_usd_per_million':rate,'rate_source':'TEST SIMULATED PRICES, NOT BILLING'}
    return ledger,a


def case_and_actions():
    scope={'channels':['SYNTH-C1'],'start':0,'end':2}
    actions=[('plan_tasks',{'nodes':[node('a',[delivery('r','amplitude',scope)])]}),('amplitude',{}),finish(),
             ('plan_tasks',{'nodes':[node('p',[delivery('p','psd',scope)])]}),('psd',{}),finish()]
    case={'id':'TEST','requests':['记录A SYNTH-C1在0到2秒的RMS和alpha功率。','继续记录A SYNTH-C1在0到2秒的alpha功率。'],
        'evaluation_only':{'obligations':[{'key':k,'turn':1,'record':'A','capability':t,'scope':scope,'fields':[['SYNTH-C1',f]]}
         for k,t,f in [('r','amplitude','rms'),('p','psd','alpha')]]}}
    return case,actions

class LiveRunnerTest(unittest.TestCase):
    def test_real_agent_deadline_snapshots_native_journals_and_settlement(self):
        case,actions=case_and_actions()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);raw=RawFake(actions);ledger,a=setup(root,raw)
            results=run_session(raw,ledger,a,case,root/'run',test_only=True)
            self.assertEqual(len(results),2)
            first=json.loads((root/'run/turn-1.json').read_text(encoding='utf8'))
            second=json.loads((root/'run/turn-2.json').read_text(encoding='utf8'))
            self.assertFalse(first['score_at_deadline']['all_required_results_correct'])
            self.assertTrue(second['score_at_deadline']['all_required_results_correct'])
            self.assertIsNone(second['score_at_deadline']['whole_request_correct'])
            rows=_rows(ledger)
            self.assertEqual(sum(r['event']=='reserved' for r in rows),6)
            self.assertEqual(sum(r['event']=='money_settled' for r in rows),6)
            self.assertTrue(any(r['event']=='final_lease_decision' for r in rows))
            self.assertEqual(len(_rows(root/'run/requests.jsonl')),6)
            self.assertEqual(len(_rows(root/'run/responses.jsonl')),6)
            self.assertTrue(all('evaluation_only' not in json.dumps(r['messages']) for r in _rows(root/'run/requests.jsonl')))
            with self.assertRaises(FileExistsError):run_session(raw,ledger,a,case,root/'run',test_only=True)

    def test_failure_is_charged_and_stops_unsent_turn(self):
        case,_=case_and_actions()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);raw=RawFake([],fail=True);ledger,a=setup(root,raw)
            results=run_session(raw,ledger,a,case,root/'failed',test_only=True)
            self.assertEqual(len(results),1)
            self.assertEqual(raw.request_count,1)
            receipt=next(r for r in _rows(ledger) if r['event']=='money_settled')
            self.assertEqual(receipt['basis'],'conservative_reservation')
            self.assertGreater(float(receipt['charged_usd']),0)
            self.assertTrue((root/'failed/session-end.json').exists())
            self.assertFalse((root/'failed/turn-2.json').exists())

    def test_missing_usage_keeps_full_reservation(self):
        case,actions=case_and_actions()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);raw=RawFake(actions,missing_usage=True);ledger,a=setup(root,raw)
            run_session(raw,ledger,a,case,root/'missing',test_only=True)
            self.assertTrue(all(r['basis']=='conservative_reservation' for r in _rows(ledger) if r['event']=='money_settled'))

    def test_caps_prior_consumption_final_checkpoint_and_test_boundary(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);raw=RawFake([]);ledger,a=setup(root,raw)
            journal=JournaledBudgetClient(raw,root/'responses')
            client=MoneyBudgetClient(journal,ledger,a,'development',request_journal=root/'requests',test_only=True)
            self.assertFalse(client._fits([],49,1))
            self.assertFalse(client._fits([],1,2000001))
            prior=[{'event':'reserved','request_id':'prior','reserved_tokens':2500000,'context':{'phase':'confirmation'}}]
            self.assertFalse(client._fits(prior,1,1)) # US$3 exhausted despite free development tokens
            self.assertFalse(client._fits([{'event':'stage_closed'}],1,1))
            _append(ledger,{'event':'reserved','request_id':'prior','reserved_tokens':1996500,'context':{'phase':'development'}})
            _append(ledger,{'event':'received','request_id':'prior','total_tokens':1996500})
            # A small exact final snapshot fits; large normal decision does not.
            client.prepare_decision([{'role':'user','content':'x'*2000}],[],[{'role':'user','content':'stop'}],[])
            self.assertTrue(client.final_only)
            self.assertTrue(client.delivery_checkpoint)
            with self.assertRaises(LLMServiceError):client.complete([{'role':'user','content':'changed'}],[],FINISH_CHOICE)
            self.assertEqual(raw.request_count,0)
            with self.assertRaises(StageBudgetExhausted):
                MoneyBudgetClient(journal,ledger,a,'development',request_journal=root/'requests',test_only=False)

    def test_confirmation_is_one_shot_freezes_sources_and_blocks_development(self):
        case,actions=case_and_actions();case['id']='C01'
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);raw=RawFake(actions);ledger,a=setup(root,raw)
            run_session(raw,ledger,a,case,root/'confirm',phase='confirmation',test_only=True)
            for phase,ident in [('confirmation','C01'),('development','T04')]:
                case['id']=ident
                with self.assertRaises(StageBudgetExhausted):run_session(raw,ledger,a,case,root/ident,phase=phase,test_only=True)
            case['id']='C02';a['rate_source']='Changed after freeze'
            with self.assertRaises(StageBudgetExhausted):run_session(raw,ledger,a,case,root/'changed',phase='confirmation',test_only=True)

    def test_wrong_scope_stops_before_next_completion_and_restart(self):
        case,actions=case_and_actions()
        # Request authorizes the window, but it conflicts with the independent
        # frozen request inventory: emulate an evaluator catching a wrong run.
        case['evaluation_only']['obligations'][0]['scope']={'channels':['SYNTH-C1'],'start':2,'end':4}
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);raw=RawFake(actions);ledger,a=setup(root,raw)
            run_session(raw,ledger,a,case,root/'wrong',test_only=True)
            self.assertEqual(raw.request_count,2)
            self.assertTrue(any(r['event']=='safety_stop' for r in _rows(ledger)))
            with self.assertRaises(StageBudgetExhausted):run_session(raw,ledger,a,case,root/'again',test_only=True)

    def test_unexpected_response_model_and_invalid_usage_stop_and_keep_reservation(self):
        case,actions=case_and_actions()
        for invalid in ('model','usage'):
            with tempfile.TemporaryDirectory() as td:
                root=Path(td);raw=RawFake(actions);ledger,a=setup(root,raw)
                if invalid=='model':raw.last_response_model='UNAUTHORIZED'
                else:
                    original=raw.complete
                    def bad(*args,**kwargs):
                        value=original(*args,**kwargs);raw.last_usage['completion_tokens']=-20
                        return value
                    raw.complete=bad
                run_session(raw,ledger,a,case,root/'bad',test_only=True)
                self.assertEqual(raw.request_count,1)
                self.assertTrue(any(r['event']=='safety_stop' for r in _rows(ledger)))

    def test_exception_final_snapshot_and_restart_never_reset_prior_consumption(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);raw=RawFake([finish()]);ledger,a=setup(root,raw)
            for i in range(47):_append(ledger,{'event':'reserved','request_id':str(i),
                'reserved_tokens':10,'context':{'phase':'development'}})
            client=MoneyBudgetClient(JournaledBudgetClient(raw,root/'responses'),ledger,a,'development',request_journal=root/'requests',test_only=True)
            client.prepare_decision([{'role':'user','content':'normal'}],[],[{'role':'user','content':'final'}],[])
            self.assertTrue(client.final_only)
            client.complete(client.delivery_checkpoint['messages'],[],FINISH_CHOICE)
            client2=MoneyBudgetClient(JournaledBudgetClient(raw,root/'responses'),ledger,a,'development',request_journal=root/'requests',test_only=True)
            self.assertFalse(client2._fits(_rows(ledger),1,1))
            self.assertEqual(raw.request_count,1)

    def test_development_inventory_preserves_t04_missing_result_and_real_event_oracle(self):
        for ident in ('T03','T04','T06','T07'):
            case=next(c for c in development_protocol()['cases'] if c['id']==ident)
            actions=[action for turn in controlled_steps(ident) for action in turn]
            with tempfile.TemporaryDirectory() as td:
                root=Path(td);raw=RawFake(actions);ledger,a=setup(root,raw)
                run_session(raw,ledger,a,case,root/'run',test_only=True)
                first=json.loads((root/'run/turn-1.json').read_text(encoding='utf8'))
                if ident=='T04':
                    self.assertFalse(first['score_at_deadline']['all_required_results_correct'])
                else:
                    self.assertTrue(first['score_at_deadline']['all_required_results_correct'])
                self.assertIsNone(first['score_at_deadline']['whole_request_correct'])
                self.assertFalse(any(r['event']=='safety_stop' for r in _rows(ledger)))
                if ident in ('T03','T07'):
                    second=json.loads((root/'run/turn-2.json').read_text(encoding='utf8'))
                    self.assertTrue(second['score_at_deadline']['all_required_results_correct'])

    def test_unrelated_clarification_cannot_trigger_predefined_window_reply(self):
        case=next(c for c in development_protocol()['cases'] if c['id']=='T03')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);raw=RawFake([finish('clarification_required',unresolved=['无关问题'])]);ledger,a=setup(root,raw)
            run_session(raw,ledger,a,case,root/'run',test_only=True)
            self.assertEqual(raw.request_count,1)
            self.assertFalse((root/'run/turn-2.json').exists())

if __name__=='__main__':unittest.main()
