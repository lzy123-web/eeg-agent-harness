"""Unaltered failed prefixes followed by explicitly CONTROLLED offline repair.

No model service is imported or constructed. Fixture identities are research
data, never controller heuristics or a claim of autonomous repair.
"""
import argparse
import json
from dataclasses import asdict
from pathlib import Path
from ..task_plan_agent import TaskPlanEEGAgent, ARMS
from ..working_memory import clone, encoded
from .task_memory import PROJECT_ROOT
from .working_memory_issue52 import records_for, audit_entries, write_new


PREFIXES=PROJECT_ROOT/'docs/research/evidence/issue61_original_prefixes.json'


class PrefixRepairClient:
    is_test_client=True
    def __init__(self, responses, actions):
        self.responses=clone(responses);self.actions=list(actions);self.agent=None
        self.views=[];self.checkpoint=None;self.proposals=[]

    def complete(self,messages,tools,**kwargs):
        self.views.append({'messages':clone(messages),'tools':clone(tools)})
        if self.responses:return self.responses.pop(0)
        if self.checkpoint is None:
            w=self.agent.working_memory
            self.checkpoint={'graph':w.graph.to_dict(),'entries':[asdict(e) for e in w.store.entries]}
        step=self.actions.pop(0)
        name,args=step(messages) if callable(step) else step
        self.proposals.append({'name':name,'arguments':clone(args)})
        return {'role':'assistant','content':None,'tool_calls':[{'id':f'controlled-{len(self.proposals)}',
            'type':'function','function':{'name':name,'arguments':json.dumps(args,ensure_ascii=False)}}]}


def repair_actions(case,variant='A'):
    if case=='M01-v2':
        task,key='rms_A_C1_0_2','rms_0_2s'
        return [('amplitude',{'task_id':task,'output_key':key,'revision':2,'record':'A','channels':['SYNTH-C2'],'start':0,'end':2}),
            accept(task,key),('revise_plan',{'task_id':task,'revision':2,'reason':'CONTROLLED old/new comparison',
                'add_deliveries':[{'key':'delta','capability':'compare_results',
                    'left':{'task_id':task,'key':key,'revision':1,'field':['SYNTH-C1','rms']},
                    'right':{'task_id':task,'key':key,'field':['SYNTH-C2','rms']}}]}),
            ('compare_results',{'task_id':task,'output_key':'delta'}),accept(task,'delta'),
            ('finish_task',{'status':'completed','answer':'CONTROLLED actual v2 selected-key proposal now preserves and reuses the old window; new/old RMS compared.'})]
    if case=='T07':
        consumer='theta_c2_stimulus';key='theta_abs_power_c2';epoch='epochs_c2_stimulus'
        producer=consumer if variant=='A' else 'explicit_epoch_producer'
        row={'key':epoch,'capability':'create_epochs','record':'A',
            'scope':{'labels':['stimulus'],'tmin':0,'tmax':1.25},
            'interpretation':{'source_ref':'u1:410ebe45d5618fa6:24:66','time_reference':'event_relative'}}
        patch={'task_id':consumer,'output_key':key,'revision':1,'reason':'Explicitly supply the omitted producer',
            'input_refs':[{'task_id':producer,'key':epoch,'level':'result','fields':[]}]}
        writes=([('revise_plan',{**patch,'add_deliveries':[row]})] if variant=='A' else
                [('plan_tasks',{'deliveries':[dict(row,task_id=producer)]}),('revise_plan',patch)])
        return writes+[
            ('create_epochs',{'task_id':producer,'output_key':epoch,'record':'A','labels':['stimulus'],'tmin':0,'tmax':1.25}),
            accept(producer,epoch),
            ('read_dependency',{'task_id':producer,'key':epoch,'level':'result'}),
            lambda messages:('event_bandpower',{'task_id':consumer,'output_key':key,'record':'A',
                'artifact_id':latest_artifact(messages)}),
            accept(consumer,key),accept('rms_c1_0_2','rms_synthc1_0_2s'),
            ('finish_task',{'status':'completed','answer':'CONTROLLED repair: RMS and event theta results calculated.'})]
    task=key='rms_c1_0_2'
    return [('revise_plan',{'task_id':task,'output_key':key,'revision':1,'reason':'Explicitly revise the existing measurement channel',
        'scope':{'channels':['SYNTH-C2']},'interpretation':{'measurement_channels':['SYNTH-C2'],
        'source_ref':'u2:dcf2cbee808386fe:0:22','range_ref':'u1:4c731a1f9c420842:0:23'}}),
        ('amplitude',{'task_id':task,'output_key':key,'revision':2,'record':'A','channels':['SYNTH-C2'],'start':0,'end':2}),
        accept(task,key),
        ('revise_plan',{'task_id':task,'revision':2,'reason':'Append explicit old/new scalar comparison',
            'add_deliveries':[{'key':'delta','capability':'compare_results',
                'left':{'task_id':task,'key':key,'revision':1,'field':['SYNTH-C1','rms']},
                'right':{'task_id':task,'key':key,'field':['SYNTH-C2','rms']}}]}),
        ('compare_results',{'task_id':task,'output_key':'delta'}),accept(task,'delta'),
        ('finish_task',{'status':'completed','answer':'CONTROLLED repair: same task revised, old/new RMS compared.'})]


