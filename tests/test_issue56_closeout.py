"""Constructed integration witnesses for review 6558208733, not model history."""
from copy import deepcopy
from dataclasses import asdict, replace
import json
from pathlib import Path
import tempfile
import unittest
from eeg_harness.task_plan_agent import TaskPlanEEGAgent
from eeg_harness.scientific_request_binding import _request_frames
from eeg_harness.research.task_memory import synthetic_records
from eeg_harness.research.working_memory_issue52 import protocol, audit_entries
from test_task_plan_agent import InspectableScriptedClient, node, delivery, reference
from test_issue56_interfaces import locator, native_batch
from test_issue55_live import RawFake, setup, run_session
from eeg_harness.research.working_memory_issue55_live import scored_case
from test_working_memory import finish


def clarification_case(request, *, scope=None, fields=None, question=True, independent=True, followup_request=None):
    """Actual existing live runner, TEST authorization/rates and temporary ledger."""
    scope={'labels':['stimulus']} if scope is None else scope
    fields=['tmin','tmax'] if fields is None else fields
    case=scored_case(next(c for c in protocol()['cases'] if c['id']=='T03'),'development')
    case['id']='TEST-ISSUE56-CLOSEOUT'
    case['requests'][0]=request
    if followup_request:case['requests'][1]=followup_request
    nodes=[node('b',[delivery('rms','amplitude',{'channels':['SYNTH-C1'],'start':2,'end':4},record='B')]),
           node('ep',[delivery('ep','create_epochs',scope)]),
           node('power',[delivery('theta','event_bandpower',{},refs=[reference('ep','ep')])],deps=['ep'])]
    ask=finish('partial',unresolved=['window']);ask[1]['answer']='已保留独立结果。'
    if question:ask[1]['clarifications']=[{'task_id':'ep','key':'ep','fields':fields}]
    actions=[('plan_tasks',{'nodes':nodes})]
    if independent:actions.append(('amplitude',{'task_id':'b','output_key':'rms'}))
    actions += [('wait_node',{'task_id':'ep','reason':'model omitted window'}),ask,
        ('revise_plan',{'task_id':'ep','updates':{'required_outputs':[delivery('ep','create_epochs',{'labels':['stimulus'],'tmin':0,'tmax':1.25})]},'reason':'user supplement'}),
        ('create_epochs',{'task_id':'ep','output_key':'ep'}),('event_bandpower',{'task_id':'power','output_key':'theta'}),finish()]
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);raw=RawFake(actions);ledger,att=setup(root,raw)
        run_session(raw,ledger,att,case,root/'run',test_only=True)
        turns=[json.loads(p.read_text(encoding='utf8')) for p in sorted((root/'run').glob('turn-*.json'))]
        fp=root/'run/followup-1.json'
        # SourceFrame audit uses actual records and parser; no surrogate metadata.
        a=TaskPlanEEGAgent(InspectableScriptedClient([]),synthetic_records())
        frames=[asdict(f) for f in _request_frames(a.working_memory.store,request)]
        return {'class':'constructed_actual_Agent_Store_Executor_Fake_live_not_historical_model',
            'request':request,'actions':actions,'frames':frames,'turns':turns,
            'followup':json.loads(fp.read_text(encoding='utf8')) if fp.exists() else None}


def reference_revision(defect=None, arm='C'):
    saved={};source='记录A SYNTH-C1在0到2秒计算RMS';target='记录B沿用前述通道在2到4秒计算RMS'
    current='记录B窗口改为4到6秒或5到7秒' if defect=='ambiguous_window' else '记录B窗口改为4到6秒'
    def plan(messages):
        saved['source']=locator(messages,source);saved['target']=locator(messages,target)
        meaning={'source_ref':saved['target'],'time_reference':'record_absolute',
            'measurement_channels':['SYNTH-C1'],'channel_reference':{'source_ref':saved['source'],'target_ref':saved['target']}}
        saved['meaning']=meaning
        b=delivery('r','amplitude',{'channels':['SYNTH-C1'],'start':2,'end':4},record='B');b['interpretation']=meaning
        return 'plan_tasks',{'nodes':[node('a',[delivery('r','amplitude',{'channels':['SYNTH-C1'],'start':0,'end':2})]),node('b',[b])]}
    def revise(messages):
        meaning=deepcopy(saved['meaning']);meaning['range_ref']=locator(messages,current)
        if defect=='foreign_window':meaning['range_ref']=saved['source']
        if defect=='old_window':meaning['range_ref']=saved['target']
        if defect=='unknown':meaning['source_ref']='u99:unknown:0:1'
        if defect=='wrong_target':meaning['channel_reference']['target_ref']=saved['source']
        scope={'channels':['SYNTH-C1'],'start':4,'end':6}
        if defect=='old_scope':scope.update(start=2,end=4);meaning.pop('range_ref')
        b=delivery('r','amplitude',scope,record='B');b['interpretation']=meaning
        return 'revise_plan',{'task_id':'b','updates':{'required_outputs':[b]},'reason':'user changed B window'}
    actions=[plan,native_batch([('amplitude',{'task_id':'a','output_key':'r'}),('amplitude',{'task_id':'b','output_key':'r'})]),finish(),
        revise,('amplitude',{'task_id':'b','output_key':'r','revision':2}),
        ('read_dependency',{'task_id':'b','key':'r','revision':1,'level':'result','fields':[['SYNTH-C1','rms']]}),
        finish('partial' if defect else 'completed',unresolved=['test negative'] if defect else [])]
    client=InspectableScriptedClient(actions);a=TaskPlanEEGAgent(client,synthetic_records(),arm=arm,session_id='issue56-closeout')
    first=a.run(source+'；'+target+'。');old=[asdict(e) for e in a.working_memory.store.entries]
    old_oracle=audit_entries(a.working_memory.store)
    if defect=='missing_channel':
        # An actual target metadata change invalidates the binding; never substitute A data.
        context=a.working_memory.store.contexts['B']
        context.record=replace(context.record,channel_names=('OTHER','SYNTH-C2'))
        a.working_memory.store.records['B']=context.record
    second=a.continue_run(current+'；记录A保持原结果。')
    return {'class':'constructed_two_turn_actual_Agent_Store_Executor_not_model_history','defect':defect,'arm':arm,
        'turns':[first.to_dict(),second.to_dict()],'old_entries':old,
        'entries':[asdict(e) for e in a.working_memory.store.entries],
        'oracle':old_oracle if defect=='missing_channel' else audit_entries(a.working_memory.store),
        'oracle_basis':'original record snapshot before metadata change' if defect=='missing_channel' else 'current records',
        'fixture_errors':client.errors}


