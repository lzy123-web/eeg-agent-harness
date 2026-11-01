"""Shared role/field-reference integration; original requests and real tools."""
from dataclasses import replace
import unittest
from eeg_harness.task_plan_agent import TaskPlanEEGAgent
from eeg_harness.events import EEGEvent, EventSet
from eeg_harness.research.task_memory import synthetic_records
from eeg_harness.research.working_memory_issue52 import run_case, controlled_steps
from test_task_plan_agent import InspectableScriptedClient, node, delivery
from test_working_memory import finish

ARMS=('A','B','C','A-equivalent')

class ScopeRepairTest(unittest.TestCase):
    def test_original_t04_proposed_reference_is_not_confirmed_selection(self):
        for arm in ARMS:
            actions=controlled_steps('T04')
            actions[0][2][1]['channel_reference']={
                'source_span':'记录A的SYNTH-C1只分析0到2秒的RMS',
                'target_span':'记录B的同名通道只分析2到4秒的RMS'}
            row=run_case('T04',arm,actions=actions)
            self.assertEqual(row['metrics']['stop_reasons'],['partial'])
            self.assertEqual(row['metrics']['numeric_executions'],1)
            self.assertTrue(all(r['passed'] for r in row['oracle']))

    def test_original_t07_same_actions_both_turns_and_original_artifact(self):
        for arm in ARMS:
            row=run_case('T07',arm)
            self.assertEqual(row['metrics']['stop_reasons'],['completed','completed'])
            self.assertEqual(row['metrics']['numeric_executions'],4)
            self.assertTrue(all(r['passed'] for r in row['oracle']))

    def channel_run(self, *, arm="C", ambiguous=False, missing=False, source_missing=False, cropped=False, swap=False, wrong_record=False, confirmed=True):
        records={k:replace(v,channel_names=('Lead-X','Lead-Y')) for k,v in synthetic_records().items()}
        if missing: records['B']=replace(records['B'],channel_names=('Absent','Lead-Y'))
        if source_missing: records['A']=replace(records['A'],channel_names=('Absent','Lead-Y'))
        source='记录A Lead-X在0.5到2.5秒计算RMS'
        target='记录B沿用前述通道选择'+('Lead-X' if confirmed else '')+'在3到5秒计算RMS'
        text=source+'；'+('记录A Lead-Y在1到3秒计算RMS；' if ambiguous else '')+target+'。'
        scope={'channels':['Lead-X'],'start':0.5 if swap else 3,'end':2.5 if swap else 5}
        ref={'source_span':source,'target_span':target if not cropped else '3到5秒计算RMS'}
        alias='A' if wrong_record else 'B'
        client=InspectableScriptedClient([('plan_tasks',{'nodes':[node('destination',[
            delivery('r','amplitude',scope,record=alias)])]}),('amplitude',{'channel_reference':ref}),
            ('finish_task',{'status':'partial','answer':'保留实际结果','unresolved':['测试停止']})])
        agent=TaskPlanEEGAgent(client,records,arm=arm)
        agent.run(text)
        return agent.working_memory.store

    def test_unconfirmed_proposal_rejects_without_mutating_authority(self):
        for arm in ARMS:
            store=self.channel_run(arm=arm,confirmed=False)
            self.assertEqual(len(store.entries),0)
            self.assertFalse(any(f['record']=='B' and 'channels' in f['sources'] for f in store.admitted_scopes))

    def test_reviewer_window_owner_full_execution_chain(self):
        for arm in ARMS:
            for tool,scope,expected in [
                ('create_epochs',{'labels':['stimulus'],'tmin':2,'tmax':4},0),
                ('amplitude',{'channels':['SYNTH-C1'],'start':2,'end':4},1)]:
                client=InspectableScriptedClient([('plan_tasks',{'nodes':[node('x',[delivery('o',tool,scope)])]}),
                    (tool,{}),('finish_task',{'status':'partial','answer':'实际结果','unresolved':['未提供事件窗']})])
                agent=TaskPlanEEGAgent(client,synthetic_records(),arm=arm)
                agent.run('记录A先查看stimulus事件信息并计算SYNTH-C1在2到4秒的RMS。')
                self.assertEqual(sum(len(c.trace.events) for c in agent.working_memory.store.contexts.values()),expected)

    def test_renamed_mixed_ownership_in_both_orders(self):
        records={k:replace(v,channel_names=('Lead-X','Lead-Y'),events=EventSet(tuple(
            EEGEvent('pulse' if e.label=='stimulus' else 'rest',e.onset_seconds)
            for e in v.events.events),v.events.source)) for k,v in synthetic_records().items()}
        for arm in ARMS:
            for text in ('记录B查看pulse事件并计算Lead-Y在1.5到3.5秒的RMS。',
                         '记录B计算Lead-Y在1.5到3.5秒的RMS并查看pulse事件。'):
                for tool,scope,count in [('create_epochs',{'labels':['pulse'],'tmin':1.5,'tmax':3.5},0),
                                        ('amplitude',{'channels':['Lead-Y'],'start':1.5,'end':3.5},1)]:
                    client=InspectableScriptedClient([('plan_tasks',{'nodes':[node('x',[delivery('o',tool,scope,record='B')])]}),
                        (tool,{}),finish('partial',unresolved=['停止测试'])])
                    agent=TaskPlanEEGAgent(client,records,arm=arm)
                    agent.run(text)
                    self.assertEqual(sum(len(c.trace.events) for c in agent.working_memory.store.contexts.values()),count)

    def test_user_confirmation_resumes_original_task_without_reusing_source_record(self):
        scope={'channels':['SYNTH-C1'],'start':2,'end':4}
        for arm in ARMS:
            client=InspectableScriptedClient([
                ('plan_tasks',{'nodes':[node('destination',[delivery('r','amplitude',scope,record='B')])]}),
                ('amplitude',{'channel_reference':{'source_span':'记录A SYNTH-C1在0到2秒RMS','target_span':'记录B在2到4秒RMS'}}),
                finish('clarification_required',unresolved=['请确认记录B通道']),
                ('select_task',{'task_id':'destination'}),('amplitude',{}),finish()])
            agent=TaskPlanEEGAgent(client,synthetic_records(),arm=arm)
            first=agent.run('记录A SYNTH-C1在0到2秒RMS；记录B在2到4秒RMS。')
            self.assertEqual(first.stop_reason,'clarification_required')
            self.assertEqual(len(agent.working_memory.store.entries),0)
            last=agent.continue_run('确认记录B SYNTH-C1在2到4秒的RMS。')
            self.assertEqual(last.stop_reason,'completed')
            self.assertEqual(len(agent.working_memory.graph.nodes),1)
            self.assertEqual(agent.working_memory.store.entries[0].record,'B')
            self.assertEqual(len(agent.working_memory.store.contexts['A'].trace.events),0)

    def test_subsequent_ranges_do_not_revive_a_previous_object(self):
        for arm in ARMS:
            for channel,count in [('SYNTH-C1',0),('SYNTH-C2',1)]:
                scope={'channels':[channel],'start':4,'end':6}
                client=InspectableScriptedClient([('plan_tasks',{'nodes':[node('x',[delivery('r','amplitude',scope)])]}),
                    ('amplitude',{}),finish('partial',unresolved=['测试'])])
                agent=TaskPlanEEGAgent(client,synthetic_records(),arm=arm)
                agent.run('记录A SYNTH-C1在0到2秒与SYNTH-C2在2到4秒和4到6秒分别计算RMS。')
                self.assertEqual(len(agent.working_memory.store.entries),count)

    def test_unique_reference_only_copies_names_to_destination(self):
        store=self.channel_run()
        self.assertEqual(len(store.entries),1)
        e=store.entries[0]
        self.assertEqual(e.record,'B')
        self.assertEqual(e.parameters['start'],3)
        self.assertEqual(len(store.contexts['A'].trace.events),0)

    def test_ambiguous_missing_channel_cropped_parent_swapped_time_and_record_rejected(self):
        for arm in ARMS:
            for option in ('ambiguous','missing','source_missing','cropped','swap','wrong_record'):
                with self.subTest(arm=arm,option=option):
                    store=self.channel_run(arm=arm,**{option:True})
                    self.assertEqual(len(store.entries),0)
                    self.assertFalse(any(c.trace.events for c in store.contexts.values()))

    def test_renamed_event_and_channel_are_roles_not_foreign_time_domains(self):
        for arm in ARMS:
            records={k:replace(v,channel_names=('Lead-X','Lead-Y'),events=EventSet(tuple(
                EEGEvent('pulse' if e.label=='stimulus' else 'rest',e.onset_seconds)
                for e in v.events.events),v.events.source)) for k,v in synthetic_records().items()}
            scope={'labels':['pulse'],'tmin':-.25,'tmax':1.25}
            client=InspectableScriptedClient([('plan_tasks',{'nodes':[node('event',[
                delivery('e','create_epochs',scope)])]}),('create_epochs',{}),finish()])
            agent=TaskPlanEEGAgent(client,records,arm=arm)
            r=agent.run('记录A pulse事件相对-0.25到1.25秒建立试次，报告Lead-Y的结果。不做基线校正。')
            self.assertEqual(r.stop_reason,'completed')
            self.assertEqual(len(agent.working_memory.store.entries),1)

    def test_unseparated_two_time_domains_remain_ambiguous(self):
        for arm in ARMS:
            scope={'labels':['stimulus'],'tmin':2,'tmax':4}
            client=InspectableScriptedClient([('plan_tasks',{'nodes':[node('event',[
                delivery('e','create_epochs',scope)])]}),('create_epochs',{}),
                ('finish_task',{'status':'partial','answer':'歧义','unresolved':['范围歧义']})])
            agent=TaskPlanEEGAgent(client,synthetic_records(),arm=arm)
            agent.run('记录A stimulus事件后0到1.25秒与SYNTH-C1在2到4秒分析。')
            self.assertEqual(len(agent.working_memory.store.entries),0)

    def test_event_interval_cannot_authorize_continuous_channel(self):
        for arm in ARMS:
            client=InspectableScriptedClient([('plan_tasks',{'nodes':[node('raw',[
                delivery('r','amplitude',{'channels':['SYNTH-C2'],'start':0,'end':1.25})])]}),
                ('amplitude',{}),('finish_task',{'status':'partial','answer':'拒绝','unresolved':['无连续授权']})])
            agent=TaskPlanEEGAgent(client,synthetic_records(),arm=arm)
            agent.run('记录A stimulus事件后0到1.25秒试次上SYNTH-C2的theta功率。')
            self.assertEqual(len(agent.working_memory.store.entries),0)

if __name__=='__main__':unittest.main()
