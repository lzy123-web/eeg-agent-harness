"""Shared interfaces on actual stores; constructed tests, not autonomy."""
from copy import deepcopy
from dataclasses import replace
import json
import unittest
from eeg_harness.task_plan_agent import ARMS
from eeg_harness.tooling import ToolRequest
from eeg_harness.task_plan import task_spec_schema
from eeg_harness.scientific_contracts import validate_contract,ContractError
from test_issue59_history_index import exercise
from test_task_plan_agent import node,delivery,reference
from test_task_plan_agent import InspectableScriptedClient
from test_working_memory import finish
from eeg_harness.task_plan_agent import TaskPlanEEGAgent
from eeg_harness.research.task_memory import synthetic_records


def channel_revision(arm='C',defect=None):
    def initial(messages):
        frame=json.loads(messages[1]['content'])['scientific_source_frames'][0]
        d=delivery('r','amplitude',{'channels':['SYNTH-C1'],'start':0,'end':2})
        d['interpretation']={'source_ref':frame['source_ref'],'time_reference':'record_absolute'}
        return 'plan_tasks',{'nodes':[node('a',[d])]}
    def revise(messages):
        frames=json.loads(messages[1]['content'])['scientific_source_frames']
        old=frames[0];current=next(f for f in frames if f['turn']==2)
        changes={'scope':{'channels':['SYNTH-C2']},'interpretation':{
            'source_ref':current['source_ref'],'range_ref':old['source_ref']}}
        if defect=='invented_window':changes['scope'].update(start=0,end=3)
        if defect=='wrong_time':changes['interpretation']['time_reference']='event_relative'
        if defect=='wrong_record':changes['record']='B'
        if defect=='unrelated_parent':changes['interpretation']['range_ref']=frames[1]['source_ref']
        return 'revise_plan',{'task_id':'a','output_key':'r','revision':1,'reason':'explicit field revision','changes':changes}
    client=InspectableScriptedClient([initial,('amplitude',{'task_id':'a','output_key':'r'}),finish(),
        revise,('amplitude',{'task_id':'a','output_key':'r'}),finish('partial' if defect else 'completed',unresolved=['negative'] if defect else [])])
    a=TaskPlanEEGAgent(client,synthetic_records(),arm=arm)
    a.run('记录A SYNTH-C1在0到2秒计算RMS；记录A SYNTH-C2在0到2秒的旧文字尚未计算。')
    before=deepcopy(a.working_memory.graph.to_dict());entry=deepcopy(a.working_memory.store.entries[0])
    if defect=='stale':
        ctx=a.working_memory.store.contexts['A'];ctx.record=replace(ctx.record,source='synthetic://changed')
    request='记录A改为SYNTH-C2，时间范围保持原样。'
    if defect=='current_conflict':request='记录A改为SYNTH-C2在2到4秒计算RMS。'
    second=a.continue_run(request)
    return a,second,client,before,entry

class InterfaceTest(unittest.TestCase):
    def test_field_revision_reuses_only_selected_actual_unchanged_window(self):
        for arm in ARMS:
            with self.subTest(arm=arm):
                a,second,c,before,old=channel_revision(arm)
                self.assertFalse(c.errors,c.errors);self.assertEqual(second.stop_reason,'completed')
                self.assertEqual(len(a.working_memory.store.entries),2)
                self.assertEqual(a.working_memory.store.entries[0],old)
                self.assertEqual(a.working_memory.store.entries[1].parameters,{'channels':['SYNTH-C2'],'start':0,'end':2})
                self.assertEqual(a.working_memory.graph.nodes['a'].revision,2)

    def test_field_revision_rejects_unearned_or_conflicting_window_atomically(self):
        for defect in ('invented_window','wrong_time','wrong_record','unrelated_parent','stale','current_conflict'):
            with self.subTest(defect=defect):
                a,second,c,before,old=channel_revision(defect=defect)
                response=next(r for r in second.tool_results if r['tool_name']=='revise_plan')
                self.assertFalse(response['success']);self.assertEqual(a.working_memory.graph.nodes['a'].revision,1)
                self.assertEqual(a.working_memory.store.entries,[old])
                self.assertEqual(a.working_memory.graph.nodes['a'].revision_history,[])

    def test_six_arms_contract_discovery_does_not_read_values_or_change_history(self):
        for arm in ARMS:
            with self.subTest(arm=arm):
                a,first,second,c,saved=exercise(arm);w=a.working_memory
                before=deepcopy(w.graph.to_dict());seen=deepcopy(w.evidence_log)
                r=w._read('a','power','contract',revision=1)
                self.assertTrue(r['valid_binding']);self.assertFalse(r['numeric_evidence'])
                f=next(f for f in r['fields'] if f['path']==['SYNTH-C1','alpha'])
                self.assertEqual(f['unit_or_kind'],'V²');self.assertNotIn('value',f)
                self.assertEqual(w.graph.to_dict(),before);self.assertEqual(w.evidence_log,seen)
                v=json.loads(w._view()[1]['content']);card=v['plan'][0]
                self.assertNotIn('required_outputs',card);self.assertEqual(card['revision_targets'][0]['revision'],2)
                bad={'nodes':[{'task_id':'a','revision':999,'invented':'state cannot be write payload'}]}
                result=w._dispatch(ToolRequest('plan_tasks',bad))
                self.assertEqual(result['code'],'INVALID_PLAN_OPERATION');self.assertEqual(w.graph.to_dict(),before)
                ctx=w.store.contexts['A'];ctx.record=replace(ctx.record,source='synthetic://replaced')
                stale=w._read('a','power','contract',revision=1)
                self.assertFalse(stale['valid_binding']);self.assertEqual(stale['fields'],[])

    def test_type_specific_compare_schema_and_source_constraints(self):
        a,*_=exercise();w=a.working_memory
        schema=task_spec_schema(next(iter(w.store.contexts.values())).executor.registry)
        refs=[reference('a','power',fields=[['SYNTH-C1','alpha']]),reference('a','power',fields=[['SYNTH-C1','alpha']])]
        legal=node('cmp',[delivery('delta','compare_results',{},refs=refs)])
        legal['required_outputs'][0]['interpretation']={}
        validate_contract(legal,schema)
        for count in (0,1,3):
            bad=deepcopy(legal);bad['required_outputs'][0]['input_refs']=refs[:1]*count
            with self.assertRaises(ContractError):validate_contract(bad,schema)
        bad=deepcopy(legal);bad['required_outputs'][0]['input_refs'][0]['fields']=[]
        with self.assertRaises(ContractError):validate_contract(bad,schema)
        bad=node('numeric',[delivery('power')]);bad['required_outputs'][0]['interpretation']={}
        with self.assertRaises(ContractError):validate_contract(bad,schema)
        missing=deepcopy(legal);missing['required_outputs'][0]['input_refs'][0]['fields']=[['missing']]
        before=w.graph.to_dict();r=w._dispatch(ToolRequest('plan_tasks',{'nodes':[missing]}))
        self.assertEqual(r['code'],'INVALID_PLAN_SOURCE');self.assertEqual(w.graph.to_dict(),before)
