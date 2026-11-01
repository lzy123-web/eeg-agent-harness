"""Constructed interface interventions, not original messages or model success."""
from copy import deepcopy
from dataclasses import asdict, replace
import json
from pathlib import Path
import tempfile
import unittest

from eeg_harness.task_plan_agent import TaskPlanEEGAgent, ARMS
from eeg_harness.task_plan import task_spec_schema
from eeg_harness.scientific_contracts import validate_contract, ContractError, computation_scope
from eeg_harness.scientific_request_binding import source_catalog
from eeg_harness.research.task_memory import synthetic_records
from eeg_harness.research.working_memory_issue52 import protocol, audit_entries
from eeg_harness.research.working_memory_issue55_live import run_session
from test_task_plan_agent import InspectableScriptedClient, node, delivery, reference, payload
from test_working_memory import finish
from test_issue55_live import RawFake, setup


def native_batch(actions):
    return {'role':'assistant','content':None,'tool_calls':[{'id':f'batch-{i}','type':'function',
        'function':{'name':name,'arguments':json.dumps(args)}} for i,(name,args) in enumerate(actions)]}


def locator(messages,text,turn=None):
    rows=payload(messages)['scientific_source_frames']
    found=[r for r in rows if r['span']==text and (turn is None or r['turn']==turn)]
    if len(found)!=1:raise AssertionError((text,rows))
    return found[0]['source_ref']