class CloseoutTest(unittest.TestCase):
    def test_owned_adjacent_window_is_not_missing_but_other_objects_are(self):
        tail='；记录B SYNTH-C1在2到4秒RMS。'
        cases=[('same','记录A stimulus事件试次在0到1.25秒',False),
            ('adjacent','记录A stimulus事件试次，事件相对窗口为0到1.25秒',False),
            ('absent','记录A stimulus事件试次',True),
            ('other_record','记录B stimulus事件相对窗口为0到1.25秒；记录A stimulus事件试次',True),
            ('other_object','记录A control事件相对窗口为0到1.25秒；记录A stimulus事件试次',True),
            ('ambiguous_record','记录A和记录B stimulus事件试次，窗口0到1.25秒',False),
            ('conflict','记录A stimulus事件试次，窗口0到1.25秒，窗口0到1.5秒',False)]
        for label,request,allowed in cases:
            with self.subTest(label=label):
                kwargs={'followup_request':'记录A stimulus事件相对窗口为0到1.25秒；记录B保持原结果。'} if label=='other_object' else {}
                r=clarification_case(request+tail,**kwargs)
                self.assertEqual(bool(r['followup'] and r['followup']['allowed']),allowed)
                self.assertEqual(len(r['turns']),2 if allowed else 1)
                if allowed:self.assertEqual(r['turns'][1]['result']['stop_reason'],'completed')

    def test_partial_endpoint_and_missing_independent_work(self):
        request='记录A stimulus事件试次，起点为0秒；记录B SYNTH-C1在2到4秒RMS。'
        r=clarification_case(request,scope={'labels':['stimulus'],'tmin':0},fields=['tmax'])
        self.assertTrue(r['followup']['allowed']);self.assertEqual(r['turns'][1]['result']['stop_reason'],'completed')
        for changes in ({'question':False},{'independent':False}):
            with self.subTest(changes=changes):
                r=clarification_case('记录A stimulus事件试次；记录B SYNTH-C1在2到4秒RMS。',**changes)
                self.assertFalse(r['followup']['allowed'])

    def test_channel_name_reference_survives_target_window_revision(self):
        for arm in ('A','B','C'):
            with self.subTest(arm=arm):
                r=reference_revision(arm=arm)
                self.assertEqual([t['stop_reason'] for t in r['turns']],['completed','completed'],r['fixture_errors'])
                self.assertEqual(len(r['entries']),3)
                self.assertEqual(r['entries'][:2],r['old_entries'])
                self.assertEqual(r['entries'][-1]['revision_of'],r['old_entries'][1]['task_id'])
                self.assertEqual(r['entries'][-1]['record'],'B')
                self.assertTrue(all(x['passed'] for x in r['oracle']))
                read=r['turns'][1]['tool_results'][-2];self.assertTrue(read['success'])

    def test_invalid_reference_revisions_are_atomic(self):
        for defect in ('foreign_window','old_window','old_scope','unknown','wrong_target','ambiguous_window','missing_channel'):
            with self.subTest(defect=defect):
                r=reference_revision(defect)
                self.assertEqual(len(r['entries']),2)
                self.assertEqual(r['entries'],r['old_entries'])
                change=next(t for t in r['turns'][1]['working_memory']['action_transitions'] if t['tool']=='revise_plan')
                self.assertFalse(change['success']);self.assertEqual(change['before'],change['after'])


if __name__=='__main__':unittest.main()
