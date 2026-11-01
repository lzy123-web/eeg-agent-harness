"""Constructed shared Agent integration; no claim of autonomous model success."""
import json
import unittest
from eeg_harness.task_plan_agent import TaskPlanEEGAgent, ARMS
from eeg_harness.research.task_memory import synthetic_records
from test_task_plan_agent import node, delivery, InspectableScriptedClient
from test_working_memory import finish


class HandoffTest(unittest.TestCase):
    def test_unseen_result_survives_schedule_then_retires_without_reexecution(self):
        for arm in ARMS:
            with self.subTest(arm=arm):
                first=node('first',[delivery('value','amplitude',{'channels':['SYNTH-C2'],'start':1,'end':3},'B')])
                waiting=node('later',[delivery('power','event_bandpower',{'labels':['control']},'A')])
                captured={}
                def check(messages):
                    observations=[json.loads(m['content']) for m in messages if m['role']=='tool']
                    actual=[o for o in observations if o['tool_name']=='amplitude']
                    self.assertEqual(len(actual),1)
                    captured['id']=actual[0]['data']['observation']['result_id']
                    self.assertEqual(actual[0]['data']['observation']['record'],'B')
                    self.assertEqual(json.loads(messages[1]['content'])['current_plan_task'],'later')
                    self.assertEqual(len(a.working_memory.store.entries),1)
                    return 'select_task',{'task_id':'first'}
                def completed(messages):
                    o=json.loads(messages[-1]['content'])['data']
                    self.assertEqual(o['status'],'already_completed')
                    self.assertEqual(o['outputs']['value']['result_id'],captured['id'])
                    self.assertEqual(a.working_memory.graph.nodes['first'].status,'TASK_COMPLETED')
                    self.assertEqual(a.working_memory.current,'later')
                    self.assertEqual(len(a.working_memory.store.entries),1)
                    self.assertFalse(any(m.get('name')=='amplitude' for m in messages))
                    return finish('partial',unresolved=['TEST unfinished science retained'])
                client=InspectableScriptedClient([('plan_tasks',{'nodes':[first,waiting]}),
                    ('amplitude',{'task_id':'first','output_key':'value'}),check,completed])
                a=TaskPlanEEGAgent(client,synthetic_records(),arm=arm)
                result=a.run('记录B的SYNTH-C2在1到3秒计算RMS；记录A的control事件功率，事件相对窗口尚未决定。')
                self.assertEqual(result.stop_reason,'partial',client.errors)
                self.assertEqual(len(a.working_memory.store.entries),1)

    def test_failed_observation_also_survives_switch_without_authorizing_wrong_scope(self):
        for arm in ('A','B','C'):
            with self.subTest(arm=arm):
                def invalid(messages):
                    return {'role':'assistant','content':None,'tool_calls':[
                        {'id':'bad','type':'function','function':{'name':'amplitude','arguments':json.dumps(
                            {'task_id':'first','output_key':'value','start':5,'end':7})}},
                        {'id':'wait','type':'function','function':{'name':'wait_node','arguments':json.dumps(
                            {'task_id':'first','reason':'TEST suspended after invalid proposal'})}}]}
                def check(messages):
                    seen={m.get('tool_call_id'):json.loads(m['content']) for m in messages if m['role']=='tool'}
                    self.assertEqual(seen['bad']['error']['code'],'ACTION_OWNER_SCOPE_CONFLICT')
                    self.assertTrue(seen['wait']['success'])
                    self.assertFalse(a.working_memory.store.entries)
                    self.assertEqual(json.loads(messages[1]['content'])['current_plan_task'],'later')
                    return finish('partial',unresolved=['TEST unfinished science retained'])
                client=InspectableScriptedClient([('plan_tasks',{'nodes':[
                    node('first',[delivery('value','amplitude')]),
                    node('later',[delivery('other','amplitude',record='B')])]}),invalid,check])
                a=TaskPlanEEGAgent(client,synthetic_records(),arm=arm)
                result=a.run('记录A的SYNTH-C1在0到2秒计算RMS；记录B的SYNTH-C1在0到2秒计算RMS。')
                self.assertEqual(result.stop_reason,'partial',client.errors)

