"""Constructed counterexamples from live v1 failures, not edited model success."""
from copy import deepcopy
import json
import unittest
from eeg_harness.task_plan_agent import TaskPlanEEGAgent
from eeg_harness.research.task_memory import synthetic_records
from test_task_plan_agent import node,delivery,InspectableScriptedClient
from test_working_memory import finish


def retained_chain():
    saved={}
    def initial(messages):
        frame=json.loads(messages[1]['content'])['scientific_source_frames'][0]
        d=delivery('old','psd',{'channels':['SYNTH-C1'],'start':0,'end':2})
        d['interpretation']={'source_ref':frame['source_ref'],'time_reference':'record_absolute'}
        return 'plan_tasks',{'nodes':[node('a',[d])]}
    def revise(messages):
        w=a.working_memory;saved['old']=deepcopy(w.graph.nodes['a'].outputs['old'])
        rows=[d.to_dict() for d in w.graph.nodes['a'].required_outputs]
        d=deepcopy(rows[0]);d['key']='new';d['scope'].update(start=4,end=6)
        frames=json.loads(messages[1]['content'])['scientific_source_frames']
        d['interpretation']['range_ref']=next(f['source_ref'] for f in frames if f['source_ref'].startswith('u2:'))
        rows.append(d)
        return 'revise_plan',{'task_id':'a','updates':{'required_outputs':rows},'reason':'Preserve actual old delivery and append explicitly requested new window'}
    c=InspectableScriptedClient([initial,('psd',{'task_id':'a','output_key':'old'}),finish(),
        revise,('psd',{'task_id':'a','output_key':'new'}),finish()])
    a=TaskPlanEEGAgent(c,synthetic_records())
    first=a.run('记录A的SYNTH-C1在0到2秒计算alpha功率。')
    second=a.continue_run('把记录A窗口改为4到6秒，并保留旧结果。')
    return a,first,second,c,saved


class RetainedEvidenceTest(unittest.TestCase):
    def test_preserved_old_output_does_not_need_new_window_authorization(self):
        a,first,second,c,saved=retained_chain()
        self.assertFalse(c.errors,c.errors)
        self.assertEqual((first.stop_reason,second.stop_reason),('completed','completed'))
        w=a.working_memory;n=w.graph.nodes['a']
        self.assertEqual(n.outputs['old']['result_id'],saved['old']['result_id'])
        self.assertEqual(w._entry_for(n.outputs['old']).parameters,{'channels':['SYNTH-C1'],'start':0,'end':2})
        self.assertEqual(len(w.store.entries),2)
        self.assertEqual(n.revision_history[0]['snapshot']['outputs']['old'],saved['old'])

    def test_available_wrong_field_rejected_but_unknown_future_field_not_guessed(self):
        from eeg_harness.tooling import ToolRequest
        a,_,_,_,_=retained_chain();w=a.working_memory
        compare=delivery('diff','compare_results',{},refs=[
            {'task_id':'a','key':key,'fields':[['invented','path']],'level':'result'} for key in ('old','new')])
        before=deepcopy(w.graph.to_dict())
        result=w._dispatch(ToolRequest('plan_tasks',{'nodes':[node('compare',[compare])]}))
        self.assertEqual(result['code'],'INVALID_PLAN_SOURCE');self.assertIn('scalar field',result['compatibility_diagnostic']['message'])
        self.assertEqual(w.graph.to_dict(),before)
        for r in compare['input_refs']:r['fields']=[['SYNTH-C1','alpha']]
        result=w._dispatch(ToolRequest('plan_tasks',{'nodes':[node('compare',[compare])]}))
        self.assertEqual(result['status'],'planned')

    def test_future_fields_remain_proposals_until_actual_result_then_fail_closed(self):
        refs=[{'task_id':'source','key':key,'fields':[['invented']],'level':'result'} for key in ('power','rms')]
        c=InspectableScriptedClient([('plan_tasks',{'nodes':[
            node('source',[delivery('power'),delivery('rms','amplitude')]),
            node('compare',[delivery('diff','compare_results',{},refs=refs)])]}),
            ('psd',{'task_id':'source','output_key':'power'}),
            ('amplitude',{'task_id':'source','output_key':'rms'}),
            ('compare_results',{'task_id':'compare','output_key':'diff'}),
            finish('partial',unresolved=['TEST explicit fields need repair'])])
        a=TaskPlanEEGAgent(c,synthetic_records());r=a.run('记录A的SYNTH-C1在0到2秒计算PSD和RMS。')
        self.assertFalse(c.errors,c.errors);self.assertEqual(r.tool_results[0]['data']['status'],'planned')
        rejected=next(x['data'] for x in r.tool_results if x['tool_name']=='compare_results')
        self.assertEqual(rejected['code'],'INVALID_PLAN_SOURCE');self.assertEqual(rejected['recovery']['field'],'input_refs')
        self.assertEqual(len(a.working_memory.store.entries),2)
        self.assertFalse(a.working_memory.graph.nodes['compare'].outputs)

    def test_preservation_does_not_authorize_modified_scientific_binding(self):
        from eeg_harness.tooling import ToolRequest
        a,_,_,_,_=retained_chain();w=a.working_memory;n=w.graph.nodes['a']
        before=deepcopy(w.graph.to_dict());rows=[d.to_dict() for d in n.required_outputs]
        rows[0]['scope']['end']=3
        r=w._dispatch(ToolRequest('revise_plan',{'task_id':'a','updates':{'required_outputs':rows},'reason':'TEST unauthorized old window'}))
        self.assertEqual(r['status'],'rejected');self.assertEqual(w.graph.to_dict(),before)

    def test_quality_contract_matches_actual_equality_boundaries(self):
        import numpy as np
        from eeg_harness.events import EpochSet
        from eeg_harness.quality import epoch_quality
        epochs=EpochSet(np.array([[[0.,1.]]]),2.,('X',),0.,1.,('e',),(0.,),None,(),'synthetic://boundary')
        r=epoch_quality(epochs,'TEST',thresholds={'flatline_delta_volts':1.,'flatline_fraction':1.,
            'high_amplitude_volts':1.,'high_amplitude_fraction':.5})
        self.assertEqual(r['quality_flag_reasons'],{'FLATLINE':1,'HIGH_AMPLITUDE':1})
        self.assertEqual(r['flagged_epoch_indices'],[0]);self.assertEqual(epochs.data.shape,(1,1,2))
        self.assertIn('adjacent',r['measurement_contract']['flatline'])
        self.assertIn('not used',r['measurement_contract']['line_noise'])
