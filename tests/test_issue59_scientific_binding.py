"""Constructed integration evidence, not replay or model-autonomy evidence."""
from copy import deepcopy
from dataclasses import replace
import json
import unittest
from eeg_harness.task_plan_agent import TaskPlanEEGAgent, ARMS
from eeg_harness.task_plan import DeliveryItem
from eeg_harness.scientific_binding import resolve_scientific_binding
from eeg_harness.research.task_memory import synthetic_records
from eeg_harness.tooling import ToolRequest
from test_task_plan_agent import node,delivery,InspectableScriptedClient
from test_working_memory import finish

SCOPE={'labels':['stimulus'],'tmin':0,'tmax':1.25}
REF={'task_id':'source','key':'epochs'}


def chain(arm='C',mode='direct',refs=None,second_text=None,measurements=None):
    refs=deepcopy(refs if refs is not None else [REF])
    saved={}
    def proposal(messages):
        frames=json.loads(messages[1]['content'])['scientific_source_frames']
        old=next(f for f in frames if f['source_ref'].startswith('u1:'))
        current=next(f for f in frames if f['source_ref'].startswith('u2:'))
        d=delivery('quality','epoch_quality',{},refs=refs)
        d['interpretation']={'source_ref':current['source_ref'],'time_reference':'event_relative',
                             'range_ref':old['source_ref']}
        if measurements is not None:d['interpretation']['measurement_channels']=measurements
        saved['delivery']=d
        if mode=='direct':return 'plan_tasks',{'nodes':[node('target',[d])]}
        empty=delivery('quality','epoch_quality',{})
        empty['interpretation']={'source_ref':current['source_ref'],'time_reference':'event_relative'}
        return 'plan_tasks',{'nodes':[node('target',[empty])]}
    def revision(messages):
        d=saved['delivery']
        if mode=='legacy':return 'revise_plan',{'task_id':'target','updates':{'required_outputs':[d]},'reason':'Explicit upstream object'}
        return 'revise_plan',{'task_id':'target','output_key':'quality','revision':1,
            'changes':{'input_refs':d['input_refs'],'interpretation':d['interpretation']},'reason':'Explicit upstream object'}
    steps=[('plan_tasks',{'nodes':[node('source',[delivery('epochs','create_epochs',SCOPE),
        delivery('power','event_bandpower',{},refs=[REF])])]}),
        ('create_epochs',{'task_id':'source','output_key':'epochs'}),
        ('event_bandpower',{'task_id':'source','output_key':'power'}),finish(),proposal]
    if mode!='direct':steps.append(revision)
    steps.extend([('epoch_quality',{'task_id':'target','output_key':'quality'}),finish()])
    c=InspectableScriptedClient(steps);a=TaskPlanEEGAgent(c,synthetic_records(),arm=arm)
    first=a.run('记录A提取stimulus事件后0到1.25秒Epoch并计算事件功率。')
    second=a.continue_run(second_text or '沿用记录A刚才的同一批Epoch追加质量测量，不重建。')
    return a,first,second,c


