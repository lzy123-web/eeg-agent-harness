"""Selected real artifact actions must attach without weakening plan matching."""
from copy import deepcopy
from dataclasses import replace
import json
import unittest
from eeg_harness.task_plan_agent import TaskPlanEEGAgent, ARMS
from eeg_harness.research.task_memory import synthetic_records
from eeg_harness.tooling import ToolRequest
from test_task_plan_agent import node, delivery, InspectableScriptedClient
from test_working_memory import finish


def exercise(arm='C', *, explicit_owner=True, extra_unexecuted=False):
    def plan(messages):
        frames=json.loads(messages[1]['content'])['scientific_source_frames']
        current=next(f for f in frames if f['source_ref'].startswith('u2:'))
        d=delivery('q','epoch_quality',{})
        d['interpretation']={'source_ref':current['source_ref'],'time_reference':'event_relative'}
        nodes=[node('qc',[d])]
        if extra_unexecuted:nodes.append(node('independent',[{**deepcopy(d),'key':'not_executed'}]))
        return 'plan_tasks',{'nodes':nodes}
    def measure(messages):
        artifact=a.working_memory.graph.nodes['producer'].outputs['ep']['output_artifact']
        return 'epoch_quality',{'artifact_id':artifact,**({'task_id':'qc','output_key':'q','revision':1} if explicit_owner else {})}
    c=InspectableScriptedClient([
        ('plan_tasks',{'nodes':[node('producer',[delivery('ep','create_epochs',{'labels':['stimulus'],'tmin':0,'tmax':1.25})])]}),
        ('create_epochs',{'task_id':'producer','output_key':'ep'}),finish(),plan,measure,
        finish('partial',unresolved=['TEST unexecuted delivery']) if extra_unexecuted else finish()])
    a=TaskPlanEEGAgent(c,synthetic_records(),arm=arm)
    first=a.run('记录A提取stimulus事件后0到1.25秒的Epoch。')
    second=a.continue_run('沿用记录A刚才的同一批Epoch追加质量测量，不重建也不删除试次。')
    assert not c.errors,c.errors
    return a,first,second


class ExecutionScopeBindingTest(unittest.TestCase):
    def test_six_arms_and_unambiguous_legacy_action_keep_exact_artifact(self):
        for arm in ARMS:
            with self.subTest(arm=arm):
                a,first,second=exercise(arm)
                self.assertEqual((first.stop_reason,second.stop_reason),('completed','completed'))
                w=a.working_memory;n=w.graph.nodes['qc'];d=n.delivery('q');out=deepcopy(n.outputs['q'])
                self.assertEqual(d.scope,{}) # runtime resolution is not a semantic plan rewrite
                self.assertEqual(out['input_artifact'],w.graph.nodes['producer'].outputs['ep']['output_artifact'])
                self.assertEqual(len(w.store.entries),2)
                self.assertFalse(w._matches(d,w.store.entries[-1]))
                self.assertFalse(w._matches(d,w.store.entries[-1],out,'another-owner'))
                w._sync_outputs(n);self.assertEqual(n.outputs['q'],out)
                self.assertTrue(w.delivery_check(n)['all_outputs_present'])
        a,_,second=exercise(explicit_owner=False)
        self.assertEqual(second.stop_reason,'completed')

    def test_unexecuted_same_capability_never_captures_the_owned_result(self):
        a,_,second=exercise(extra_unexecuted=True);w=a.working_memory;n=w.graph.nodes['qc']
        self.assertEqual(second.stop_reason,'partial');self.assertIn('q',n.outputs)
        other=w.graph.nodes['independent']
        self.assertNotIn('not_executed',other.outputs)
        w._sync_outputs(other);self.assertNotIn('not_executed',other.outputs)
        self.assertFalse(w._matches(other.delivery('not_executed'),w.store.entries[-1],n.outputs['q'],other.task_id))

    def test_receipt_is_invalid_after_contract_identity_or_real_binding_change(self):
        for defect in ('contract','result','artifact','record'):
            with self.subTest(defect=defect):
                a,_,_=exercise();w=a.working_memory;n=w.graph.nodes['qc'];out=n.outputs['q'];d=n.delivery('q')
                if defect=='contract':d.interpretation['source_ref']='unverified-new-source'
                elif defect=='result':out['result_id']=w.store.entries[0].task_id
                elif defect=='artifact':w.store.contexts['A'].artifacts.clear()
                else:
                    ctx=w.store.contexts['A'];ctx.record=replace(ctx.record,source='synthetic://changed-source')
                self.assertFalse(w.delivery_check(n)['all_outputs_present'])
                self.assertFalse(w._execution_scope(d,out,n.task_id))
                self.assertNotEqual(w._accept_delivery(n,'q',1,out['result_id']).get('status'),'delivery_accepted')

    def test_bad_owner_and_artifact_replacement_reject_before_any_computation(self):
        for delta in ({'task_id':'missing'},{'output_key':'missing'},{'revision':2},
                      {'record':'B'},{'artifact_id':'unapproved-other-artifact'}):
            with self.subTest(delta=delta):
                a,_,_=exercise();w=a.working_memory;before=len(w.store.entries)
                args={'task_id':'qc','output_key':'q','revision':1};args.update(delta)
                r=w._dispatch(ToolRequest('epoch_quality',args))
                self.assertEqual(r['status'],'rejected');self.assertEqual(len(w.store.entries),before)

