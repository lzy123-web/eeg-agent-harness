"""Historical locators are discoverable facts, never automatic old-result reuse."""
from copy import deepcopy
from dataclasses import replace
import json
import unittest
from eeg_harness.task_plan_agent import TaskPlanEEGAgent,ARMS
from eeg_harness.research.task_memory import synthetic_records
from test_task_plan_agent import node,delivery,InspectableScriptedClient
from test_working_memory import finish


def exercise(arm='C'):
    saved={}
    def initial(messages):
        frames=json.loads(messages[1]['content'])['scientific_source_frames']
        d=delivery('power');d['interpretation']={'source_ref':frames[0]['source_ref'],'time_reference':'record_absolute'}
        saved['old']=deepcopy(d)
        return 'plan_tasks',{'nodes':[node('a',[d])]}
    def revise(messages):
        frames=json.loads(messages[1]['content'])['scientific_source_frames']
        return 'revise_plan',{'task_id':'a','output_key':'power','revision':1,'reason':'Explicit new window',
            'changes':{'scope':{'start':4,'end':6},'interpretation':{'range_ref':next(f['source_ref'] for f in frames if f['source_ref'].startswith('u2:'))}}}
    def inspect(messages):
        saved['view']=json.loads(messages[1]['content'])
        return 'read_dependency',{'task_id':'a','key':'power','level':'result'}
    c=InspectableScriptedClient([initial,('psd',{'task_id':'a','output_key':'power'}),finish(),revise,inspect,
        ('read_dependency',{'task_id':'a','key':'power','revision':1,'level':'result'}),
        ('psd',{'task_id':'a','output_key':'power','revision':2}),finish()])
    a=TaskPlanEEGAgent(c,synthetic_records(),arm=arm)
    first=a.run('记录A的SYNTH-C1在0到2秒计算alpha功率。')
    second=a.continue_run('把记录A窗口改为4到6秒，保留原0到2秒结果。')
    return a,first,second,c,saved


class HistoryIndexTest(unittest.TestCase):
    def test_six_arms_discover_exact_history_without_promoting_it_to_current_result(self):
        for arm in ARMS:
            with self.subTest(arm=arm):
                a,first,second,c,saved=exercise(arm);w=a.working_memory
                self.assertFalse(c.errors,c.errors);self.assertEqual((first.stop_reason,second.stop_reason),('completed','completed'))
                card=next(n for n in saved['view']['task_summaries'] if n['task_id']=='a')
                self.assertEqual(card['readable_keys'],[])
                history=card['historical_outputs'];self.assertEqual(len(history),1)
                self.assertEqual(history[0]['revision'],1);self.assertEqual(history[0]['scope']['end'],2)
                self.assertTrue(history[0]['valid_binding']);self.assertNotIn('value',history[0])
                missing=next(x['data'] for x in second.tool_results if x['tool_name']=='read_dependency' and not x['success'])
                self.assertEqual(missing['requested_revision'],2);self.assertEqual(missing['available_history'],history)
                self.assertEqual(len(w.store.entries),2);self.assertEqual(w.store.entries[-1].parameters['end'],6)
                self.assertNotEqual(w.graph.nodes['a'].outputs['power']['result_id'],history[0]['result_id'])

    def test_stale_binding_is_visible_as_invalid_and_still_unreadable(self):
        a,_,_,_,_=exercise();w=a.working_memory
        ctx=w.store.contexts['A'];ctx.record=replace(ctx.record,source='synthetic://changed')
        rows=w._history_index(w.graph.nodes['a'])
        self.assertFalse(rows[0]['valid_binding'])
        self.assertEqual(w._read('a','power','result',revision=1)['code'],'STALE_RESULT')
