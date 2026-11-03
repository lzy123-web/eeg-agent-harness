"""Review counterexample and default-wire tests, never autonomous evidence."""
from copy import deepcopy
from dataclasses import replace
import json
import unittest

from eeg_harness.task_plan import TaskSpec,task_spec_schema
from eeg_harness.task_plan_agent import TaskPlanEEGAgent,ARMS
from eeg_harness.scientific_contracts import validate_contract
from eeg_harness.tooling import ToolRequest
from eeg_harness.working_memory import encoded
from eeg_harness.research.task_memory import synthetic_records
from eeg_harness.research.working_memory_issue52 import run_case
from eeg_harness.research.working_memory_issue58 import incremental_steps
from test_task_plan_agent import node,delivery,reference,InspectableScriptedClient
from test_working_memory import finish
from test_issue59_history_index import exercise


def compact_action(name,args):
    """Mechanical mapping of known legal scripts, no science/order changes."""
    args=deepcopy(args)
    if name=='plan_tasks':
        rows=[]
        for n in args['nodes']:
            data={r['task_id'] for d in n['required_outputs'] for r in d.get('input_refs',[])}
            for d in n['required_outputs']:
                row={**d,'task_id':n['task_id'],'goal':n['goal']}
                row['control_dependencies']=sorted(set(n.get('control_dependencies',[]))|(set(n.get('dependencies',[]))-data))
                row['optional_operations']=n.get('optional_operations',[])
                if d['capability']=='compare_results':
                    for k in ('record','scope','input_refs','interpretation'):row.pop(k,None)
                    for side,ref in zip(('left','right'),d['input_refs']):
                        row[side]={k:v for k,v in ref.items() if k not in ('fields','level')}
                        row[side]['field']=ref['fields'][0]
                rows.append(row)
        return name,{'deliveries':rows}
    if name=='revise_plan' and 'changes' in args:
        changes=args.pop('changes');return name,{**args,**changes}
    return name,args


def compact_steps(case):
    def wrap(step):
        if isinstance(step,str):return step
        def choose(messages):
            name,args=step(messages) if callable(step) else deepcopy(step)
            return compact_action(name,args)
        return choose
    return [[wrap(s) for s in turn] for turn in incremental_steps(case)]


