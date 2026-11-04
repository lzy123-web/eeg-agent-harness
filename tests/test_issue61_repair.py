"""Real failed prefix + explicitly controlled recovery; never autonomous claims."""
from copy import deepcopy
from dataclasses import asdict,replace
import json
from itertools import product
import unittest
from eeg_harness.research.working_memory_issue61 import (PREFIXES,PrefixRepairClient,run_repair,repair_actions)
from eeg_harness.research.working_memory_issue52 import records_for
from eeg_harness.task_plan_agent import TaskPlanEEGAgent,ARMS
from eeg_harness.tooling import ToolRequest
from eeg_harness.scientific_contracts import validate_contract,ContractError
from eeg_harness.working_memory import encoded


def checkpoint(case='T07',first_turn_only=False):
    source=json.loads(PREFIXES.read_text(encoding='utf8'))[case]
    c=PrefixRepairClient([],[]);a=TaskPlanEEGAgent(c,records_for(),session_id='issue55-session');c.agent=a;offset=0
    for turn,count in enumerate(source['prefix_turn_counts'][:1] if first_turn_only else source['prefix_turn_counts']):
        c.responses=deepcopy(source['responses'][offset:offset+count]);offset+=count
        (a.run if turn==0 else a.continue_run)(source['requests'][turn])
    return a


