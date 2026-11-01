"""Reasonable interpretation fixtures over the original Agent, never NLP scores."""
from copy import deepcopy
from dataclasses import replace
import unittest
from eeg_harness.events import EEGEvent,EventSet
from eeg_harness.task_plan_agent import TaskPlanEEGAgent
from eeg_harness.research.task_memory import synthetic_records
from eeg_harness.research.working_memory_issue52 import run_case
from eeg_harness.research.working_memory_issue55_repair import interpreted_actions
from eeg_harness.research.working_memory_issue55 import score_obligations
from test_task_plan_agent import InspectableScriptedClient,node,delivery
from test_working_memory import finish

ARMS=('A','B','C','A-equivalent')


def run_interpreted(text,tool,scope,meaning,arm='C',records=None,record='A'):
    d=delivery('out',tool,scope,record=record);d['interpretation']=meaning
    actions=[('plan_tasks',{'nodes':[node('x',[d])]}),(tool,{}),finish()]
    agent=TaskPlanEEGAgent(InspectableScriptedClient(actions),records or synthetic_records(),arm=arm)
    result=agent.run(text)
    return agent,result


class InterpretationTest(unittest.TestCase):
    def test_plan_scope_error_preserves_original_tool_diagnostic_without_committing(self):
        bad=delivery('power','event_bandpower',{'labels':['stimulus'],'tmin':0,'tmax':1,'channels':['SYNTH-C2']})
        for arm in ARMS:
            a=TaskPlanEEGAgent(InspectableScriptedClient([('plan_tasks',{'nodes':[node('x',[bad])]}),finish()]),synthetic_records(),arm=arm)
            r=a.run('记录A stimulus事件相对0到1秒的SYNTH-C2功率。')
            error=r.tool_results[0]['data']
            self.assertEqual(error['code'],'INVALID_PLAN_REQUIREMENT')
            detail=error['requirement_errors'][0]
            self.assertEqual(detail['task_id'],'x');self.assertEqual(detail['output_key'],'power')
            self.assertEqual(detail['allowed_scope_fields'],['labels','tmax','tmin'])
            self.assertFalse(a.working_memory.graph.nodes)
            self.assertFalse(a.working_memory.store.entries)

    def test_referenced_measurement_dimension_uses_same_verified_field_relation(self):
        source='记录A SYNTH-C1在0到2秒RMS';target='记录B沿用前述通道在2到4秒RMS'
        meaning={'source_span':target,'time_reference':'record_absolute','measurement_channels':['SYNTH-C1'],
                 'channel_reference':{'source_span':source,'target_span':target}}
        scope={'channels':['SYNTH-C1'],'start':2,'end':4}
        for arm in ARMS:
            a,r=run_interpreted(source+'；'+target+'。','amplitude',scope,meaning,arm,record='B')
            self.assertEqual(r.stop_reason,'completed');self.assertEqual(len(a.working_memory.store.entries),1)
            bad=deepcopy(meaning);bad['measurement_channels']=['SYNTH-C2']
            a,_=run_interpreted(source+'；'+target+'。','amplitude',scope,bad,arm,record='B')
            self.assertFalse(a.working_memory.store.entries);self.assertFalse(a.working_memory.store.admitted_scopes)

    def test_interpretation_error_recovers_by_plan_revision_not_action_override(self):
        source='记录A SYNTH-C1在0到2秒RMS';target='记录B沿用前述通道在2到4秒RMS'
        output=delivery('out','amplitude',{'channels':['SYNTH-C1'],'start':2,'end':4},record='B')
        output['interpretation']={'source_span':target,'time_reference':'record_absolute','measurement_channels':['SYNTH-C1']}
        fixed=deepcopy(output);ref={'source_span':source,'target_span':target}
        fixed['interpretation']['channel_reference']=ref
        for arm in ARMS:
            actions=[('plan_tasks',{'nodes':[node('x',[output])]}),('amplitude',{}),
                ('amplitude',{'channel_reference':ref}),
                ('revise_plan',{'task_id':'x','updates':{'required_outputs':[fixed]},'reason':'repair field relation'}),
                ('amplitude',{}),finish()]
            a=TaskPlanEEGAgent(InspectableScriptedClient(actions),synthetic_records(),arm=arm)
            r=a.run(source+'；'+target+'。')
            self.assertEqual(r.stop_reason,'completed');self.assertEqual(len(a.working_memory.store.entries),1)
            results=[x['data'] for x in r.tool_results]
            self.assertTrue(any(x.get('recovery',{}).get('tool')=='revise_plan' for x in results))
            self.assertTrue(any(x.get('code')=='INTERPRETATION_CONFLICT' for x in results))
            self.assertEqual(a.working_memory.graph.nodes['x'].revision,2)
            numeric=[t for t in a.working_memory.tool_definitions() if t['function']['name']=='amplitude'][0]
            self.assertNotIn('channel_reference',numeric['function']['parameters']['properties'])

    def test_original_t04_and_t07_requests_scored_without_user_rewording(self):
        for arm in ARMS:
            for ident,count in [('T04',2),('T07',4)]:
                row=run_case(ident,arm,actions=interpreted_actions(ident))
                self.assertTrue(all(s=='completed' for s in row['metrics']['stop_reasons']),row['metrics'])
                self.assertEqual(row['metrics']['numeric_executions'],count)
                self.assertTrue(all(c['passed'] for c in row['oracle']))

    def test_event_measurement_order_never_changes_time_reference(self):
        for arm in ARMS:
            for label,channel,start,end,alias in [('stimulus','SYNTH-C2',0,1.25,'A'),('pulse','Lead-Y',-.25,1.5,'B')]:
                records={k:replace(v,channel_names=('Lead-X','Lead-Y'),events=EventSet(tuple(
                    EEGEvent('pulse' if e.label=='stimulus' else 'rest',e.onset_seconds) for e in v.events.events),v.events.source))
                    for k,v in synthetic_records().items()} if label=='pulse' else synthetic_records()
                for text in (f'记录{alias} {label}事件的{channel}通道在事件相对{start}到{end}秒计算theta功率',
                             f'记录{alias} {label}事件在相对{start}到{end}秒计算{channel}通道的theta功率'):
                    meaning={'source_span':text,'time_reference':'event_relative','measurement_channels':[channel]}
                    good,r=run_interpreted(text+'。','create_epochs',{'labels':[label],'tmin':start,'tmax':end},meaning,arm,records,alias)
                    self.assertEqual(r.stop_reason,'completed')
                    bad,_=run_interpreted(text+'。','amplitude',{'channels':[channel],'start':start,'end':end},meaning,arm,records,alias)
                    self.assertEqual(len(bad.working_memory.store.entries),0)
                    self.assertFalse(bad.working_memory.store.admitted_scopes)
                    proof=good.working_memory.store.entries[0].tool_trace[0]['scientific_sources']
                    self.assertEqual(proof['tmin']['semantic_status'],'model_interpretation_not_intent_proof')

    def test_mixed_parent_without_interpretation_does_not_guess_from_order(self):
        text='记录A stimulus事件的SYNTH-C2通道在事件相对0到1.25秒计算theta功率'
        for tool,scope in [('create_epochs',{'labels':['stimulus'],'tmin':0,'tmax':1.25}),
                           ('amplitude',{'channels':['SYNTH-C2'],'start':0,'end':1.25})]:
            agent,_=run_interpreted(text+'。',tool,scope,{})
            self.assertEqual(len(agent.working_memory.store.entries),0)

    def test_plan_cannot_invent_values_crop_parent_or_change_tool_time_base(self):
        text='记录A stimulus事件的SYNTH-C2通道在事件相对0到1.25秒计算theta功率'
        original={'source_span':text,'time_reference':'event_relative','measurement_channels':['SYNTH-C2']}
        for option in ('window','parent','record','dimension','range'):
            meaning=deepcopy(original);scope={'labels':['stimulus'],'tmin':0,'tmax':1.25};record='A'
            if option=='window':scope['tmax']=2
            if option=='parent':meaning['source_span']='事件相对0到1.25秒计算theta功率'
            if option=='record':record='B'
            if option=='dimension':meaning['measurement_channels']=['ABSENT']
            if option=='range':meaning['range_span']='0到2秒'
            a,_=run_interpreted(text+'。','create_epochs',scope,meaning,record=record)
            self.assertFalse(a.working_memory.store.entries)
            self.assertFalse(a.working_memory.store.admitted_scopes)

    def test_field_relation_only_normalizes_channels_and_rejects_fact_conflicts(self):
        for option in ('valid','ambiguous','missing','window','target','cropped'):
            source='记录A SYNTH-C1在0到2秒RMS'
            target='记录B沿用前述通道在2到4秒RMS'
            if option=='target':target='记录B SYNTH-C2在2到4秒RMS'
            text=source+'；'+('记录A SYNTH-C2在1到3秒RMS；' if option=='ambiguous' else '')+target+'。'
            meaning={'source_span':target,'time_reference':'record_absolute','channel_reference':{'source_span':source,'target_span':target}}
            records=synthetic_records()
            if option=='missing':records['B']=replace(records['B'],channel_names=('Absent','SYNTH-C2'))
            if option=='cropped':meaning['channel_reference']['source_span']='SYNTH-C1在0到2秒RMS'
            scope={'channels':['SYNTH-C1'],'start':0 if option=='window' else 2,'end':2 if option=='window' else 4}
            agent,r=run_interpreted(text,'amplitude',scope,meaning,records=records,record='B')
            self.assertEqual(len(agent.working_memory.store.entries),1 if option=='valid' else 0)
            if option=='valid':
                self.assertEqual(r.stop_reason,'completed')
                self.assertEqual(agent.working_memory.store.entries[0].record,'B')
                self.assertEqual(len(agent.working_memory.store.contexts['A'].trace.events),0)

    def test_false_semantic_interpretation_is_not_certified_as_original_request_success(self):
        # Explicit limitation: a self-consistent but false interpretation is
        # not an EEG metadata contradiction. No string rule proves its intent.
        text='记录A先查看stimulus事件信息并计算SYNTH-C1在2到4秒的RMS'
        meaning={'source_span':text,'time_reference':'event_relative'}
        a,_=run_interpreted(text+'。','create_epochs',{'labels':['stimulus'],'tmin':2,'tmax':4},meaning)
        self.assertEqual(len(a.working_memory.store.entries),1)
        case={'evaluation_only':{'obligations':[{'key':'rms','turn':1,'record':'A','capability':'amplitude',
            'scope':{'channels':['SYNTH-C1'],'start':2,'end':4},'fields':[['SYNTH-C1','rms']]}]}}
        score=score_obligations(case,a.working_memory.store,1)
        self.assertFalse(score['all_required_results_correct'])
        self.assertIsNone(score['whole_request_correct'])

    def test_missing_window_interpretation_preserves_clarification_contract(self):
        text='记录A stimulus事件的SYNTH-C2通道计算theta功率'
        meaning={'source_span':text,'time_reference':'event_relative','measurement_channels':['SYNTH-C2']}
        a,_=run_interpreted(text+'。','create_epochs',{'labels':['stimulus']},meaning)
        store=a.working_memory.store
        self.assertFalse(store.entries)
        self.assertFalse(store.admitted_scopes)
        pending=[p for g in store.subgoals for p in g.pending_actions]
        self.assertTrue(any(p['code']=='MISSING_SCIENTIFIC_PARAMETER' and set(p['missing_fields'])=={'tmin','tmax'} for p in pending))

if __name__=='__main__':unittest.main()
