"""Original v3 prefixes and controlled recovery; never autonomous scores."""
import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import unittest

from eeg_harness.task_plan_agent import TaskPlanEEGAgent, ARMS
from eeg_harness.scientific_contracts import contract_diagnostics, validate_contract, ContractError
from eeg_harness.tooling import ToolRequest
from eeg_harness.research.working_memory_issue52 import records_for
from eeg_harness.research.working_memory_issue61 import accept, PrefixRepairClient
from eeg_harness.working_memory import clone

EVIDENCE=Path(__file__).resolve().parents[1]/'docs/research/evidence/issue61_plan_repair.json'

def original(case):
    run=json.loads(EVIDENCE.read_text(encoding='utf8'))['final_v3_closeout']['runs'][case]
    return [t['user_request'] for t in run['turns']], [r['raw_assistant_message'] for r in run['native_responses']]

class Client(PrefixRepairClient):
    def complete(self,messages,tools,**kw):
        response=super().complete(messages,tools,**kw)
        self.views[-1]['tool_choice']=kw.get('tool_choice','auto')
        return response

def setup(case='M01',arm='C',max_rounds=12,max_tools=36):
    requests,rs=original(case)
    client=Client([],[]);a=TaskPlanEEGAgent(client,records_for(),arm=arm,session_id='issue55-session',
        max_rounds=max_rounds,max_tool_calls=max_tools,max_context_bytes=256000,timeout_seconds=900)
    client.agent=a
    return a,client,requests,rs

