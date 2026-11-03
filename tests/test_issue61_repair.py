"""Real failed prefix + explicitly controlled recovery; never autonomous claims."""
from copy import deepcopy
from dataclasses import asdict
import json
import unittest
from eeg_harness.research.working_memory_issue61 import (PREFIXES,PrefixRepairClient,run_repair,repair_actions)
from eeg_harness.research.working_memory_issue52 import records_for
from eeg_harness.task_plan_agent import TaskPlanEEGAgent,ARMS
from eeg_harness.tooling import ToolRequest
from eeg_harness.scientific_contracts import validate_contract,ContractError
from eeg_harness.working_memory import encoded


def checkpoint(case='T07'):
    source=json.loads(PREFIXES.read_text(encoding='utf8'))[case]
    c=PrefixRepairClient([],[]);a=TaskPlanEEGAgent(c,records_for(),session_id='issue55-session');c.agent=a;offset=0
    for turn,count in enumerate(source['prefix_turn_counts']):
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
        self.assertEqual(result['recovery']['source_fields'],['interpretation','input_refs'])

    def test_append_ceiling_and_mixed_patch_structure(self):
        w=checkpoint().working_memory;name,args=repair_actions('T07')[0]
        schema=next(c['function']['parameters'] for c in w.control_definitions() if c['function']['name']==name)
        for bad in ({k:v for k,v in args.items() if k!='output_key'},
                    {**args,'add_deliveries':[args['add_deliveries'][0]]*13}):
            with self.assertRaises(ContractError):validate_contract(bad,schema)
        create=next(c['function']['parameters'] for c in w.control_definitions() if c['function']['name']=='plan_tasks')
        self.assertEqual(create['properties']['deliveries']['maxItems'],32*12)

if __name__=='__main__':unittest.main()
