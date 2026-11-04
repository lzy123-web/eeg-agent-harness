"""Issue62 original prefixes and explicit controlled delta counterexamples."""
import json,unittest
from copy import deepcopy
from pathlib import Path
from eeg_harness.task_plan_agent import TaskPlanEEGAgent,ARMS
from eeg_harness.research.working_memory_issue61_continuation import ReplayClient
from eeg_harness.research.working_memory_issue55_live import development_records
from eeg_harness.research.working_memory_issue55 import protocol
from eeg_harness.scientific_contracts import validate_contract,ContractError
from eeg_harness.tooling import ToolRequest
from eeg_harness.working_memory import encoded

E=Path(__file__).resolve().parents[1]/'docs/research/evidence/issue61_plan_repair.json'
def original(case):
    return json.loads(E.read_text(encoding='utf8'))['review_continuation']['final_v2']['cases'][case]
def setup(case='T05',arm='C'):
    r=original(case);c=ReplayClient([],[]);a=TaskPlanEEGAgent(c,development_records(),arm=arm,session_id='issue55-session',**protocol()['agent_settings']);c.agent=a
    first=r['turns'][0]['result']['rounds'];c.responses=[v['raw_assistant_message'] for v in r['native_responses'][:first]]
    result=a.run(r['turns'][0]['user_request']);return a,c,r,result

def current_ref(w,span=None):
    from eeg_harness.scientific_request_binding import source_catalog
    rows=[f for f in source_catalog(w.store) if f['turn']==w.store.turn and (span is None or span in f['span'])]
    return rows[0]['source_ref']
def patch_args(w,scope,ref):
    n=next(iter(w.graph.nodes.values()));return {'task_id':n.task_id,'output_key':n.required_outputs[0].key,'revision':n.revision,'reason':'TEST explicit scientific delta','scope':scope,'change_source':ref}