class ContinuationTest(unittest.TestCase):
    def test_real_continuation_source_diagnostics_change_but_still_reject(self):
        fixture=json.loads((EVIDENCE.parent/'issue61_continuation_prefixes.json').read_text(encoding='utf8'))
        a,c,requests,rs=setup();c.responses=fixture['responses'][:4]
        self.assertEqual(a.run(fixture['requests'][0]).stop_reason,'completed')
        c.responses=fixture['responses'][4:]
        c.actions=[('finish_task',{'status':'partial','answer':'TEST unresolved source and comparison remain.',
            'unresolved':['source and comparison unresolved']})]
        r=a.continue_run(fixture['requests'][1]);self.assertEqual(r.stop_reason,'partial')
        self.assertEqual(len(a.working_memory.store.entries),1)
        errors=[t['error'] for t in r.tool_results[:4]]
        self.assertEqual(errors[-2]['code'],errors[-1]['code'])
        self.assertNotEqual(errors[-2]['message'],errors[-1]['message'])
        self.assertEqual([p['errors'] for p in a.working_memory.progress_events[:4]],[1,2,2,2])
        self.assertEqual(a.working_memory.repair_credits,2)

    def test_new_diagnostic_messages_are_finite_and_argument_changes_do_not_refresh(self):
        a,c,requests,rs=setup();w=a.working_memory;w.begin_turn(requests[0]);w._action_state_before=w._progress_state()
        for i in range(6):
            w._observe_control_progress(ToolRequest('revise_plan',{'renamed':i}),
                {'status':'rejected','code':'INVALID_PLAN_SOURCE','field_path':['interpretation'],'message':f'TEST predicate {i}'})
        self.assertEqual(w.repair_credits,3);self.assertEqual(w.errors,3);self.assertEqual(w.check_stop(),'no_progress')
        w.begin_turn(requests[0]);w._action_state_before=w._progress_state()
        for i in range(3):
            w._observe_control_progress(ToolRequest('revise_plan',{'renamed':i}),
                {'status':'rejected','code':'INVALID_PLAN_SOURCE','field_path':['interpretation'],'message':'TEST same predicate'})
        self.assertEqual(w.repair_credits,0);self.assertEqual(w.check_stop(),'no_progress')

    def test_original_three_errors_aggregate_and_bounded_correction(self):
        a,c,requests,rs=setup();c.responses=rs[:4];self.assertEqual(a.run(requests[0]).stop_reason,'completed')
        w=a.working_memory;w.begin_turn(requests[1]);before=clone(w.graph.to_dict())
        sizes=[]
        for raw in rs[4:]:
            call=raw['tool_calls'][0];r=w.execute(ToolRequest(call['function']['name'],json.loads(call['function']['arguments']))).data
            sizes.append(len(r['structure_diagnostics']['issues']))
            compare=r['recovery']['public_contracts'][1]
            self.assertEqual(compare['source_fields'],['left','right'])
            self.assertNotIn('interpretation',compare['allowed_fields'])
            self.assertNotIn('input_refs',compare['allowed_fields'])
            self.assertEqual(w.graph.to_dict(),before)
        self.assertEqual(sizes,[4,3,1]);self.assertEqual(w.errors,1);self.assertIsNone(w.check_stop())
        self.assertEqual(w.repair_credits,2)
        # No free retries just because another target/value/error was chosen.
        raw=rs[-1]['tool_calls'][0];args=json.loads(raw['function']['arguments'])
        for _ in range(2):w.execute(ToolRequest('plan_tasks',args))
        self.assertEqual(w.check_stop(),'no_progress')

    def test_public_branch_diagnostics_no_inference_and_truncation(self):
        a,c,requests,rs=setup();w=a.working_memory;w.begin_turn(requests[0])
        schemas={x['function']['name']:x['function']['parameters'] for x in w.control_definitions()}
        for capability,expected in [('compare_results',['left','right']),('amplitude',['interpretation','input_refs']),('unknown',[])]:
            r=w._dispatch(ToolRequest('plan_tasks',{'deliveries':[{'task_id':'new','key':'x','capability':capability,'bogus':1}]}))
            self.assertEqual(r['recovery']['public_contracts'][0]['source_fields'],expected)
            self.assertEqual(w.graph.nodes,{})
        bad={'deliveries':[{'capability':'compare_results',**{f'bad{i}':i for i in range(30)}}]}
        d=contract_diagnostics(bad,schemas['plan_tasks']);self.assertTrue(d['truncated']);self.assertEqual(len(d['issues']),24)
        with self.assertRaises(ContractError):validate_contract(bad,schemas['plan_tasks'])
        # Diagnostics do not remove conflicting fields or silently normalize.
        self.assertIn('bad0',bad['deliveries'][0])
        for args in ({},{'tasks':[]},{'nodes':[{'task_id':'x'}]}):
            r=w._dispatch(ToolRequest('plan_tasks',args))
            self.assertEqual(r['field_path'],['deliveries'])
            self.assertTrue(r['structure_diagnostics']['issues'])
            self.assertIn('compatibility_diagnostic',r)

    def test_field_associations_versions_and_available_view_are_not_word_bags(self):
        a,c,requests,rs=setup();w=a.working_memory;w.begin_turn(requests[0])
        evidence={'result_id':'result-1','revision':1,'record':'A','fields':[
            {'path':['C1','rms'],'value':1,'semantics':{'unit':'V'}},
            {'path':['C2','rms'],'value':2,'semantics':{'unit':'V'}}]}
        swapped=deepcopy(evidence);swapped['fields'][0]['value']=2;swapped['fields'][1]['value']=1
        self.assertNotEqual(w._observation_atoms(evidence),w._observation_atoms(swapped))
        changed=deepcopy(evidence);changed['revision']=2
        self.assertNotEqual(w._observation_atoms(evidence),w._observation_atoms(changed))
        changed=deepcopy(evidence);changed['fields'][0]['semantics']['unit']='V²'
        self.assertNotEqual(w._observation_atoms(evidence),w._observation_atoms(changed))
        w.last_view=[{'role':'tool','content':json.dumps({'data':evidence,'duration_ms':9})}]
        self.assertFalse(w._observation_atoms(evidence)-w._visible_atoms())
        w.last_view=[]
        self.assertTrue(w._observation_atoms(evidence)-w._visible_atoms())

    def test_append_comparison_errors_map_to_public_operands(self):
        a,c,requests,rs=setup();c.responses=rs[:4];a.run(requests[0]);w=a.working_memory
        n=next(iter(w.graph.nodes.values()));key=n.required_outputs[0].key
        args={'task_id':n.task_id,'revision':n.revision,'reason':'TEST contract path',
            'add_deliveries':[{'key':'derived','capability':'compare_results',
                'left':{'task_id':n.task_id,'key':key,'field':['missing']},
                'right':{'task_id':n.task_id,'key':key,'field':['SYNTH-C1','mean_abs']}}]}
        before=clone(w.graph.to_dict())
        r=w._dispatch(ToolRequest('revise_plan',args))
        self.assertEqual(r['field_path'],['add_deliveries',0,'left','field'])
        self.assertEqual(w.graph.to_dict(),before)
        for change in ({'task_id':'absent'},{'revision':99}):
            bad=deepcopy(args);bad['add_deliveries'][0]['left'].update(change)
            r=w._dispatch(ToolRequest('revise_plan',bad))
            self.assertEqual(r['field_path'][:3],['add_deliveries',0,'left'])
            self.assertNotIn('input_refs',r['field_path']);self.assertEqual(w.graph.to_dict(),before)

    def test_different_rejection_classes_and_truncated_sets_cannot_reset_forever(self):
        a,c,requests,rs=setup();w=a.working_memory;w.begin_turn(requests[0])
        w._action_state_before=w._progress_state()
        counts=[]
        for i in range(9):
            w._observe_control_progress(ToolRequest('TEST-execution',{'renamed':i}),
                {'status':'rejected','code':f'TEST-rule-{i%5}'})
            counts.append(w.errors)
            if w.check_stop():break
        self.assertLessEqual(len(counts),6);self.assertEqual(counts,sorted(counts))
        self.assertLessEqual(w.repair_credits,3);self.assertEqual(w.check_stop(),'no_progress')
        w.begin_turn(requests[0]);w._action_state_before=w._progress_state()
        for size in (3,2,1):
            w._observe_control_progress(ToolRequest('plan_tasks',{'deliveries':[]}),{'status':'rejected',
                'code':'INVALID_PLAN_STRUCTURE','structure_diagnostics':{'truncated':True,
                    'issues':[{'path':['deliveries',i],'rule':'required'} for i in range(size)]}})
        self.assertEqual(w.repair_credits,0);self.assertEqual(w.check_stop(),'no_progress')

    def test_original_failure_then_legal_revision_actual_executor_six_arms(self):
        for arm in ARMS:
            with self.subTest(arm=arm):
                a,c,requests,rs=setup(arm=arm);c.responses=rs[:4]
                self.assertEqual(a.run(requests[0]).stop_reason,'completed')
                w=a.working_memory;n=next(iter(w.graph.nodes.values()));key=n.required_outputs[0].key
                old=clone(n.outputs[key]);c.responses=rs[4:]
                def revise(messages):
                    frames=json.loads(messages[1]['content'])['scientific_source_frames']
                    current=next(f['source_ref'] for f in frames if f['turn']==2 and 'SYNTH-C2' in f['span'])
                    return 'revise_plan',{'task_id':n.task_id,'output_key':key,'revision':1,'reason':'TEST explicit same measurement',
                        'scope':{'channels':['SYNTH-C2']},'interpretation':{'source_ref':current,'measurement_channels':['SYNTH-C2']}}
                c.actions=[revise,('amplitude',{'task_id':n.task_id,'output_key':key}),accept(n.task_id,key),
                    ('finish_task',{'status':'partial','answer':'TEST actual revised RMS retained; comparison deliberately not executed.',
                                    'unresolved':['TEST comparison not executed']})]
                r=a.continue_run(requests[1]);self.assertEqual(r.stop_reason,'partial',r.to_dict())
                self.assertEqual(w.graph.nodes[n.task_id].revision,2)
                self.assertNotEqual(w.graph.nodes[n.task_id].outputs[key]['result_id'],old['result_id'])
                self.assertTrue(w.store.find_entry(old['result_id']))
                self.assertEqual(r.rounds,7)

    def test_t07_original_quality_checkpoint_review_repeat_and_hard_wire(self):
        a,c,requests,rs=setup();a,c,requests,rs=setup('T07')
        with patch('eeg_harness.tools.uuid4',return_value='da8a8c63-9dcb-4077-a136-39ade73f5302'),patch('eeg_harness.events.uuid4',return_value='da8a8c63-9dcb-4077-a136-39ade73f5302'):
            c.responses=rs[:7];self.assertEqual(a.run(requests[0]).stop_reason,'completed')
            c.responses=rs[7:];r=a.continue_run(requests[1])
        self.assertEqual(r.stop_reason,'round_limit')
        last=c.views[-1];payload=json.loads(last['messages'][1]['content'])
        self.assertEqual(payload['phase'],'hard_final_delivery')
        self.assertFalse(payload['delivery_phase']['can_resume_execution'])
        self.assertEqual([t['function']['name'] for t in last['tools']],['finish_task'])
        self.assertEqual(last['tool_choice']['function']['name'],'finish_task')
        self.assertNotIn('先依据',last['messages'][0]['content'])
        self.assertTrue(any(json.loads(v['messages'][1]['content']).get('phase')=='delivery_review' for v in c.views))
        self.assertTrue(any(e['kind']=='redundant_observation' for e in a.working_memory.progress_events))
        self.assertEqual(len(a.working_memory.store.entries),4)

    def test_soft_review_preserves_legal_reads_and_can_add_omitted_work(self):
        a,c,requests,rs=setup();c.responses=rs[:3]
        # The original RMS is now produced; no injected ready DAG.
        def add(messages):
            payload=json.loads(messages[1]['content']);self.assertEqual(payload['phase'],'delivery_review')
            n=payload['plan'][0];key=n['declared_outputs'][0]['key']
            return 'revise_plan',{'task_id':n['task_id'],'revision':n['revision'],'reason':'TEST explicit derived output',
                'add_deliveries':[{'key':'self_difference','capability':'compare_results',
                    'left':{'task_id':n['task_id'],'key':key,'field':['SYNTH-C1','rms']},
                    'right':{'task_id':n['task_id'],'key':key,'field':['SYNTH-C1','mean_abs']}}]}
        def partial(messages):
            self.assertNotEqual(json.loads(messages[1]['content'])['phase'],'delivery_review')
            return 'finish_task',{'status':'partial','answer':'TEST derived comparison not executed.','unresolved':['comparison']}
        c.actions=[add,partial];r=a.run(requests[0]);self.assertEqual(r.stop_reason,'partial')
        self.assertEqual(len(next(iter(a.working_memory.graph.nodes.values())).required_outputs),2)

    def test_resource_and_tool_limits_use_same_final_message(self):
        for gate in ('round','tool','budget'):
            a,c,requests,rs=setup(max_rounds=1 if gate=='round' else 12,max_tools=1 if gate=='tool' else 36)
            if gate=='budget':c.prepare_decision=lambda *args:True
            c.actions=[('finish_task',{'status':'partial','answer':'TEST no executed evidence.','unresolved':['not run']})]
            r=a.run(requests[0]);self.assertEqual(r.stop_reason,'partial')
            view=c.views[0];payload=json.loads(view['messages'][1]['content'])
            self.assertEqual(payload['phase'],'hard_final_delivery')
            self.assertEqual(payload['available_evidence'],[])
            self.assertEqual(view['tool_choice']['function']['name'],'finish_task')
            self.assertEqual([t['function']['name'] for t in view['tools']],['finish_task'])

    def test_unadvertised_action_on_last_round_is_not_executed(self):
        a,c,requests,rs=setup(max_rounds=1)
        c.responses=[rs[0]];r=a.run(requests[0])
        self.assertEqual(r.stop_reason,'round_limit');self.assertEqual(a.working_memory.graph.nodes,{})
        self.assertEqual(r.tool_results[0]['data']['recovery']['tool'],'finish_task')

    def test_quality_checkpoint_can_complete_and_batch_review_is_not_a_stop(self):
        a,c,requests,rs=setup('T07')
        with patch('eeg_harness.tools.uuid4',return_value='da8a8c63-9dcb-4077-a136-39ade73f5302'),patch('eeg_harness.events.uuid4',return_value='da8a8c63-9dcb-4077-a136-39ade73f5302'):
            c.responses=rs[:7];a.run(requests[0]);c.responses=rs[7:14]
            c.actions=[('finish_task',{'status':'completed','answer':'CONTROLLED all registered outputs exist; this fixed test text is not an autonomous natural-request score.'})]
            result=a.continue_run(requests[1])
        self.assertEqual(result.stop_reason,'completed')
        self.assertEqual(len(a.working_memory.store.entries),4)
        self.assertEqual(json.loads(c.views[-1]['messages'][1]['content'])['phase'],'delivery_review')
        # In the first turn, review is selected only after the whole native
        # batch; it cannot block a later allowed action within that batch.
        a,c,requests,rs=setup();c.responses=[rs[0],{'role':'assistant','content':None,
            'tool_calls':[*rs[1]['tool_calls'],*rs[2]['tool_calls']]}]
        c.actions=[('finish_task',{'status':'completed','answer':'CONTROLLED actual RMS'})]
        result=a.run(requests[0]);self.assertEqual(result.stop_reason,'completed')
        self.assertTrue(all(x['success'] for x in result.tool_results))

    def test_hard_final_missing_evidence_cannot_complete_or_exceed_context(self):
        a,c,requests,rs=setup(max_rounds=1)
        c.actions=[('finish_task',{'status':'completed','answer':'TEST no evidence claim'})]
        result=a.run(requests[0]);self.assertNotEqual(result.stop_reason,'completed')
        self.assertFalse(result.tool_results[0]['success'])
        a,c,requests,rs=setup(max_rounds=1)
        build=a.working_memory.build_final_messages
        def oversized(reason):
            messages,tools=build(reason);messages[1]['content']+='x'*256001;return messages,tools
        a.working_memory.build_final_messages=oversized
        result=a.run(requests[0]);self.assertEqual(result.stop_reason,'context_capacity');self.assertEqual(c.views,[])

if __name__=='__main__':unittest.main()