class ConvergenceTest(unittest.TestCase):
    def setUp(self):
        self.a=TaskPlanEEGAgent(InspectableScriptedClient([]),synthetic_records());self.w=self.a.working_memory
        self.schema=task_spec_schema(next(iter(self.w.store.contexts.values())).executor.registry)

    def test_review_partial_context_schema_and_real_parser_agree(self):
        refs=[reference('a','x',fields=[['x']]),reference('b','x',fields=[['x']])]
        for meaning in ({},{'time_reference':'record_absolute'},{'source_ref':'u1:x:0:1'},
                        {'time_reference':'record_absolute','source_ref':'u1:x:0:1'},
                        {'time_reference':'wrong'},{'source_ref':'x','source_span':'y'},
                        {'range_ref':'x','range_span':'y'},{'unknown':1}):
            with self.subTest(meaning=meaning):
                d=delivery('delta','compare_results',{},refs=refs);d['interpretation']=meaning
                n=node('c',[d]);accepted=[]
                for fn in (lambda:validate_contract(n,self.schema),lambda:TaskSpec.from_dict(n)):
                    try:fn();accepted.append(True)
                    except ValueError:accepted.append(False)
                self.assertEqual(accepted[0],accepted[1])
                self.assertEqual(accepted[0],not (meaning.get('time_reference')=='wrong' or 'source_span' in meaning or 'range_span' in meaning or 'unknown' in meaning))
        for refs_bad in ([],refs[:1],refs+refs[:1],[{**refs[0],'fields':[]},refs[1]]):
            n=node('c',[delivery('d','compare_results',{},refs=refs_bad)])
            for fn in (lambda:validate_contract(n,self.schema),lambda:TaskSpec.from_dict(n)):
                with self.assertRaises(ValueError):fn()

    def test_default_write_contract_removed_whole_task_and_wrapper_repetition(self):
        controls={c['function']['name']:c['function'] for c in self.w.control_definitions()}
        self.assertEqual(set(controls['plan_tasks']['parameters']['properties']),{'deliveries'})
        p=controls['revise_plan']['parameters']['properties']
        self.assertNotIn('updates',p);self.assertNotIn('changes',p)
        self.assertNotIn('required_outputs',encoded(controls['plan_tasks']).decode())
        # Issue61 publishes atomic additions. Measure the previous write core
        # separately; the new schema's cost is reported in the Issue61 evidence.
        tools=deepcopy(self.w.tool_definitions())
        rev=next(t['function']['parameters'] for t in tools if t['function']['name']=='revise_plan')
        rev['properties'].pop('add_deliveries',None)
        self.assertLess(len(encoded(tools)),31000)
        self.assertLess(len(encoded(self.w.tool_definitions())),36000)
        bad={'deliveries':[],'nodes':[node('a',[delivery('x')])]}
        before=self.w.graph.to_dict()
        self.assertEqual(self.w._dispatch(ToolRequest('plan_tasks',bad))['code'],'INVALID_PLAN_STRUCTURE')
        self.assertEqual(self.w.graph.to_dict(),before)

    def test_default_source_relation_type_survives_schema_derivation(self):
        row={'task_id':'a','key':'r','capability':'amplitude','record':'A',
             'scope':{'channels':['SYNTH-C1'],'start':0,'end':2}}
        schema=next(c['function']['parameters'] for c in self.w.control_definitions() if c['function']['name']=='plan_tasks')
        for value in (3,[],{}, {'source_ref':'x','target_ref':'y'}):
            proposal={'deliveries':[{**row,'interpretation':{'source_ref':'s','time_reference':'record_absolute','channel_reference':value}}]}
            ok=isinstance(value,dict) and set(value)=={'source_ref','target_ref'}
            outcomes=[]
            for fn in (lambda:validate_contract(proposal,schema),lambda:TaskSpec.from_dict(self.w._normalize_write('plan_tasks',proposal)['nodes'][0])):
                try:fn();outcomes.append(True)
                except ValueError:outcomes.append(False)
            self.assertEqual(outcomes,[ok,ok])

    def test_comparison_creation_preserves_explicit_nonempty_condition(self):
        self.w.begin_turn('记录A SYNTH-C1在0到2秒与2到4秒的RMS比较，差值至少0。')
        refs=[reference('a','x',fields=[['SYNTH-C1','rms']]),reference('b','x',fields=[['SYNTH-C1','rms']])]
        rule={'path':['right_minus_left'],'op':'gte','value':0,'source':'差值至少0'}
        nodes=[node('a',[delivery('x','amplitude',{'channels':['SYNTH-C1'],'start':0,'end':2})]),
               node('b',[delivery('x','amplitude',{'channels':['SYNTH-C1'],'start':2,'end':4})]),
               node('c',[delivery('delta','compare_results',{},refs=refs,rules=[rule])])]
        name,proposal=compact_action('plan_tasks',{'nodes':nodes})
        schema=next(c['function']['parameters'] for c in self.w.control_definitions() if c['function']['name']==name)
        validate_contract(proposal,schema)
        r=self.w._dispatch(ToolRequest(name,proposal));self.assertEqual(r['status'],'planned',r)
        self.assertEqual(self.w.graph.nodes['c'].delivery('delta').acceptance_rule,[rule])
        self.assertFalse(self.w.delivery_check(self.w.graph.nodes['c'])['scientifically_accepted'])

    def test_actual_compact_two_turn_chains_all_six_arms(self):
        for case in ('T05','T07'):
            for arm in ARMS:
                with self.subTest(case=case,arm=arm):
                    r=run_case(case,arm,actions=compact_steps(case))
                    self.assertEqual(r['metrics']['controlled_errors'],[])
                    self.assertEqual(r['metrics']['stop_reasons'],['completed','completed'])
                    self.assertEqual(r['metrics']['oracle_count'],r['metrics']['oracle_passed'])
                    self.assertEqual(r['metrics']['duplicate_numeric_invocations'],0)

    def test_contract_current_missing_and_history_are_distinct_then_stale(self):
        a,_,_,_,_=exercise();w=a.working_memory;n=w.graph.nodes['a']
        n.outputs.pop('power');n.output_status.pop('power',None)
        current=w._read('a','power','contract')
        self.assertEqual(current['availability'],'undelivered');self.assertEqual(current['fields'],[])
        history=current['available_history'];self.assertEqual(history[0]['revision'],1)
        self.assertTrue(history[0]['valid_binding'])
        old=w._read('a','power','contract',revision=1)
        self.assertEqual(old['availability'],'delivered');self.assertTrue(old['fields'])
        ctx=w.store.contexts['A'];ctx.record=replace(ctx.record,source='synthetic://changed')
        stale=w._read('a','power','contract',revision=1)
        self.assertEqual(stale['availability'],'stale');self.assertEqual(stale['fields'],[])
        self.assertFalse(stale['available_history'][0]['valid_binding'])

    def test_flat_revision_atomic_failures_and_selected_identity(self):
        a,_,_,_,_=exercise();w=a.working_memory
        for patch in ({'revision':1,'scope':{'start':1}}, {'scope':{'start':1}},
                      {'scope':{'nonsense':1},'interpretation':{'range_ref':'bad'}},
                      {'interpretation':{'source_ref':'bad','source_span':'bad'}},
                      {'left':{'task_id':'a','key':'power','field':['SYNTH-C1','alpha']}}):
            args={'task_id':'a','output_key':'power','revision':2,'reason':'negative',**patch}
            before=deepcopy(w.graph.to_dict());r=w._dispatch(ToolRequest('revise_plan',args))
            self.assertEqual(r['status'],'rejected');self.assertEqual(w.graph.to_dict(),before)

    def test_explicit_compact_independent_new_and_no_future_field_fabrication(self):
        a,_,_,_,_=exercise();w=a.working_memory
        n=node('independent',[delivery('later','amplitude',{'channels':['SYNTH-C1'],'start':4,'end':6})])
        name,args=compact_action('plan_tasks',{'nodes':[n]})
        before=deepcopy(w.graph.nodes['a'].to_dict());r=w._dispatch(ToolRequest(name,args))
        self.assertEqual(r['status'],'planned');self.assertEqual(w.graph.nodes['a'].to_dict(),before)
        d=w._read('independent','later','contract');self.assertEqual(d['availability'],'undelivered')
        self.assertFalse(d['fields']);self.assertFalse(d['actual_delivery'])