class RepairTest(unittest.TestCase):
    def test_real_prefix_both_paths_and_non_event_transfer_six_arms(self):
        for case,variant in [('T07','A'),('T07','B'),('M01','A')]:
            for arm in ARMS:
                with self.subTest(case=case,variant=variant,arm=arm):
                    r=run_repair(case,variant,arm)
                    self.assertTrue(all(v['stop_reason']=='completed' for v in r['results']))
                    # Original rejected prefix remains; none of the controlled
                    # repair operations need a weaker science check.
                    controlled=[t for t in r['transitions'] if t['call_id'].startswith('controlled-')]
                    self.assertTrue(all(t['success'] for t in controlled),controlled)
                    self.assertEqual(r['checkpoint']['entries'][0],r['entries'][0])
                    self.assertEqual(len(r['entries']),3 if case=='T07' else 2)
                    if case=='M01':
                        self.assertEqual(r['entries'][1]['revision_of'],r['entries'][0]['task_id'])
                    writes=[p for p in r['controlled_proposals'] if p['name'] in ('plan_tasks','revise_plan')]
                    if case=='T07':self.assertEqual(len(writes),1 if variant=='A' else 2)

    def test_invalid_append_atomic_scope_refs_keys_versions_and_obligations(self):
        a=checkpoint();w=a.working_memory
        name,good=repair_actions('T07')[0]
        variants=[]
        for change in ({'revision':99},{'output_key':'absent'},{'input_refs':[{'task_id':'absent','key':'x','level':'result','fields':[]}]},
                       {'input_refs':[{'task_id':good['task_id'],'key':good['output_key'],'level':'result','fields':[]}]}):
            variants.append({**deepcopy(good),**change})
        for change in ({'key':good['output_key']},{'record':'B'},{'scope':{'labels':['stimulus'],'tmin':2,'tmax':4}},
                       {'interpretation':{'time_reference':'record_absolute','source_ref':'u1:410ebe45d5618fa6:24:66'}},
                       {'interpretation':{'time_reference':'event_relative','source_ref':'missing'}},
                       {'required':False,'key':good['output_key']}):
            bad=deepcopy(good);bad['add_deliveries'][0].update(change);variants.append(bad)
        for bad in variants:
            with self.subTest(bad=bad):
                before=deepcopy(w.snapshot());entries=[asdict(e) for e in w.store.entries]
                result=w._dispatch(ToolRequest(name,bad))
                self.assertEqual(result['status'],'rejected',result)
                self.assertEqual(w.snapshot(),before)
                self.assertEqual([asdict(e) for e in w.store.entries],entries)
        accepted=w._dispatch(ToolRequest(name,good));self.assertNotEqual(accepted['status'],'rejected',accepted)
        # Plans and references are not produced artifacts.
        result=w.execute(ToolRequest('event_bandpower',{'task_id':good['task_id'],'output_key':good['output_key'],'record':'A','artifact_id':'invented'}))
        self.assertFalse(result.success);self.assertEqual(len(w.store.entries),1)

    def test_contract_feedback_discriminates_and_prerequisite_facts_shared(self):
        a=checkpoint();w=a.working_memory
        schema=next(c['function']['parameters'] for c in w.control_definitions() if c['function']['name']=='plan_tasks')
        bad={'deliveries':[{'task_id':'c','key':'x','capability':'compare_results','left':{},'right':{},'record':'A'}]}
        with self.assertRaises(ContractError) as cm:validate_contract(bad,schema)
        self.assertNotEqual(str(cm.exception),'Choose exactly one advertised representation')
        view=json.loads(w.build_messages()[1]['content'])
        fact=view['artifact_input_contracts'][0]
        self.assertEqual(fact['status'],'producer_not_selected');self.assertIn('create_epochs',fact['registered_producer_capabilities'])
        self.assertNotIn('scope',fact)
        # Explicitly independent new analysis is not silently rewritten.
        m=checkpoint('M01').working_memory
        old=json.loads(PREFIXES.read_text(encoding='utf8'))['M01']['responses'][7]['tool_calls'][0]
        result=m._dispatch(ToolRequest('plan_tasks',json.loads(old['function']['arguments'])))
        self.assertEqual(result['status'],'rejected');self.assertNotIn('inherit an actual',result['message'])
        # This retained legacy proposal has no advertised flat row. Do not
        # recommend canonical fields as though they were its public branch.
        self.assertEqual(result['recovery']['source_fields'],[])

    def test_append_ceiling_and_mixed_patch_structure(self):
        w=checkpoint().working_memory;name,args=repair_actions('T07')[0]
        schema=next(c['function']['parameters'] for c in w.control_definitions() if c['function']['name']==name)
        for bad in ({k:v for k,v in args.items() if k!='output_key'},
                    {**args,'add_deliveries':[args['add_deliveries'][0]]*13}):
            with self.assertRaises(ContractError):validate_contract(bad,schema)
        create=next(c['function']['parameters'] for c in w.control_definitions() if c['function']['name']=='plan_tasks')
        self.assertEqual(create['properties']['deliveries']['maxItems'],32*12)

    def test_feedback_actual_effect_not_semantic_guess_and_final_exclusive(self):
        w=checkpoint('M01').working_memory
        existing='rms_c1_0_2';key=existing
        new={'task_id':'independent','key':'new','capability':'amplitude','record':'A',
             'scope':{'channels':['SYNTH-C2'],'start':0,'end':2},'unsupported':True}
        r=w._dispatch(ToolRequest('plan_tasks',{'deliveries':[new]}))
        self.assertEqual(r['recovery']['proposed_effects'][0]['operation'],'new_task_delivery')
        self.assertFalse(r['recovery']['proposed_effects'][0]['implicit_previous_result'])
        r=w._dispatch(ToolRequest('revise_plan',{'task_id':existing,'revision':1,'reason':'TEST',
            'add_deliveries':[{k:v for k,v in new.items() if k!='task_id'}]}))
        self.assertEqual(r['recovery']['proposed_effects'][0]['operation'],'append_new_delivery')
        self.assertFalse(r['recovery']['proposed_effects'][0]['implicit_previous_result'])
        r=w._dispatch(ToolRequest('revise_plan',{'task_id':existing,'output_key':key,'revision':1,'reason':'TEST','scope':{'start':4}}))
        self.assertEqual(r['status'],'rejected')
        self.assertTrue(r['recovery']['proposed_effects'][0]['implicit_previous_result'])
        w.final_only=True
        r=w._dispatch(ToolRequest('plan_tasks',{'deliveries':[new]}))
        self.assertEqual(r['recovery']['tool'],'finish_task')
        self.assertNotIn('operation_contract',r['recovery'])
        malformed=w._dispatch(ToolRequest('plan_tasks',{'tasks':[]}))
        self.assertEqual(malformed['recovery']['tool'],'finish_task')
        self.assertNotIn('operation_contract',malformed['recovery'])

    def test_actual_v2_selected_patch_reuses_only_unchanged_result_window(self):
        w=checkpoint('M01-v2').working_memory
        self.assertFalse(w.action_transitions[-2]['success']) # explicit wrong range locator remains rejected
        self.assertTrue(w.action_transitions[-1]['success']) # unaltered real call16
        n=next(iter(w.graph.nodes.values()));self.assertEqual(n.revision,2)
        old=deepcopy(asdict(w.store.entries[0]))
        result=w.execute(ToolRequest('amplitude',{'task_id':n.task_id,'output_key':n.required_outputs[0].key,
            'record':'A','channels':['SYNTH-C2'],'start':0,'end':2}))
        self.assertTrue(result.success,result.error_message)
        self.assertEqual(asdict(w.store.entries[0]),old)
        new=w.store.entries[-1];self.assertEqual(new.revision_of,old['task_id'])
        for k in ('start','end'):
            source=new.tool_trace[-1]['scientific_sources'][k]
            self.assertEqual(source['kind'],'result');self.assertEqual(source['result_id'],old['task_id'])
        # A later explicit original locator must remain composable through the
        # actual result->result->user field provenance chain.
        from eeg_harness.scientific_request_binding import source_catalog
        w.begin_turn('记录A的SYNTH-C1，窗口保持原样。');frames=source_catalog(w.store)
        proposal={'task_id':n.task_id,'output_key':n.required_outputs[0].key,'revision':2,'reason':'TEST third turn',
            'scope':{'channels':['SYNTH-C1']},'interpretation':{'measurement_channels':['SYNTH-C1'],
                'source_ref':next(f['source_ref'] for f in frames if f['turn']==w.store.turn and 'SYNTH-C1' in f['span']),
                'range_ref':frames[0]['source_ref']}}
        bad=deepcopy(proposal);bad['interpretation']['range_ref']=next(f['source_ref'] for f in frames if f['turn']==2 and '时间范围' in f['span'])
        before=deepcopy(w.graph.to_dict());r=w._dispatch(ToolRequest('revise_plan',bad))
        self.assertEqual(r['status'],'rejected');self.assertEqual(w.graph.to_dict(),before)
        r=w._dispatch(ToolRequest('revise_plan',proposal));self.assertEqual(r['status'],'revised',r)
        self.assertEqual(asdict(w.store.entries[0]),old)

    def test_retained_window_conflicts_stale_missing_and_wrong_explicit_locators(self):
        from eeg_harness.scientific_request_binding import source_catalog
        # Independent constructions after the real first-turn result. No
        # phrase/name rules in production; all conflicts use actual frames.
        scenarios=[
            ('记录A的SYNTH-C2改用2到4秒。','window'),
            ('记录A的SYNTH-C2；窗口2到4秒。','adjacent'),
            ('记录A的SYNTH-C2；结束改为4秒。','endpoint'),
            ('记录B的SYNTH-C2。','record'),
            ('记录A的SYNTH-C2。','stale'),
            ('记录A的SYNTH-C2。','changed_pair'),
            ('记录A的SYNTH-C2。','new_key_no_witness'),
            ('记录A的SYNTH-C2。','wrong_locator')]
        for origin,(request,defect) in product(('M01','M01-v2'),scenarios):
            with self.subTest(origin=origin,defect=defect):
                a=checkpoint(origin,first_turn_only=True);w=a.working_memory;w.begin_turn(request)
                n=next(iter(w.graph.nodes.values()));key=n.required_outputs[0].key
                locator=source_catalog(w.store)[-1]['source_ref']
                # Select the current object-bearing complete parent, not its
                # adjacent range. The verifier must still see that range.
                locator=next(f['source_ref'] for f in source_catalog(w.store) if f['turn']==w.store.turn and 'SYNTH-C2' in f['span'])
                interp={'source_ref':locator,'measurement_channels':['SYNTH-C2']}
                args={'task_id':n.task_id,'output_key':key,'revision':1,'reason':'TEST',
                    'scope':{'channels':['SYNTH-C2']},'interpretation':interp}
                if defect=='changed_pair':args['scope']['end']=4
                if defect=='wrong_locator':interp['range_ref']='missing'
                if defect=='stale':
                    ctx=w.store.contexts['A'];ctx.record=replace(ctx.record,source='synthetic://stale-binding')
                if defect=='new_key_no_witness':
                    args={'task_id':n.task_id,'revision':1,'reason':'TEST','add_deliveries':[{
                        'key':'new','capability':'amplitude','record':'A','scope':{'channels':['SYNTH-C2'],'start':0,'end':2},
                        'interpretation':{**interp,'time_reference':'record_absolute'}}]}
                before=deepcopy(w.graph.to_dict());result=w._dispatch(ToolRequest('revise_plan',args))
                self.assertEqual(result['status'],'rejected',result);self.assertEqual(w.graph.to_dict(),before)

    def test_explicit_cross_task_result_reference_retains_window_without_identity_rewrite(self):
        from eeg_harness.scientific_request_binding import source_catalog
        w=checkpoint('M01',first_turn_only=True).working_memory
        old=next(iter(w.graph.nodes.values()));old_result=deepcopy(asdict(w.store.entries[0]))
        w.begin_turn('记录A的SYNTH-C1追加频带功率，沿用已有测量时间范围。')
        loc=next(f['source_ref'] for f in source_catalog(w.store) if f['turn']==w.store.turn and 'SYNTH-C1' in f['span'])
        row={'task_id':'independent_spectrum','key':'power','capability':'psd','record':'A',
            'scope':{'channels':['SYNTH-C1'],'start':0,'end':2},
            'interpretation':{'source_ref':loc,'time_reference':'record_absolute','measurement_channels':['SYNTH-C1']}}
        missing=w._dispatch(ToolRequest('plan_tasks',{'deliveries':[row]}))
        self.assertEqual(missing['status'],'rejected')
        row['input_refs']=[{'task_id':old.task_id,'key':old.required_outputs[0].key,'level':'result','fields':[]}]
        r=w._dispatch(ToolRequest('plan_tasks',{'deliveries':[row]}));self.assertEqual(r['status'],'planned',r)
        r=w.execute(ToolRequest('psd',{'task_id':'independent_spectrum','output_key':'power','record':'A','channels':['SYNTH-C1'],'start':0,'end':2}))
        self.assertTrue(r.success,r.error_message);self.assertEqual(w.graph.nodes[old.task_id].revision,1)
        self.assertEqual(asdict(w.store.entries[0]),old_result)

if __name__=='__main__':unittest.main()
