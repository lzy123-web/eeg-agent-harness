"""Constructed Fake decisions; real Agent/Store/Executor, not model autonomy."""
from copy import deepcopy
from dataclasses import asdict, replace
import json
import unittest

from eeg_harness.task_plan_agent import TaskPlanEEGAgent, ARMS
from eeg_harness.research.task_memory import synthetic_records
from test_task_plan_agent import node, delivery, reference, InspectableScriptedClient
from test_working_memory import finish


REQUEST = '记录A stimulus事件后0到1.25秒建立试次并计算功率；只有试次数至少2才继续功率分析。'
AUTO = {'C', 'C-no-selection', 'A-equivalent'}


def plan(structure='conditional', count=2):
    scope = {'labels': ['stimulus'], 'tmin': 0, 'tmax': 1.25}
    rules = [] if structure == 'unconditional' else [{'path': ['valid_epoch_count'],
        'op': 'gte', 'value': count, 'source': f'只有试次数至少{count}才继续功率分析'}]
    producer = delivery('epochs', 'create_epochs', scope, rules=rules)
    consumer = delivery('power', 'event_bandpower', scope, refs=[reference('events', 'epochs')])
    if structure == 'split':
        return [node('events', [producer]), node('consumer', [consumer], deps=['events'])]
    return [node('events', [producer, consumer])]


def action(tool, key, task='events', **extra):
    return tool, {'task_id': task, 'output_key': key, **extra}


def accept(agent, key='epochs', task='events', **overrides):
    n = agent.working_memory.graph.nodes[task]
    return 'complete_node', {'task_id': task, 'output_key': key,
        'revision': n.revision, 'result_id': n.outputs[key]['result_id'], **overrides}


def matrix_case(arm, structure, *, local=False):
    states = []
    def capture(messages):
        states.append(deepcopy(a.working_memory.graph.to_dict()))
        if local and structure == 'conditional' and arm not in AUTO:
            return accept(a)
        return 'complete_node', {'task_id': 'events'}
    c = InspectableScriptedClient([('plan_tasks', {'nodes': plan(structure)}),
        action('create_epochs', 'epochs'), ('check_deliveries', {'task_id': 'events'}),
        capture, action('event_bandpower', 'power', 'consumer' if structure == 'split' else 'events'),
        finish('partial', unresolved=['TEST trace end; final answer is not a scientific score'])])
    a = TaskPlanEEGAgent(c, synthetic_records(), arm=arm)
    r = a.run(REQUEST)
    return {'arm': arm, 'structure': structure, 'local_acceptance': local,
        'request': REQUEST, 'plan': plan(structure), 'result': asdict(r),
        'before_acceptance': states, 'snapshot': a.working_memory.snapshot(),
        'messages': c.seen, 'client_errors': c.errors,
        'scientific_executions': [e.capability for e in a.working_memory.store.entries],
        'outputs': deepcopy(a.working_memory.graph.nodes['events'].outputs),
        'checks': a.working_memory.delivery_check(a.working_memory.graph.nodes['events'])}


