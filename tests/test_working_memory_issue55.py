"""Issue55 evaluation and evidence-accounting counterexamples, all offline."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from eeg_harness.research.working_memory_issue55 import (
    protocol, records_for, scientific_preflight, score_obligations, main, drive_requests)
from eeg_harness.task_plan_agent import TaskPlanEEGAgent
from test_task_plan_agent import InspectableScriptedClient, node, delivery
from test_working_memory import finish


class Issue55Test(unittest.TestCase):
    def test_independent_budget_requires_grant_and_preserves_confirmation_pool(self):
        from eeg_harness.research.working_memory_issue55 import Issue55BudgetClient
        from eeg_harness.research.task_memory_issue39_budget import StageBudgetExhausted
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'budget.jsonl'
            with self.assertRaises(StageBudgetExhausted):
                Issue55BudgetClient(None,path)
            self.assertFalse(path.exists())
            grant={'stage':'issue55','completions':144,'api_tokens':6000000,
                   'user_grant':'TEST ONLY: fake client, never a real authorization'}
            budget=Issue55BudgetClient(None,path,authorization=grant)
            self.assertTrue(budget._fits([],2,50000))
            self.assertFalse(budget._fits([],49,1))
            self.assertFalse(budget._fits([],1,2000001))
            self.assertFalse(budget._fits([{'event':'stage_closed'}],1,1))
            content=path.read_text(encoding='utf8')
            path.write_text(content.replace('issue55','issue51'),encoding='utf8')
            with self.assertRaises(StageBudgetExhausted):
                Issue55BudgetClient(None,path,authorization=grant)

    def test_new_fixture_and_oracle_use_real_executor(self):
        rows = scientific_preflight()
        self.assertEqual(len(rows), 12)
        self.assertTrue(all(row['passed'] for row in rows))
        self.assertEqual(sum(len(row['oracle']) for row in rows), 17)

    def test_paid_cli_rejected_before_preflight_or_output(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
                'eeg_harness.research.working_memory_issue55.preflight') as run:
            out=Path(tmp)/'new.json'
            with self.assertRaises(SystemExit):
                main(['--real','--output',str(out)])
            run.assert_not_called()
            self.assertFalse(out.exists())

    def test_request_driver_does_not_pass_evaluator_state(self):
        class Result:
            stop_reason='completed'
            def to_dict(self):return {'stop_reason':self.stop_reason}
        class Agent:
            def __init__(self):self.seen=[]
            def run(self,text):self.seen.append(text);return Result()
            continue_run=run
        a=Agent()
        case=protocol()['cases'][1]
        drive_requests(a,case['requests'])
        self.assertEqual(a.seen,case['requests'])
        self.assertNotIn('evaluation_only',json.dumps(a.seen))

    def test_driver_stops_before_unsent_turns_on_technical_failure(self):
        class Result:
            stop_reason='no_progress'
            def to_dict(self):return {'stop_reason':self.stop_reason}
        class Agent:
            def run(self,text):return Result()
            def continue_run(self,text):raise AssertionError('Must not send future turn')
        self.assertEqual(len(drive_requests(Agent(),['first','later'])),1)

    def test_complete_model_dag_does_not_prove_complete_original_request(self):
        scope={'channels':['SYNTH-C1'],'start':.5,'end':2.5}
        client=InspectableScriptedClient([('plan_tasks',{'nodes':[node('only-one',[
            delivery('rms','amplitude',scope)])]}),('amplitude',{}),finish()])
        agent=TaskPlanEEGAgent(client,records_for())
        # Explicit object wording here isolates evaluator omission from T04's
        # independently retained ellipsis-source rejection.
        result=agent.run('记录A SYNTH-C1在0.5到2.5秒的RMS和alpha功率。')
        self.assertEqual(result.stop_reason,'completed')
        self.assertEqual(agent.working_memory.graph.nodes['only-one'].status,'TASK_COMPLETED')
        scored=score_obligations(protocol()['cases'][0],agent.working_memory.store,1)
        self.assertFalse(scored['all_required_results_correct'])
        self.assertEqual([r['passed'] for r in scored['requirements']],[True,False,False])
        self.assertIsNone(scored['whole_request_correct'])
        entry=agent.working_memory.store.entries[0]
        for change in ('source','time','scope','record'):
            with self.subTest(change=change):
                original=copy.deepcopy(entry.evidence)
                params=copy.deepcopy(entry.parameters)
                if change=='source':entry.evidence['source']='synthetic://wrong'
                if change=='time':entry.evidence['analysis_configuration']['time_reference']='event_relative'
                if change=='scope':entry.parameters['start']=1
                if change=='record':
                    case=copy.deepcopy(protocol()['cases'][0]);case['evaluation_only']['obligations'][0]['record']='B'
                else:case=protocol()['cases'][0]
                self.assertFalse(score_obligations(case,agent.working_memory.store,1)['requirements'][0]['passed'])
                entry.evidence.clear();entry.evidence.update(original)
                entry.parameters.clear();entry.parameters.update(params)

    def test_rejected_scientific_action_is_not_actual_evidence_use_all_arms(self):
        scope={'channels':['SYNTH-C1'],'start':0,'end':2}
        for arm in ('A','B','C','A-equivalent'):
            client=InspectableScriptedClient([('plan_tasks',{'nodes':[node('x',[
                delivery('rms','amplitude',scope)])]}),('amplitude',{}),
                ('finish_task',{'status':'partial','answer':'未执行未授权范围','unresolved':['范围不匹配']})])
            agent=TaskPlanEEGAgent(client,records_for(),arm=arm)
            agent.run('记录A SYNTH-C1在4到6秒的RMS。')
            logs=agent.working_memory.evidence_log
            attempts=[r for r in logs if r['event']=='use_attempt']
            self.assertEqual(len(attempts),1)
            self.assertFalse(attempts[0]['success'])
            self.assertFalse(any(r['event']=='used' for r in logs))
            self.assertEqual(len(agent.working_memory.store.entries),0)


if __name__=='__main__':unittest.main()