class InterfacesTest(unittest.TestCase):
    def agent(self,actions,arm='C',records=None):
        c=InspectableScriptedClient(actions)
        return TaskPlanEEGAgent(c,records or synthetic_records(),arm=arm,session_id='issue56-test'),c

    def test_shared_derived_contract_rejects_at_exact_path_and_keeps_missing_scope(self):
        for arm in ARMS:
            with self.subTest(arm=arm):
                good=node('p',[delivery('out')]);bad=deepcopy(good);bad['required_outputs'][0]['scope']['band']='alpha'
                a,c=self.agent([('plan_tasks',{'nodes':[bad]}),('plan_tasks',{'nodes':[good]}),
                    ('revise_plan',{'task_id':'p','updates':{'required_outputs':[delivery('out',scope={'start':'bad'})]},'reason':'test invalid type'}),
                    ('psd',{'task_id':'p','output_key':'out'}),finish()],arm)
                result=a.run('记录A SYNTH-C1在0到2秒的alpha功率。')
                self.assertEqual(result.stop_reason,'completed',c.errors)
                self.assertEqual(result.tool_results[0]['data']['field_path'],['nodes',0,'required_outputs',0,'scope','band'])
                self.assertEqual(result.tool_results[2]['data']['field_path'],['updates','required_outputs',0,'scope','start'])
                self.assertEqual(a.working_memory.graph.nodes['p'].revision,1)
                registry=a.working_memory.store.contexts['A'].executor.registry
                schema=task_spec_schema(registry)
                for capability in ('psd','amplitude','create_epochs','event_bandpower','epoch_quality'):
                    d=delivery('missing',capability,{})
                    validate_contract(node('waiting',[d]),schema)
                    with self.assertRaises(ContractError):validate_contract(node('invalid',[delivery('x',capability,{'invented':1})]),schema)
                self.assertEqual(computation_scope(registry,'event_bandpower'),computation_scope(registry,'create_epochs'))

    def test_explicit_owners_keep_independent_batch_and_same_capability_outputs(self):
        for arm in ARMS:
            with self.subTest(arm=arm):
                scopes=[{'channels':['SYNTH-C1'],'start':0,'end':2},{'channels':['SYNTH-C1'],'start':2,'end':4}]
                nodes=[node('a',[delivery('early','amplitude',scopes[0]),delivery('late','amplitude',scopes[1])]),
                       node('b',[delivery('power','psd',scopes[0],record='B')])]
                a,c=self.agent([('plan_tasks',{'nodes':nodes}),native_batch([
                    ('select_task',{'task_id':'b'}),('select_task',{'task_id':'a'}),
                    ('psd',{'task_id':'b','output_key':'power','revision':1}),
                    ('amplitude',{'task_id':'a','output_key':'late'}),
                    ('amplitude',{'task_id':'a','output_key':'early'})]),finish()],arm)
                r=a.run('记录A SYNTH-C1在0到2秒和2到4秒分别计算RMS；记录B SYNTH-C1在0到2秒计算alpha功率。')
                self.assertEqual(r.stop_reason,'completed',c.errors)
                self.assertEqual([(e.record,e.parameters['start']) for e in a.working_memory.store.entries],[('B',0),('A',2),('A',0)])
                self.assertTrue(all(x['passed'] for x in audit_entries(a.working_memory.store)))
                ids=[r['request_id'] for r in r.tool_results];self.assertEqual(len(ids),len(set(ids)))
                self.assertEqual(len(a.working_memory.action_transitions),7)

    def test_wrong_owner_stale_revision_and_implicit_batch_never_compute(self):
        for defect in ('unknown','key','record','revision','boolean_revision','implicit'):
            with self.subTest(defect=defect):
                args={'task_id':'p','output_key':'out'}
                if defect=='unknown':args['task_id']='missing'
                if defect=='key':args['output_key']='missing'
                if defect=='record':args['record']='B'
                if defect=='revision':args['revision']=2
                if defect=='boolean_revision':args['revision']=True
                if defect=='implicit':args={}
                a,c=self.agent([('plan_tasks',{'nodes':[node('p',[delivery('out')])]}),
                    native_batch([('psd',args),('psd',args)]),finish('partial',unresolved=['test rejection'])])
                a.run('记录A SYNTH-C1在0到2秒计算alpha功率。')
                self.assertFalse(a.working_memory.store.entries)
                for t in a.working_memory.action_transitions[1:3]:self.assertEqual(t['before'],t['after'])

    def test_source_refs_support_field_relation_without_copying_text(self):
        source='记录A Lead-X在0.5到2.5秒计算RMS';target='记录B沿用前述通道在3到5秒计算RMS'
        records={k:replace(v,channel_names=('Lead-X','Lead-Y')) for k,v in synthetic_records().items()}
        for arm in ARMS:
            for defect in (None,'wrong_record','unknown','foreign_window','both_forms'):
                with self.subTest(arm=arm,defect=defect):
                    def plan(messages):
                        s,t=locator(messages,source),locator(messages,target)
                        meaning={'source_ref':t,'time_reference':'record_absolute','measurement_channels':['Lead-X'],
                                 'channel_reference':{'source_ref':s,'target_ref':t}}
                        if defect=='wrong_record':meaning['source_ref']=s
                        if defect=='unknown':meaning['source_ref']='u99:unknown:0:1'
                        if defect=='foreign_window':meaning['range_ref']=s
                        if defect=='both_forms':meaning['source_span']=target
                        d=delivery('rms','amplitude',{'channels':['Lead-X'],'start':3,'end':5},record='B');d['interpretation']=meaning
                        return 'plan_tasks',{'nodes':[node('b',[d])]}
                    a,c=self.agent([plan,('amplitude',{'task_id':'b','output_key':'rms'}),
                        finish('partial' if defect else 'completed',unresolved=['test negative'] if defect else [])],arm,records)
                    r=a.run(source+'；'+target+'。')
                    self.assertEqual(len(a.working_memory.store.entries),0 if defect else 1,c.errors)
                    if not defect:self.assertEqual(r.stop_reason,'completed')
                    else:self.assertFalse(a.working_memory.store.admitted_scopes)

    def test_historical_locator_current_supplement_and_original_artifact_chain(self):
        first='记录A stimulus事件上SYNTH-C2的theta功率，窗口尚未决定；记录B SYNTH-C1在2到4秒RMS。'
        supplement='事件相对窗口为0到1.25秒。'
        for arm in ARMS:
            with self.subTest(arm=arm):
                saved={}
                def plan(messages):
                    saved['source']=locator(messages,'记录A stimulus事件上SYNTH-C2的theta功率')
                    ep=delivery('ep','create_epochs',{'labels':['stimulus']});ep['interpretation']={
                        'source_ref':saved['source'],'time_reference':'event_relative','measurement_channels':['SYNTH-C2']}
                    return 'plan_tasks',{'nodes':[node('ep',[ep]),node('b',[delivery('rms','amplitude',{'channels':['SYNTH-C1'],'start':2,'end':4},record='B')]),
                        node('power',[delivery('theta','event_bandpower',{},refs=[reference('ep','ep')])],deps=['ep'])]}
                def revise(messages):
                    ep=delivery('ep','create_epochs',{'labels':['stimulus'],'tmin':0,'tmax':1.25})
                    ep['interpretation']={'source_ref':saved['source'],'range_ref':locator(messages,'事件相对窗口为0到1.25秒'),
                        'time_reference':'event_relative','measurement_channels':['SYNTH-C2']}
                    return 'revise_plan',{'task_id':'ep','updates':{'required_outputs':[ep]},'reason':'user supplied window'}
                ask=finish('partial',unresolved=['missing window']);ask[1]['clarifications']=[{'task_id':'ep','key':'ep','fields':['tmin','tmax']}]
                a,c=self.agent([plan,('amplitude',{'task_id':'b','output_key':'rms'}),('wait_node',{'task_id':'ep','reason':'missing window'}),ask,
                    revise,native_batch([('create_epochs',{'task_id':'ep','output_key':'ep'}),('event_bandpower',{'task_id':'power','output_key':'theta'})]),finish(),
                    ('plan_tasks',{'nodes':[node('quality',[delivery('q','epoch_quality',{},refs=[reference('ep','ep',level='process')])],deps=['ep'])]}),
                    ('read_dependency',{'task_id':'ep','key':'ep','level':'process'}),('epoch_quality',{'task_id':'quality','output_key':'q'}),finish()],arm)
                r=a.run(first);self.assertEqual(r.stop_reason,'partial',c.errors);b=a.working_memory.store.entries[0]
                r=a.continue_run(supplement);self.assertEqual(r.stop_reason,'completed',c.errors)
                r=a.continue_run('沿用记录A原试次进行质量检查，不重新建立试次。');self.assertEqual(r.stop_reason,'completed',c.errors)
                entries=a.working_memory.store.entries;self.assertEqual(entries[0],b)
                self.assertEqual([e.capability for e in entries],['amplitude','create_epochs','event_bandpower','epoch_quality'])
                self.assertEqual(len({e.evidence['binding']['artifact_id'] for e in entries[1:]}),1)
                self.assertTrue(all(row['passed'] for row in audit_entries(a.working_memory.store)))

    def test_internal_waiting_plus_unrelated_answer_cannot_receive_gold(self):
        case=next(c for c in protocol()['cases'] if c['id']=='T03')
        for question in ('none','unrelated','valid','incomplete','known_window','fake_missing','missing_independent'):
            with self.subTest(question=question), tempfile.TemporaryDirectory() as td:
                scope={'labels':['stimulus']}
                if question=='known_window':scope.update(tmin=0,tmax=1.25)
                ccase=deepcopy(case)
                if question=='fake_missing':ccase['requests'][0]+='记录A stimulus事件相对0到1.25秒。'
                nodes=[node('b',[delivery('rms','amplitude',{'channels':['SYNTH-C1'],'start':2,'end':4},record='B')]),
                       node('ep',[delivery('ep','create_epochs',scope)])]
                done=finish('partial',unresolved=['waiting']);done[1]['answer']='请告诉我你喜欢什么颜色。' if question=='unrelated' else '已保留真实结果。'
                if question not in ('none','unrelated'):
                    done[1]['clarifications']=[{'task_id':'ep','key':'ep','fields':['tmin'] if question=='incomplete' else ['tmin','tmax']}]
                actions=[('plan_tasks',{'nodes':nodes})]
                if question!='missing_independent':actions.append(('amplitude',{'task_id':'b','output_key':'rms'}))
                actions += [('wait_node',{'task_id':'ep','reason':'missing window'}),done,finish('partial',unresolved=['TEST stop'])]
                raw=RawFake(actions);root=Path(td);ledger,att=setup(root,raw)
                run_session(raw,ledger,att,ccase,root/'run',test_only=True)
                self.assertEqual((root/'run/turn-2.json').exists(),question=='valid')
                if question=='valid':
                    first=json.loads((root/'run/turn-1.json').read_text(encoding='utf8'))
                    self.assertIn('tmin, tmax',first['accepted_final_answer'])

    def test_revision_uses_current_range_ref_retains_old_values_and_unrelated_record(self):
        for defect in (None,'old_range','other_record','stale_source'):
            with self.subTest(defect=defect):
                saved={}
                def plan(messages):
                    saved['a']=locator(messages,'记录A SYNTH-C1在0到2秒alpha功率')
                    saved['b']=locator(messages,'记录B SYNTH-C1在2到4秒RMS')
                    d=delivery('p');d['interpretation']={'source_ref':saved['a'],'time_reference':'record_absolute'}
                    return 'plan_tasks',{'nodes':[node('a',[d]),node('b',[delivery('r','amplitude',{'channels':['SYNTH-C1'],'start':2,'end':4},record='B')])]}
                def revise(messages):
                    d=delivery('p',scope={'channels':['SYNTH-C1'],'start':4,'end':6})
                    meaning={'source_ref':saved['a'],'time_reference':'record_absolute'}
                    if defect!='old_range':meaning['range_ref']=saved['b'] if defect=='other_record' else locator(messages,'记录A窗口改为4到6秒')
                    if defect=='stale_source':meaning['source_ref']=saved['a'].replace('u1:','u7:')
                    d['interpretation']=meaning
                    return 'revise_plan',{'task_id':'a','updates':{'required_outputs':[d]},'reason':'user changed A window'}
                steps=[plan,native_batch([('psd',{'task_id':'a','output_key':'p'}),('amplitude',{'task_id':'b','output_key':'r'})]),finish(),
                    revise,('psd',{'task_id':'a','output_key':'p','revision':2})]
                if not defect:
                    steps += [('plan_tasks',{'nodes':[node('delta',[delivery('d','compare_results',{},refs=[
                        {**reference('a','p',fields=[['SYNTH-C1','alpha']]),'revision':1},reference('a','p',fields=[['SYNTH-C1','alpha']])])],deps=['a'])]}),
                        ('compare_results',{'task_id':'delta','output_key':'d'}),finish()]
                else:steps += [finish('partial',unresolved=['test rejected invalid history'])]
                a,c=self.agent(steps);self.assertEqual(a.run('记录A SYNTH-C1在0到2秒alpha功率；记录B SYNTH-C1在2到4秒RMS。').stop_reason,'completed',c.errors)
                old=list(a.working_memory.store.entries)
                r=a.continue_run('记录A窗口改为4到6秒；与之前alpha功率比较，记录B保留原结果。')
                self.assertEqual(a.working_memory.store.entries[:2],old)
                self.assertEqual(len(a.working_memory.store.entries),2 if defect else 3,c.errors)
                if not defect:
                    self.assertEqual(r.stop_reason,'completed',c.errors)
                    self.assertEqual(a.working_memory.store.entries[-1].revision_of,old[0].task_id)
                    self.assertEqual(len(a.working_memory.comparisons),1)

    def test_explicit_owner_allows_declared_optional_observation_not_arbitrary_tool(self):
        for allowed in (True,False):
            a,c=self.agent([('plan_tasks',{'nodes':[node('p',[delivery('out')],optional=['record_quality'] if allowed else [])]}),
                native_batch([('record_quality',{'task_id':'p','channels':['SYNTH-C1'],'start':0,'end':2}),
                              ('psd',{'task_id':'p','output_key':'out'})]),finish()])
            r=a.run('记录A SYNTH-C1在0到2秒alpha功率，必要时检查相同范围的数据质量。')
            self.assertEqual(r.stop_reason,'completed',c.errors)
            self.assertEqual(len(a.working_memory.store.entries),2 if allowed else 1)


if __name__=='__main__':unittest.main()