def accept(task,key):
    def choose(messages):
        view=json.loads(messages[1]['content'])
        n=next(n for n in view['task_summaries'] if n['task_id']==task)
        out=n['outputs'][key]
        return 'complete_node',{'task_id':task,'output_key':key,'revision':n['revision'],
            'result_id':out.get('result_id') or out.get('comparison_id')}
    return choose


def latest_artifact(messages):
    # Fixture reads the actual delivered artifact; never invent a runtime ID.
    for m in reversed(messages):
        if m.get('role')=='tool':
            text=m.get('content','')
            try:data=json.loads(text)
            except ValueError:continue
            def find(v):
                if isinstance(v,dict):
                    if 'artifact_id' in v:return v['artifact_id']
                    for x in v.values():
                        r=find(x)
                        if r:return r
                if isinstance(v,list):
                    for x in v:
                        r=find(x)
                        if r:return r
            result=find(data)
            if result:return result
    raise ValueError('CONTROLLED fixture cannot find actual epoch receipt')


def run_repair(case,variant='A',arm='C'):
    source=json.loads(PREFIXES.read_text(encoding='utf8'))[case]
    client=PrefixRepairClient([],[])
    agent=TaskPlanEEGAgent(client,records_for(),arm=arm,session_id='issue55-session',max_rounds=24,max_tool_calls=72)
    client.agent=agent;results=[];offset=0
    for turn,count in enumerate(source['prefix_turn_counts']):
        client.responses=clone(source['responses'][offset:offset+count]);offset+=count
        client.actions=repair_actions(case,variant) if turn==len(source['prefix_turn_counts'])-1 else []
        result=agent.run(source['requests'][turn]) if turn==0 else agent.continue_run(source['requests'][turn])
        results.append(result.to_dict())
    w=agent.working_memory
    return {'kind':'unaltered prefix + controlled continuation, NOT autonomous success','case':case,'variant':variant,'arm':arm,
        'checkpoint':client.checkpoint,'results':results,'graph':w.graph.to_dict(),
        'entries':[asdict(e) for e in w.store.entries], 'numeric_audit':audit_entries(w.store),
        'controlled_proposals':client.proposals,'views':client.views,'transitions':w.action_transitions}


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    rows=[run_repair(c,v,a) for c,v in [('T07','A'),('T07','B'),('M01','A'),('M01-v2','A')] for a in ARMS]
    write_new(args.output,{'runs':rows})

if __name__=='__main__':main()