class DeliveryAcceptanceTest(unittest.TestCase):
    def assert_clean(self, client, result, expected='completed'):
        self.assertFalse(client.errors)
        self.assertEqual(result.stop_reason, expected)

    def test_six_arm_paths_and_paired_structures(self):
        for arm in ARMS:
            for structure in ('conditional', 'unconditional', 'split'):
                with self.subTest(arm=arm, structure=structure):
                    row = matrix_case(arm, structure, local=True)
                    self.assertFalse(row['client_errors'])
                    self.assertEqual(row['scientific_executions'], ['create_epochs', 'event_bandpower'])
                    epochs = row['outputs']['epochs']
                    if structure != 'unconditional':
                        self.assertEqual(row['checks']['outputs'][0]['predicates'][0]['value'], 3)
                    if structure == 'conditional':
                        self.assertEqual(epochs['acceptance']['owner'], 'program' if arm in AUTO else 'model')

    def test_acceptance_handoff_idempotency_and_sync_without_extra_reads(self):
        remembered = {}
        def first_accept(messages):
            wm = a.working_memory
            self.assertEqual(wm.graph.nodes['events'].output_status['epochs'], 'TOOL_SUCCEEDED')
            self.assertEqual(len(wm.store.entries), 1)
            return accept(a)
        def repeat(messages):
            native = json.loads(messages[-1]['content'])['data']
            self.assertEqual(native['status'], 'delivery_accepted')
            self.assertFalse(native['idempotent'])
            n = a.working_memory.graph.nodes['events']
            self.assertNotEqual(n.status, 'TASK_COMPLETED')
            self.assertIsNotNone(a.working_memory.store.active)
            self.assertNotIn('power', n.outputs)
            remembered.update(deepcopy(n.outputs['epochs']))
            return accept(a)
        def check_repeat(messages):
            self.assertTrue(json.loads(messages[-1]['content'])['data']['idempotent'])
            self.assertEqual(len(a.working_memory.store.entries), 1)
            return action('amplitude', 'rms', 'other')
        def check_sync(messages):
            n = a.working_memory.graph.nodes['events']
            self.assertEqual(n.outputs['epochs'], remembered)
            self.assertEqual(n.output_status['epochs'], 'DELIVERY_SATISFIED')
            self.assertEqual(n.outputs['power']['input_artifact'], remembered['output_artifact'])
            self.assertEqual(n.status, 'TASK_COMPLETED')
            return finish()
        c = InspectableScriptedClient([('plan_tasks', {'nodes': plan()+[
            node('other', [delivery('rms', 'amplitude', record='B')])]}),
            action('create_epochs', 'epochs'), first_accept, repeat, check_repeat,
            ('read_dependency', {'task_id':'events','key':'epochs','level':'result'}),
            action('event_bandpower', 'power'), check_sync])
        a = TaskPlanEEGAgent(c, synthetic_records(), arm='A')
        self.assert_clean(c, a.run(REQUEST+'记录B的SYNTH-C1在0到2秒计算RMS。'))

    def test_illegal_acceptance_is_transactional_and_whole_completion_still_waits(self):
        for invalid in (
            {'task_id':'events','output_key':'missing','revision':1,'result_id':'wrong'},
            {'task_id':'wrong','output_key':'epochs','revision':1,'result_id':'wrong'},
            {'task_id':'events','output_key':'epochs','revision':99,'result_id':'wrong'},
            {'task_id':'events','output_key':'epochs','revision':1,'result_id':'wrong'},
            {'task_id':'events','output_key':'epochs'},
        ):
            with self.subTest(invalid=invalid):
                saved={}
                def attempt(messages):
                    saved['graph']=deepcopy(a.working_memory.graph.to_dict())
                    return 'complete_node',invalid
                def check(messages):
                    self.assertEqual(json.loads(messages[-1]['content'])['error']['code'],'INVALID_DELIVERY_ACCEPTANCE')
                    self.assertEqual(a.working_memory.graph.to_dict(),saved['graph'])
                    return 'complete_node',{'task_id':'events'}
                def end(messages):
                    self.assertEqual(json.loads(messages[-1]['content'])['error']['code'],'MISSING_DELIVERY')
                    return finish('partial',unresolved=['TEST consumer pending'])
                c=InspectableScriptedClient([('plan_tasks',{'nodes':plan()}),
                    action('complete_node','epochs',revision=1,result_id='missing'),
                    action('event_bandpower','power'), action('create_epochs','epochs'),attempt,check,end])
                a=TaskPlanEEGAgent(c,synthetic_records(),arm='A')
                r=a.run(REQUEST)
                self.assert_clean(c,r,'partial')
                self.assertEqual(r.tool_results[1]['error']['code'],'INVALID_DELIVERY_ACCEPTANCE')
                self.assertEqual(r.tool_results[2]['error']['code'],'DELIVERY_INPUT_NOT_READY')
                self.assertEqual(len(a.working_memory.store.entries),1)

    def test_failed_extra_predicate_preserves_method_responsibility(self):
        for arm in ARMS:
            with self.subTest(arm=arm):
                def attempt(messages):
                    check = a.working_memory.delivery_check(a.working_memory.graph.nodes['events'])
                    self.assertFalse(check['outputs'][0]['accepted'])
                    self.assertEqual(check['outputs'][0]['predicates'][0]['value'],3)
                    return accept(a)
                def finish_case(messages):
                    n = a.working_memory.graph.nodes['events']
                    row = a.working_memory.delivery_check(n)['outputs'][0]
                    self.assertFalse(row['accepted']) # model assertion never rewrites truth
                    if arm in AUTO:
                        self.assertNotIn('acceptance',n.outputs['epochs'])
                        self.assertNotIn('power',n.outputs)
                    else:
                        self.assertEqual(n.outputs['epochs']['acceptance']['owner'],'model')
                        self.assertFalse(n.outputs['epochs']['acceptance']['scientifically_accepted'])
                        self.assertIn('power',n.outputs)
                    return finish('partial',unresolved=['TEST injected mistaken model judgment; predicate remains false'])
                c = InspectableScriptedClient([('plan_tasks',{'nodes':plan(count=4)}),
                    action('create_epochs','epochs'),attempt,action('event_bandpower','power'),finish_case])
                a = TaskPlanEEGAgent(c,synthetic_records(),arm=arm)
                self.assert_clean(c,a.run(REQUEST.replace('至少2','至少4')),'partial')
                if arm in AUTO:
                    self.assertEqual(c.seen[-1][-1]['role'],'tool')
                else:
                    self.assertEqual(len(a.working_memory.store.entries),2)

    def test_declining_failed_predicate_allows_independent_branch(self):
        for arm in ARMS:
            with self.subTest(arm=arm):
                def decline(messages):
                    check=json.loads(messages[-1]['content'])['data']
                    self.assertFalse(check['outputs'][0]['accepted'])
                    return 'wait_node',{'task_id':'events','reason':'Actual 3 < required 4; do not accept'}
                c=InspectableScriptedClient([('plan_tasks',{'nodes':plan(count=4)+[
                    node('other',[delivery('rms','amplitude',record='B')])]}),
                    action('create_epochs','epochs'),('check_deliveries',{'task_id':'events'}),
                    decline,action('amplitude','rms','other'),finish('partial',unresolved=['3 < 4; power not computed'])])
                a=TaskPlanEEGAgent(c,synthetic_records(),arm=arm)
                self.assert_clean(c,a.run(REQUEST.replace('至少2','至少4')+'记录B的SYNTH-C1在0到2秒计算RMS。'),'partial')
                self.assertEqual([e.capability for e in a.working_memory.store.entries],['create_epochs','amplitude'])
                self.assertEqual(a.working_memory.graph.nodes['other'].status,'TASK_COMPLETED')

    def test_wrong_artifact_and_unauthorized_scope_remain_common_hard_failures(self):
        for arm in ARMS:
            with self.subTest(arm=arm):
                def accept_or_continue(messages):
                    return accept(a)
                c=InspectableScriptedClient([('plan_tasks',{'nodes':plan()}),
                    action('create_epochs','epochs',tmax=2),
                    action('create_epochs','epochs'),accept_or_continue,
                    action('event_bandpower','power',artifact_id='invented'),
                    action('event_bandpower','power'),finish()])
                a=TaskPlanEEGAgent(c,synthetic_records(),arm=arm)
                r=a.run(REQUEST)
                self.assert_clean(c,r)
                self.assertEqual(r.tool_results[1]['error']['code'],'ACTION_OWNER_SCOPE_CONFLICT')
                self.assertEqual(r.tool_results[4]['error']['code'],'ARTIFACT_DEPENDENCY_MISMATCH')
                self.assertEqual(len(a.working_memory.store.entries),2)

    def test_real_scope_revision_invalidates_acceptance_and_consumer_keeps_history(self):
        saved={}
        def remember(messages):
            saved['old']=deepcopy(a.working_memory.graph.nodes['events'].outputs)
            saved['other']=deepcopy(a.working_memory.graph.nodes['other'].outputs)
            return finish()
        def revise(messages):
            outputs=deepcopy(plan()[0]['required_outputs'])
            for d in outputs:d['scope']['tmax']=1.75
            return 'revise_plan',{'task_id':'events','updates':{'required_outputs':outputs},'reason':'User changed relative window'}
        def stale(messages):
            n=a.working_memory.graph.nodes['events']
            self.assertNotIn('power',n.outputs)
            self.assertNotIn('acceptance',n.outputs['epochs'])
            self.assertNotEqual(n.outputs['epochs']['output_artifact'],saved['old']['epochs']['output_artifact'])
            return accept(a,revision=1,result_id=saved['old']['epochs']['result_id'])
        def wrong_result(messages):
            self.assertEqual(json.loads(messages[-1]['content'])['error']['code'],'INVALID_DELIVERY_ACCEPTANCE')
            return accept(a,result_id=saved['old']['epochs']['result_id'])
        def pending(messages):
            self.assertEqual(json.loads(messages[-1]['content'])['error']['code'],'DELIVERY_INPUT_NOT_READY')
            return accept(a)
        def end(messages):
            graph=a.working_memory.graph
            self.assertEqual(graph.resolve_ref({**reference('events','epochs'),'revision':1})['output'],saved['old']['epochs'])
            self.assertEqual(graph.nodes['other'].outputs,saved['other'])
            self.assertEqual(len(a.working_memory.store.entries),5)
            return finish()
        c=InspectableScriptedClient([('plan_tasks',{'nodes':plan()+[node('other',[delivery('rms','amplitude',record='B')])]}),
            action('create_epochs','epochs'),lambda m:accept(a),action('event_bandpower','power'),
            action('amplitude','rms','other'),remember,revise,action('create_epochs','epochs'),stale,wrong_result,
            action('event_bandpower','power'),pending,action('event_bandpower','power'),end])
        a=TaskPlanEEGAgent(c,synthetic_records(),arm='A')
        self.assert_clean(c,a.run(REQUEST+'记录B的SYNTH-C1在0到2秒计算RMS。'))
        self.assert_clean(c,a.continue_run('只把记录A stimulus事件相对窗口改为0到1.75秒并重算功率，原计数条件保留；B不重算。'))

    def test_explicit_acceptance_cannot_bypass_user_processing_prohibition(self):
        for arm in ARMS:
            with self.subTest(arm=arm):
                def check(messages):
                    self.assertFalse(a.working_memory.store.entries)
                    self.assertFalse(a.working_memory.graph.nodes['events'].outputs)
                    self.assertFalse(a.working_memory.store.contexts['A'].artifacts)
                    return action('complete_node','epochs',revision=1,result_id='invented')
                c=InspectableScriptedClient([('plan_tasks',{'nodes':plan()}),
                    action('create_epochs','epochs',baseline=[0,0.2]),check,
                    finish('partial',unresolved=['TEST baseline prohibited; no result to accept'])])
                a=TaskPlanEEGAgent(c,synthetic_records(),arm=arm)
                r=a.run(REQUEST+'不做基线校正或筛选。')
                self.assert_clean(c,r,'partial')
                self.assertFalse(r.tool_results[1]['success'])
                self.assertEqual(r.tool_results[2]['error']['code'],'INVALID_DELIVERY_ACCEPTANCE')

    def test_binding_invalidation_cannot_be_reaccepted(self):
        # Explicit fault injection, not a historical or natural model action.
        def invalidate(messages):
            context=a.working_memory.store.contexts['A']
            context.record=replace(context.record,source='synthetic://replacement-record')
            return accept(a)
        c=InspectableScriptedClient([('plan_tasks',{'nodes':plan()}),action('create_epochs','epochs'),
            lambda m:accept(a),invalidate,action('event_bandpower','power'),
            finish('partial',unresolved=['TEST changed physical record binding'])])
        a=TaskPlanEEGAgent(c,synthetic_records(),arm='A')
        r=a.run(REQUEST)
        self.assert_clean(c,r,'partial')
        self.assertEqual(r.tool_results[3]['error']['code'],'INVALID_DELIVERY_ACCEPTANCE')
        self.assertEqual(len(a.working_memory.store.entries),1)
        self.assertNotIn('acceptance',a.working_memory.graph.nodes['events'].outputs['epochs'])

    def test_receipt_binding_to_changed_contract_or_replaced_result(self):
        # Bounded state-level seam test, separately labelled from real-chain tests.
        def inspect(messages):
            w=a.working_memory;n=w.graph.nodes['events'];d=n.delivery('epochs')
            original=deepcopy(n.outputs['epochs'])
            d.acceptance_rule.append({'path':['valid_epoch_count'],'op':'gte','value':4,'source':'TEST changed condition'})
            self.assertFalse(w._acceptance_valid(d,original,n.output_status['epochs']))
            d.acceptance_rule.pop()
            replacement=deepcopy(original);replacement['result_id']='TEST replacement identity'
            w._mark_delivery(n,d,replacement)
            self.assertEqual(n.output_status['epochs'],'TOOL_SUCCEEDED')
            self.assertNotIn('acceptance',n.outputs['epochs'])
            w._mark_delivery(n,d,original)
            # The original proof cannot be smuggled into a new binding call.
            self.assertEqual(n.output_status['epochs'],'TOOL_SUCCEEDED')
            return finish('partial',unresolved=['TEST state-level replacement'])
        c=InspectableScriptedClient([('plan_tasks',{'nodes':plan()}),action('create_epochs','epochs'),lambda m:accept(a),inspect])
        a=TaskPlanEEGAgent(c,synthetic_records(),arm='A')
        self.assert_clean(c,a.run(REQUEST),'partial')


if __name__ == '__main__':
    # Explicit offline evidence entry; never imports a service client or ledger.
    import argparse
    from eeg_harness.research.working_memory_issue52 import write_new
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matrix-output',required=True)
    parser.add_argument('--local',action='store_true',help='Use the new explicit local-acceptance path')
    args=parser.parse_args()
    write_new(args.matrix_output,{'kind':'constructed_integration_not_model_autonomy',
        'external_completions':0,'actual_api_tokens':0,
        'rows':[matrix_case(a,s,local=args.local) for s in ('conditional','unconditional','split') for a in ARMS]})