class ScientificBindingTest(unittest.TestCase):
    def test_direct_incremental_and_legacy_share_sources_across_six_arms(self):
        for arm in ARMS:
            for mode in ('direct','incremental','legacy'):
                with self.subTest(arm=arm,mode=mode):
                    a,first,second,c=chain(arm,mode)
                    self.assertFalse(c.errors,c.errors)
                    self.assertEqual((first.stop_reason,second.stop_reason),('completed','completed'))
                    w=a.working_memory;target=w.graph.nodes['target'];out=target.outputs['quality']
                    self.assertEqual(out['input_artifact'],w.graph.nodes['source'].outputs['epochs']['output_artifact'])
                    self.assertEqual(len(w.store.entries),3)
                    self.assertEqual(target.delivery('quality').scope,{})
                    self.assertTrue(w.delivery_check(target)['all_outputs_present'])

    def test_equivalent_explicit_refs_deduplicate_but_different_artifact_conflicts(self):
        a,_,second,c=chain(refs=[REF,{'task_id':'source','key':'power'}])
        self.assertEqual(second.stop_reason,'completed',c.errors)
        w=a.working_memory;d=w.graph.nodes['target'].delivery('quality');b=w._binding(d)
        self.assertEqual(len(b.witnesses),2);self.assertFalse(b.conflicts)
        store=w.store;original=store.entries[0]
        other=replace(deepcopy(original),task_id='TEST-other');other.evidence['binding']['artifact_id']='TEST-other'
        # Exact actual binding failure cannot be converted into a pending input.
        bad=resolve_scientific_binding(store,'epoch_quality','A',{},references=[
            {'entry':original,'reference':REF,'delivery':d.to_dict()},
            {'entry':other,'reference':{'task_id':'other','key':'ep'},'delivery':d.to_dict()}])
        self.assertFalse(bad.ok)
        # Now a valid distinct artifact with exactly equal data and parameters:
        # equality of values still does not confer identity.
        ctx=store.contexts['A'];original_id=original.evidence['binding']['artifact_id']
        ctx.artifacts['TEST-other']=replace(ctx.artifacts[original_id],artifact_id='TEST-other')
        self.assertTrue(store._binding_valid(other))
        different=resolve_scientific_binding(store,'epoch_quality','A',{},references=[
            {'entry':original,'reference':REF,'delivery':d.to_dict()},
            {'entry':other,'reference':{'task_id':'other','key':'ep'},'delivery':d.to_dict()}])
        self.assertFalse(different.ok);self.assertIn('different actual artifacts','; '.join(different.conflicts))

    def test_no_interpretation_is_not_an_escape_from_actual_artifact_window_check(self):
        a,_,_,_=chain();w=a.working_memory
        w.begin_turn('记录A将stimulus事件窗口改为0到1秒，计算质量。')
        count=len(w.store.entries);artifact=w.store.entries[0].evidence['binding']['artifact_id']
        result=w.store.execute_action('epoch_quality',{'artifact_id':artifact},record='A')
        self.assertNotEqual(result['status'],'observed');self.assertEqual(len(w.store.entries),count)

    def test_candidate_graph_invalidates_current_source_while_history_remains_explicit(self):
        a,_,_,_=chain();w=a.working_memory;old=deepcopy(w.graph.to_dict())
        proposed=deepcopy(w.graph);source=proposed.nodes['source'];ds=[d.to_dict() for d in source.required_outputs]
        ds[0]['scope']['tmax']=1
        proposed.revise('source',{'required_outputs':ds},'TEST proposed new window')
        d=proposed.nodes['target'].delivery('quality');b=w._binding(d,graph=proposed)
        self.assertTrue(b.pending);self.assertIsNone(b.entry);self.assertEqual(b.scope['tmax'],1)
        self.assertEqual(w.graph.to_dict(),old)
        pinned=deepcopy(d.to_dict());pinned['input_refs'][0]['revision']=1
        history=w._binding(DeliveryItem.from_dict(pinned),graph=proposed)
        self.assertFalse(history.pending);self.assertEqual(history.scope['tmax'],1.25)
        self.assertIsNotNone(history.entry)

    def test_explicit_new_window_cannot_hide_behind_old_artifact_or_old_range(self):
        for mode in ('direct','incremental','legacy'):
            a,_,second,c=chain(mode=mode,second_text='记录A将stimulus事件窗口改为0到1秒，追加Epoch质量测量。')
            self.assertEqual(len(a.working_memory.store.entries),2)
            self.assertNotEqual(second.stop_reason,'completed')
            self.assertTrue(any(x['data'].get('code')=='INVALID_PLAN_SOURCE' for x in second.tool_results))

    def test_future_dependency_is_legal_but_neither_ready_nor_delivered(self):
        saved={}
        def inspect(messages):
            w=a.working_memory;d=w.graph.nodes['target'].delivery('q');b=w._binding(d)
            saved.update(binding=b.summary(),ready=w.graph.dependency_state('target')['ready'],
                         complete=w.delivery_check(w.graph.nodes['target'])['all_outputs_present'])
            return 'epoch_quality',{'task_id':'target','output_key':'q'}
        c=InspectableScriptedClient([('plan_tasks',{'nodes':[node('source',[delivery('epochs','create_epochs',SCOPE)]),
            node('target',[delivery('q','epoch_quality',{},refs=[REF])])]}),inspect,
            finish('partial',unresolved=['TEST producer not executed'])])
        a=TaskPlanEEGAgent(c,synthetic_records());r=a.run('记录A提取stimulus事件后0到1.25秒Epoch并计算质量。')
        self.assertFalse(c.errors,c.errors);self.assertEqual(r.stop_reason,'partial')
        self.assertEqual(saved['binding']['status'],'pending');self.assertFalse(saved['ready']);self.assertFalse(saved['complete'])
        self.assertFalse(a.working_memory.store.entries)