class SimplificationTest(unittest.TestCase):
    def test_window_delta_all_arms_actual_execution_and_history(self):
        for arm in ARMS:
            with self.subTest(arm=arm):
                a,c,r,first=setup(arm=arm);w=a.working_memory;old=deepcopy(w.graph.nodes['alpha_power_A'].outputs);b=deepcopy(w.graph.nodes['rms_B'].outputs)
                c.actions=[lambda _:('revise_plan',patch_args(w,{'start':4,'end':6},current_ref(w,'4到6'))),
                    ('psd',{'task_id':'alpha_power_A','output_key':'alpha_abs_power_A_c1_0_2'}),
                    ('finish_task',{'status':'partial','answer':'TEST actual revised PSD; comparison deliberately omitted','unresolved':['comparison']})]
                result=a.continue_run(r['turns'][1]['user_request'])
                self.assertTrue(result.tool_results[0]['success'],result.tool_results[0]);self.assertTrue(result.tool_results[1]['success'],result.tool_results[1])
                self.assertEqual(len(w.store.entries),3);self.assertEqual(w.graph.nodes['rms_B'].outputs,b)
                self.assertEqual(w.graph.nodes['alpha_power_A'].revision_history[0]['snapshot']['outputs'],old)
                self.assertEqual(w.store.entries[-1].parameters,{'channels':['SYNTH-C1'],'start':4,'end':6})
                self.assertEqual(w.store.entries[-1].revision_of,w.store.entries[0].task_id)
    def test_channel_delta_retains_selected_actual_window(self):
        a,c,r,first=setup('M01');w=a.working_memory
        c.actions=[lambda _:('revise_plan',patch_args(w,{'channels':['SYNTH-C2']},current_ref(w,'SYNTH-C2'))),
            lambda _:('amplitude',{k:v for k,v in patch_args(w,{},'x').items() if k in ('task_id','output_key','revision')}),
            ('finish_task',{'status':'partial','answer':'TEST new RMS only','unresolved':['compare']})]
        result=a.continue_run(r['turns'][1]['user_request']);self.assertTrue(all(t['success'] for t in result.tool_results),result.tool_results)
        self.assertEqual(w.store.entries[-1].parameters,{'channels':['SYNTH-C2'],'start':0,'end':2})
    def test_rejections_are_atomic_and_never_repair_explicit_wrong_sources(self):
        for variant in ('missing','historical','wrong_current','stale_revision','unknown_channel','double_source','unknown_field','missing_target'):
            with self.subTest(variant=variant):
                a,c,r,_=setup();w=a.working_memory;w.begin_turn(r['turns'][1]['user_request']);args=patch_args(w,{'start':4,'end':6},current_ref(w,'4到6'))
                if variant=='missing':args.pop('change_source')
                if variant=='historical':args['change_source']=w.graph.nodes['alpha_power_A'].required_outputs[0].interpretation['source_ref']
                if variant=='wrong_current':args['change_source']=current_ref(w,'原0到2')
                if variant=='stale_revision':args['revision']=2
                if variant=='unknown_channel':args['scope']['channels']=['MISSING']
                if variant=='double_source':args['interpretation']={'range_ref':args['change_source']}
                if variant=='unknown_field':args['scope']['invented']=1
                if variant=='missing_target':args['task_id']='not-selected'
                before=(w.graph.to_dict(),deepcopy(w.store.entries));out=w._dispatch(ToolRequest('revise_plan',args))
                self.assertEqual(out['status'],'rejected',out);self.assertEqual(w.graph.to_dict(),before[0]);self.assertEqual(w.store.entries,before[1])
    def test_double_change_needs_complete_current_source(self):
        a,c,r,_=setup();w=a.working_memory;w.begin_turn('记录A的同一测量改为SYNTH-C2在4到6秒。')
        args=patch_args(w,{'channels':['SYNTH-C2'],'start':4,'end':6},current_ref(w));out=w._dispatch(ToolRequest('revise_plan',args));self.assertEqual(out['status'],'revised',out)
        result=w._dispatch(ToolRequest('psd',{'task_id':args['task_id'],'output_key':args['output_key']}));self.assertNotEqual(result['status'],'rejected',result)
        self.assertEqual(w.store.entries[-1].parameters,{'channels':['SYNTH-C2'],'start':4,'end':6})
    def test_task_goal_once_and_original_conflict_rejected_with_locations(self):
        a,c,r,first=setup('T07');w=a.working_memory
        raw=json.loads(r['native_responses'][0]['raw_assistant_message']['tool_calls'][0]['function']['arguments'])
        out=w._dispatch(ToolRequest('plan_tasks',raw));self.assertEqual(out['status'],'rejected');self.assertEqual(out['field_path'],['deliveries',2,'goal']);self.assertIn("['deliveries', 1, 'goal']",out['message']);self.assertFalse(w.graph.nodes)
        migrated=deepcopy(raw);goals={}
        for row in migrated['deliveries']:goals.setdefault(row['task_id'],row.pop('goal'))
        migrated['task_goals']=[{'task_id':k,'goal':v} for k,v in goals.items()]
        mixed=deepcopy(migrated);mixed['deliveries'][0]['goal']='TEST legacy leftover'
        refused=w._dispatch(ToolRequest('plan_tasks',mixed));self.assertEqual(refused['field_path'],['deliveries',0,'goal']);self.assertNotEqual(refused.get('status'),'planned');self.assertFalse(w.graph.nodes)
        schema=next(t['function']['parameters'] for t in w.control_definitions() if t['function']['name']=='plan_tasks');validate_contract(migrated,schema)
        out=w._dispatch(ToolRequest('plan_tasks',migrated));self.assertEqual(out['status'],'planned',out);self.assertEqual(len(w.store.entries),0)
        # This migration is an explicit test author choice, never automatic.
    def test_goal_identity_and_public_schema_equal_across_arms(self):
        schemas=[]
        for arm in ARMS:
            a=TaskPlanEEGAgent(None,development_records(),arm=arm);defs={t['function']['name']:t['function']['parameters'] for t in a.working_memory.control_definitions()};schemas.append((defs['plan_tasks'],defs['revise_plan']))
        self.assertTrue(all(s==schemas[0] for s in schemas));self.assertIn('task_goals',schemas[0][0]['properties']);self.assertIn('change_source',schemas[0][1]['properties'])
        for row in schemas[0][0]['properties']['deliveries']['items']['oneOf']:self.assertNotIn('goal',row['properties'])
    def test_numeric_relation_error_points_to_public_repair(self):
        a,c,r,_=setup();w=a.working_memory
        result=w._dispatch(ToolRequest('psd',{'task_id':'alpha_power_A','output_key':'alpha_abs_power_A_c1_0_2','channel_reference':{'source_span':'x','target_span':'y'}}))
        self.assertEqual(result['code'],'INTERPRETATION_CONFLICT');self.assertNotIn('required_outputs',json.dumps(result));self.assertIn('interpretation.channel_reference',result['message']);self.assertEqual(len(w.store.entries),2)
    def test_event_delta_preserves_artifact_history_and_invalidates_dependent(self):
        a=TaskPlanEEGAgent(None,development_records());w=a.working_memory
        w.begin_turn('记录A stimulus事件0到1.25秒的试次，计算SYNTH-C2的theta功率。')
        ref=current_ref(w);meaning={'source_ref':ref,'time_reference':'event_relative'}
        args={'deliveries':[{'task_id':'event_task','key':'ep','capability':'create_epochs','record':'A','scope':{'labels':['stimulus'],'tmin':0,'tmax':1.25},'interpretation':meaning},
            {'task_id':'consumer','key':'theta','capability':'event_bandpower','record':'A','scope':{'labels':['stimulus'],'tmin':0,'tmax':1.25},'interpretation':meaning,'input_refs':[{'task_id':'event_task','key':'ep'}]}]}
        self.assertEqual(w._dispatch(ToolRequest('plan_tasks',args))['status'],'planned')
        self.assertEqual(w._dispatch(ToolRequest('create_epochs',{'task_id':'event_task','output_key':'ep'}))['status'],'observed')
        old_artifact=w.store.entries[0].evidence['binding']['artifact_id']
        w.begin_turn('记录A的原事件试次窗口改为0到0.75秒。')
        delta=patch_args(w,{'tmax':.75},current_ref(w));r=w._dispatch(ToolRequest('revise_plan',delta));self.assertEqual(r['status'],'revised',r)
        self.assertEqual(w.graph.nodes['consumer'].status,'STALE');self.assertEqual(w.store.entries[0].evidence['binding']['artifact_id'],old_artifact)
        self.assertEqual(w._dispatch(ToolRequest('create_epochs',{'task_id':'event_task','output_key':'ep'}))['status'],'observed')
        self.assertNotEqual(w.store.entries[-1].evidence['binding']['artifact_id'],old_artifact)
        self.assertEqual(w.store.entries[-1].parameters['tmax'],.75)
    def test_pending_verified_user_source_not_fabricated_result_and_stale_result_rejected(self):
        a,c,r,_=setup();w=a.working_memory
        from dataclasses import replace
        ctx=w.store.contexts['A'];ctx.record=replace(ctx.record,source='synthetic://TEST-stale-binding')
        w.begin_turn(r['turns'][1]['user_request']);before=w.graph.to_dict()
        args=patch_args(w,{'start':4,'end':6},current_ref(w,'4到6'));args['input_refs']=[{'task_id':args['task_id'],'key':args['output_key'],'revision':1}]
        out=w._dispatch(ToolRequest('revise_plan',args))
        self.assertEqual(out['status'],'rejected',out);self.assertEqual(w.graph.to_dict(),before)
        # An explicitly planned but unexecuted object can retain its unique
        # validated user source, without claiming a nonexistent result.
        a=TaskPlanEEGAgent(None,development_records());w=a.working_memory;w.begin_turn('记录A SYNTH-C1在0到2秒的RMS。')
        args={'deliveries':[{'task_id':'pending','key':'r','capability':'amplitude','record':'A','scope':{'channels':['SYNTH-C1'],'start':0,'end':2},'interpretation':{'source_ref':current_ref(w),'time_reference':'record_absolute'}}]}
        self.assertEqual(w._dispatch(ToolRequest('plan_tasks',args))['status'],'planned');w.begin_turn('记录A原测量窗口改为4到6秒。')
        out=w._dispatch(ToolRequest('revise_plan',patch_args(w,{'start':4,'end':6},current_ref(w))))
        self.assertEqual(out['status'],'revised',out);self.assertEqual(len(w.store.entries),0)
    def test_changed_window_parent_cannot_borrow_another_object_or_time_base(self):
        for text in ('记录A的stimulus事件后4到6秒。','记录A SYNTH-C2，窗口4到6秒。'):
            for mode in ('legacy','delta'):
                with self.subTest(text=text,mode=mode):
                    a,c,r,_=setup();w=a.working_memory;w.begin_turn(text)
                    ref=current_ref(w,'4到6');args=patch_args(w,{'start':4,'end':6},ref)
                    if mode=='legacy':args['interpretation']={'range_ref':args.pop('change_source')}
                    before=w.graph.to_dict();count=len(w.store.entries);out=w._dispatch(ToolRequest('revise_plan',args))
                    self.assertEqual(out['status'],'rejected',out);self.assertIn('different scientific object',out['message']);self.assertEqual(w.graph.to_dict(),before);self.assertEqual(len(w.store.entries),count)
if __name__=='__main__':unittest.main()
