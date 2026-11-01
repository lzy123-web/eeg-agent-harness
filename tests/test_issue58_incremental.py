"""Finite graph/transaction counterexamples and actual two-turn EEG chains."""
from copy import deepcopy
import json
import unittest
import tempfile
from pathlib import Path

from eeg_harness.task_plan import PlanGraph
from eeg_harness.task_plan_agent import TaskPlanEEGAgent, ARMS
from eeg_harness.research.task_memory import synthetic_records
from eeg_harness.research.working_memory_issue52 import run_case
from eeg_harness.research.working_memory_issue58 import incremental_steps
from test_task_plan import task, output, ref
from test_task_plan_agent import node, delivery, InspectableScriptedClient
from test_working_memory import finish


class IncrementalGraphTest(unittest.TestCase):
    def test_derived_data_readiness_and_explicit_control_remain_distinct(self):
        g=PlanGraph()
        g.submit([task('source',outputs=[output('power'),output('pending')]),
            task('data',outputs=[output(refs=[ref('source')])]),
            {**task('controlled',outputs=[output(refs=[ref('source')])]),'control_dependencies':['source']}])
        self.assertFalse(g.dependency_state('data')['ready'])
        g.mark_output('source','power',{'result_id':'actual'})
        g.nodes['source'].status='WAITING_INPUT'
        self.assertTrue(g.dependency_state('data')['ready'])
        self.assertFalse(g.dependency_state('controlled')['ready'])
        g.nodes['source'].status='TASK_COMPLETED'
        self.assertTrue(g.dependency_state('controlled')['ready'])
        self.assertEqual(g.dependency_relations(g.nodes['data'])['data'][0]['source'],'input_refs')

    def test_current_cycles_unknown_and_pinned_history_have_different_edges(self):
        g=PlanGraph();g.submit([task('a'),task('b',outputs=[output(refs=[ref('a')])])])
        g.mark_output('a','power',{'result_id':'old'});g.nodes['a'].status='TASK_COMPLETED'
        before=g.to_dict()
        for change in ({'required_outputs':[output(refs=[ref('b')])]},
                       {'required_outputs':[output(refs=[ref('missing')])]},
                       {'required_outputs':[output(refs=[{**ref('a'),'revision':99}])]}):
            with self.assertRaises(ValueError):g.revise('a',change,'invalid')
            self.assertEqual(g.to_dict(),before)
        g.revise('a',{'required_outputs':[output(start=4,end=6)]},'new range')
        g.submit([task('history',outputs=[output(refs=[{**ref('a'),'revision':1}])])])
        self.assertTrue(g.dependency_state('history')['ready'])
        self.assertFalse(g.dependency_state('b')['ready'])
        # Historical A1 does not create a cycle with current A2 -> history.
        g.revise('a',{'required_outputs':[output(start=4,end=6,refs=[ref('history')])]},'current depends on historical analysis')
        self.assertEqual(g.resolve_ref({**ref('a'),'revision':1})['output']['result_id'],'old')
        with self.assertRaises(ValueError):
            g.revise('history',{'control_dependencies':['a']},'real control cycle')

    def test_adding_a_data_reference_cannot_erase_an_existing_legacy_control(self):
        g=PlanGraph();g.submit([task('source'),task('consumer',deps=['source'])])
        g.mark_output('source','power',{'result_id':'actual'});g.nodes['source'].status='WAITING_INPUT'
        self.assertFalse(g.dependency_state('consumer')['ready'])
        g.revise('consumer',{'required_outputs':[output(refs=[ref('source')])]},'add data, keep control')
        self.assertEqual(g.nodes['consumer'].control_dependencies,['source'])
        self.assertFalse(g.dependency_state('consumer')['ready'])
        g.nodes['source'].status='TASK_COMPLETED'
        self.assertTrue(g.dependency_state('consumer')['ready'])

    def test_derived_consumers_invalidate_but_pinned_and_independent_results_survive(self):
        g=PlanGraph();g.submit([task('a'),task('following',outputs=[output(refs=[ref('a')])]),
            task('pinned',outputs=[output(refs=[{**ref('a'),'revision':1}])]),task('independent')])
        for n in g.nodes.values():g.mark_output(n.task_id,'power',{'result_id':n.task_id});n.status='TASK_COMPLETED'
        change=g.revise('a',{'required_outputs':[output(start=4,end=6)]},'new window')
        self.assertEqual(change['invalidated'],['following'])
        self.assertEqual(g.nodes['pinned'].outputs['power']['result_id'],'pinned')
        self.assertEqual(g.nodes['independent'].outputs['power']['result_id'],'independent')


