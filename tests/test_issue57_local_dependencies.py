"""Actual tools for local delivery dependencies, plus transactional negatives."""
from copy import deepcopy
import json
import unittest
from eeg_harness.task_plan import PlanGraph
from eeg_harness.task_plan_agent import TaskPlanEEGAgent, ARMS
from eeg_harness.research.task_memory import synthetic_records
from test_task_plan_agent import node, delivery, reference, InspectableScriptedClient
from test_working_memory import finish


def group():
    scope={'labels':['control'],'tmin':0,'tmax':1.5}
    return node('event',[delivery('epochs','create_epochs',scope),
        delivery('power','event_bandpower',scope,refs=[reference('event','epochs')])])


class LocalDependenciesTest(unittest.TestCase):
    def test_comparison_missing_fields_reports_contract_without_mutation(self):
        initial=node('source',[delivery('power','psd')])
        invalid=node('comparison',[delivery('change','compare_results',{},refs=[
            reference('source','power','summary'),reference('source','power','result')])],deps=['source'])
        def check(messages):
            error=json.loads(messages[-1]['content'])['data']
            self.assertEqual(error['code'],'INVALID_PLAN_STRUCTURE')
            self.assertEqual(error['field_path'],['nodes',0,'required_outputs',0,'input_refs',0,'fields'])
            self.assertEqual(error['message'],'Array size outside contract') # same invalid proposal now rejected by advertised schema
            self.assertEqual(list(a.working_memory.graph.nodes),['source'])
            self.assertEqual(len(a.working_memory.store.entries),1)
            return finish('partial',unresolved=['TEST comparison was rejected'])
        c=InspectableScriptedClient([('plan_tasks',{'nodes':[initial]}),('psd',{}),
            ('plan_tasks',{'nodes':[invalid]}),check])
        a=TaskPlanEEGAgent(c,synthetic_records());r=a.run('记录A的SYNTH-C1在0到2秒计算功率。')
        self.assertEqual(r.stop_reason,'partial',c.errors)

    def test_real_producer_consumer_and_premature_wrong_artifact_rejection(self):
        for arm in ARMS:
            with self.subTest(arm=arm):
                def check_missing(messages):
                    self.assertEqual(json.loads(messages[-1]['content'])['error']['code'],'DELIVERY_INPUT_NOT_READY')
                    self.assertFalse(a.working_memory.store.entries)
                    return 'create_epochs',{'task_id':'event','output_key':'epochs'}
                def wrong_handle(messages):
                    return 'event_bandpower',{'task_id':'event','output_key':'power','artifact_id':'invented'}
                def valid(messages):
                    self.assertEqual(json.loads(messages[-1]['content'])['error']['code'],'ARTIFACT_DEPENDENCY_MISMATCH')
                    self.assertEqual(len(a.working_memory.store.entries),1)
                    return 'event_bandpower',{'task_id':'event','output_key':'power'}
                client=InspectableScriptedClient([('plan_tasks',{'nodes':[group()]}),
                    ('event_bandpower',{'task_id':'event','output_key':'power'}),check_missing,
                    wrong_handle,valid,finish()])
                a=TaskPlanEEGAgent(client,synthetic_records(),arm=arm)
                r=a.run('记录A的control事件按事件相对0到1.5秒分段并计算频带功率，不做基线和筛选。')
                self.assertEqual(r.stop_reason,'completed',client.errors)
                entries=a.working_memory.store.entries
                self.assertEqual(len(entries),2)
                self.assertEqual(entries[0].evidence['binding']['artifact_id'],entries[1].evidence['binding']['artifact_id'])
                self.assertEqual(a.working_memory.graph.nodes['event'].status,'TASK_COMPLETED')

    def test_actual_local_revision_keeps_old_artifact_and_independent_result(self):
        spec=group();independent=node('other',[delivery('rms','amplitude',record='B')])
        def revised(messages):
            updated=deepcopy(spec['required_outputs'])
            for d in updated:d['scope']['tmax']=2
            return 'revise_plan',{'task_id':'event','updates':{'required_outputs':updated},'reason':'User changed window'}
        actions=[('plan_tasks',{'nodes':[spec,independent]}),
            ('create_epochs',{'task_id':'event','output_key':'epochs'}),
            ('event_bandpower',{'task_id':'event','output_key':'power'}),
            ('amplitude',{'task_id':'other','output_key':'rms'}),finish(),revised,
            ('create_epochs',{'task_id':'event','output_key':'epochs'}),
            ('event_bandpower',{'task_id':'event','output_key':'power'}),finish()]
        c=InspectableScriptedClient(actions);a=TaskPlanEEGAgent(c,synthetic_records())
        first=a.run('记录A的control事件按事件相对0到1.5秒分段并计算频带功率；记录B的SYNTH-C1在0到2秒计算RMS。')
        self.assertEqual(first.stop_reason,'completed',c.errors)
        old=deepcopy(a.working_memory.graph.nodes['event'].outputs)
        second=a.continue_run('只把记录A的control事件相对窗口改为0到2秒，重新计算功率，记录B不重算。')
        self.assertEqual(second.stop_reason,'completed',c.errors)
        entries=a.working_memory.store.entries
        self.assertEqual(len(entries),5)
        self.assertEqual(sum(e.record=='B' for e in entries),1)
        current=a.working_memory.graph.nodes['event'].outputs
        self.assertNotEqual(old['epochs']['output_artifact'],current['epochs']['output_artifact'])
        self.assertEqual(current['epochs']['output_artifact'],current['power']['input_artifact'])
        self.assertEqual(a.working_memory.graph.resolve_ref({'task_id':'event','key':'power','revision':1})['output'],old['power'])

    def test_cycles_unknown_keys_and_future_versions_reject_atomically(self):
        g=PlanGraph();g.submit([group()]);before=g.to_dict()
        for refs in ([reference('event','power')],[reference('event','unknown')],
                     [{**reference('event','epochs'),'revision':99}]):
            outputs=deepcopy(group()['required_outputs']);outputs[0]['input_refs']=refs
            with self.subTest(refs=refs),self.assertRaises(ValueError):
                g.revise('event',{'required_outputs':outputs},'TEST invalid local reference')
            self.assertEqual(g.to_dict(),before)

    def test_local_transitive_invalidation_and_pinned_history(self):
        spec=group();spec['required_outputs'] += [delivery('independent','amplitude',{'channels':['SYNTH-C1'],'start':0,'end':2})]
        g=PlanGraph();g.submit([spec,node('child',[delivery('copy','event_bandpower',{},refs=[reference('event','power')]),
            delivery('nested','event_bandpower',{},refs=[reference('child','copy')])],deps=['event'])])
        for tid,keys in [('event',['epochs','power','independent']),('child',['copy','nested'])]:
            for key in keys:g.mark_output(tid,key,{'result_id':tid+'/'+key})
        outputs=deepcopy(spec['required_outputs']);outputs[0]['scope']['tmax']=1.75
        change=g.revise('event',{'required_outputs':outputs},'TEST changed upstream')
        self.assertEqual(change['changed_keys'],['epochs','power'])
        self.assertEqual(list(g.nodes['event'].outputs),['independent'])
        self.assertEqual(g.nodes['child'].outputs,{})
        self.assertEqual(g.resolve_ref({**reference('event','power'),'revision':1})['output']['result_id'],'event/power')
        # An explicit old revision is a historical operand, not a current cycle.
        outputs=deepcopy(g.nodes['event'].to_dict(runtime=False)['required_outputs'])
        outputs[1]['input_refs']=[{**reference('event','power'),'revision':1}]
        g.revise('event',{'required_outputs':outputs},'TEST pin old result')
        self.assertEqual(g.nodes['event'].revision,3)