class IncrementalAgentTest(unittest.TestCase):
    def test_original_two_turn_tasks_six_arms_real_tools_and_no_recomputation(self):
        schemas=[]
        for case in ('T05','T07'):
            for arm in ARMS:
                with self.subTest(case=case,arm=arm):
                    r=run_case(case,arm,actions=incremental_steps(case))
                    self.assertEqual(r['metrics']['stop_reasons'],['completed','completed'])
                    self.assertFalse(r['metrics']['controlled_errors'])
                    self.assertTrue(all(x['passed'] for x in r['oracle']))
                    self.assertEqual(r['metrics']['duplicate_numeric_invocations'],0)
                    schemas.append(r['decisions'][0]['tools'])
                    w1,w2=[x['working_memory'] for x in r['raw_agent_results']]
                    if case=='T05':
                        old=next(n for n in w1['plan'] if n['task_id']=='alpha')
                        new=next(n for n in w2['plan'] if n['task_id']=='alpha')
                        self.assertEqual(new['revision_history'][0]['snapshot']['outputs'],old['outputs'])
                        self.assertEqual(new['required_outputs'][0]['scope'],{'channels':['SYNTH-C1'],'start':4,'end':6})
                        b1=next(n for n in w1['plan'] if n['task_id']=='b')
                        b2=next(n for n in w2['plan'] if n['task_id']=='b')
                        self.assertEqual(b1,b2)
                    else:
                        epochs=next(n for n in w1['plan'] if n['task_id']=='epochs')['outputs']['ep']
                        quality=next(n for n in w2['plan'] if n['task_id']=='quality')['outputs']['quality']
                        self.assertEqual(quality['input_artifact'],epochs['output_artifact'])
                        power1=next(n for n in w1['plan'] if n['task_id']=='power')
                        self.assertEqual(power1,next(n for n in w2['plan'] if n['task_id']=='power'))
                        q=next(t['data']['observation']['result']['data'] for t in r['raw_agent_results'][1]['tool_results'] if t['tool_name']=='epoch_quality')
                        self.assertIn('flagged_epoch_indices',q)
                        self.assertTrue(q)
        self.assertTrue(all(s==schemas[0] for s in schemas))

    def test_bad_incremental_targets_fields_sources_are_atomic(self):
        request='记录A的SYNTH-C1在0到2秒计算功率；记录B的SYNTH-C1在2到4秒计算RMS。'
        def start(messages):
            frames=json.loads(messages[1]['content'])['scientific_source_frames']
            d=delivery('power');d['interpretation']={'source_ref':frames[0]['source_ref'],'time_reference':'record_absolute'}
            return 'plan_tasks',{'nodes':[node('a',[d]),node('b',[delivery('rms','amplitude',{'channels':['SYNTH-C1'],'start':2,'end':4},record='B')])]}
        variants=[{'task_id':'missing'},{'output_key':'missing'},{'revision':0},{'revision':True},{'revision':99},
                  {'changes':{'record':'B'}},{'changes':{'scope':{'typo':4}}},
                  {'changes':{'scope':{'start':4,'end':6}}},
                  {'changes':{'scope':{'start':4,'end':6},'interpretation':{'time_reference':'event_relative'}}},
                  {'changes':{'scope':{'start':4,'end':6},'interpretation':{'source_ref':'unknown'}}},
                  {'changes':{'scope':{'start':4,'end':6},'interpretation':{'source_ref':'B_SOURCE'}}},
                  {'changes':{'scope':{'start':4,'end':6},'interpretation':{'range_ref':'CURRENT','time_reference':'event_relative'}}},
                  {'changes':{'scope':{'start':4,'end':7},'interpretation':{'range_ref':'CURRENT'}}},
                  {'changes':{'input_refs':[{'task_id':'missing','key':'power'}]}},
                  {'changes':{'input_refs':[{'task_id':'a','key':'power'}]}},
                  {'changes':{},'updates':{'goal':'ambiguous representations'}}]
        for delta in variants:
            with self.subTest(delta=delta):
                saved={}
                def bad(messages):
                    w=a.working_memory;saved['state']=(deepcopy(w.graph.to_dict()),w.current,deepcopy(w.node_goals),len(w.store.entries))
                    frames=json.loads(messages[1]['content'])['scientific_source_frames']
                    proposal={'task_id':'a','output_key':'power','revision':1,'changes':{'scope':{'start':4,'end':6},'interpretation':{'range_ref':frames[-1]['source_ref']}},'reason':'TEST explicit revision'}
                    proposal.update(deepcopy(delta))
                    if proposal.get('changes',{}).get('interpretation',{}).get('source_ref')=='B_SOURCE':
                        proposal['changes']['interpretation']['source_ref']=frames[1]['source_ref']
                    if proposal.get('changes',{}).get('interpretation',{}).get('range_ref')=='CURRENT':
                        proposal['changes']['interpretation']['range_ref']=next(f['source_ref'] for f in frames if f['source_ref'].startswith('u2:'))
                    return 'revise_plan',proposal
                def rejected(messages):
                    self.assertFalse(json.loads(messages[-1]['content'])['success'])
                    w=a.working_memory
                    self.assertEqual((w.graph.to_dict(),w.current,w.node_goals,len(w.store.entries)),saved['state'])
                    return finish('partial',unresolved=['TEST invalid proposal rejected atomically'])
                c=InspectableScriptedClient([start,('psd',{'task_id':'a','output_key':'power'}),
                    ('amplitude',{'task_id':'b','output_key':'rms'}),finish(),bad,rejected])
                a=TaskPlanEEGAgent(c,synthetic_records())
                self.assertEqual(a.run(request).stop_reason,'completed',c.errors)
                self.assertEqual(a.continue_run('把记录A的分析窗口改为4到6秒，B结果保留。').stop_reason,'partial',c.errors)
                self.assertFalse(c.errors)

    def test_legal_independent_new_measurement_is_not_guessed_to_be_revision(self):
        c=InspectableScriptedClient([('plan_tasks',{'nodes':[node('first',[delivery('power')])]}),
            ('psd',{'task_id':'first','output_key':'power'}),finish(),
            ('plan_tasks',{'nodes':[node('first_rev',[delivery('power','psd',{'channels':['SYNTH-C1'],'start':4,'end':6},record='B')])]}),
            ('psd',{'task_id':'first_rev','output_key':'power'}),finish()])
        a=TaskPlanEEGAgent(c,synthetic_records())
        self.assertEqual(a.run('记录A的SYNTH-C1在0到2秒计算功率。').stop_reason,'completed')
        self.assertEqual(a.continue_run('新增记录B的SYNTH-C1在4到6秒的独立功率分析，保留A。').stop_reason,'completed',c.errors)
        self.assertEqual(a.working_memory.graph.nodes['first'].revision,1)
        self.assertEqual(len(a.working_memory.graph.nodes),2)

    def test_actual_live_wire_and_final_lease_on_explicit_test_ledger(self):
        from eeg_harness.research.working_memory_issue58 import OfflineWireClient
        from eeg_harness.research.working_memory_issue55_live import run_session
        from eeg_harness.research.working_memory_issue52 import protocol
        from eeg_harness.research.task_memory_issue39_budget import _rows
        from test_issue55_live import setup
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);raw=OfflineWireClient('T05');ledger,attestation=setup(root,raw)
            case=next(c for c in protocol()['cases'] if c['id']=='T05')
            results=run_session(raw,ledger,attestation,case,root/'run',test_only=True)
            self.assertEqual([r['stop_reason'] for r in results],['completed','completed'])
            rows=_rows(ledger)
            self.assertTrue(rows[0]['test_only'])
            self.assertEqual(sum(r['event']=='reserved' for r in rows),raw.request_count)
            self.assertEqual(sum(r['event']=='money_settled' for r in rows),raw.request_count)
            self.assertEqual(sum(r['event']=='final_lease_decision' for r in rows),raw.request_count)
            self.assertFalse(raw.inner.control_errors)
