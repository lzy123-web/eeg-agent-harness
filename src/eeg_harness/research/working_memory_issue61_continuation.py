"""Offline v3 prefix replay and explicitly controlled continuation.

No service/configuration client is constructed. Original proposals remain
unchanged; the artifact allocator reproduces the historical synthetic handle.
Controlled actions and sequence exhaustion are never autonomous evidence.
"""
import argparse,json
from pathlib import Path
from dataclasses import asdict
from unittest.mock import patch
from .task_memory import PROJECT_ROOT
from .working_memory_issue52 import records_for,write_new,audit_entries
from .working_memory_issue55 import protocol
from .working_memory_issue61 import PrefixRepairClient,accept
from ..task_plan_agent import TaskPlanEEGAgent,ARMS
from ..working_memory import clone

SOURCE=PROJECT_ROOT/'docs/research/evidence/issue61_plan_repair.json'

def original(case):
    r=json.loads(SOURCE.read_text(encoding='utf8'))['final_v3_closeout']['runs'][case]
    return [t['user_request'] for t in r['turns']],[r['raw_assistant_message'] for r in r['native_responses']]

class ReplayClient(PrefixRepairClient):
    def complete(self,messages,tools,**kwargs):
        if not self.responses and not self.actions:
            self.boundary={'kind':'offline original response sequence exhausted; no additional model response',
                'errors':self.agent.working_memory.errors,'stop':self.agent.working_memory.check_stop()}
            raise RuntimeError('OFFLINE_REPLAY_BOUNDARY')
        response=super().complete(messages,tools,**kwargs)
        self.views[-1]['tool_choice']=kwargs.get('tool_choice','auto')
        return response

def run(case,arm='C',controlled=False):
    requests,responses=original(case);first=4 if case=='M01' else 7
    client=ReplayClient([],[]);client.boundary=None
    agent=TaskPlanEEGAgent(client,records_for(),arm=arm,session_id='issue55-session',**protocol()['agent_settings'])
    client.agent=agent;results=[]
    with patch('eeg_harness.tools.uuid4',return_value='da8a8c63-9dcb-4077-a136-39ade73f5302'),patch('eeg_harness.events.uuid4',return_value='da8a8c63-9dcb-4077-a136-39ade73f5302'):
        client.responses=clone(responses[:first]);results.append(agent.run(requests[0]).to_dict())
        client.responses=clone(responses[first:])
        if controlled and case=='M01':
            n=next(iter(agent.working_memory.graph.nodes.values()));key=n.required_outputs[0].key
            def revise(messages):
                frames=json.loads(messages[1]['content'])['scientific_source_frames']
                source=next(f['source_ref'] for f in frames if f['turn']==2 and 'SYNTH-C2' in f['span'])
                return 'revise_plan',{'task_id':n.task_id,'output_key':key,'revision':1,'reason':'CONTROLLED selected measurement',
                    'scope':{'channels':['SYNTH-C2']},'interpretation':{'source_ref':source,'measurement_channels':['SYNTH-C2']}}
            client.actions=[revise,('amplitude',{'task_id':n.task_id,'output_key':key}),accept(n.task_id,key),
                ('finish_task',{'status':'partial','answer':'CONTROLLED actual revision; requested comparison deliberately not executed.',
                    'unresolved':['comparison not executed in this mechanism probe']})]
        elif controlled:
            # Preserve the real quality-complete checkpoint and four subsequent
            # read decisions. Replace only the final wrong-tool response with
            # an explicitly constructed honest partial delivery.
            client.responses=clone(responses[first:-1])
            client.actions=[('finish_task',{'status':'partial','answer':'CONTROLLED quality calculation retained; complete natural report not evaluated.',
                'unresolved':['controlled report is not autonomous request completion']})]
        results.append(agent.continue_run(requests[1]).to_dict())
    w=agent.working_memory
    return {'case':case,'arm':arm,'kind':'controlled recovery' if controlled else 'original proposal replay',
        'allocator_identity_replayed':case=='T07','autonomous_success_claim':False,
        'original_response_count':len(responses)-(1 if controlled and case=='T07' else 0),
        'sequence_boundary':client.boundary,'results':results,'views':client.views,
        'controlled_proposals':client.proposals,'entries':[asdict(e) for e in w.store.entries],
        'numeric_audit':audit_entries(w.store),'progress':w.progress_events}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case',choices=['M01','T07','all'],default='all')
    p.add_argument('--arm',choices=[*ARMS,'all'],default='C')
    p.add_argument('--controlled',action='store_true');p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();cases=['M01','T07'] if args.case=='all' else [args.case]
    arms=ARMS if args.arm=='all' else [args.arm]
    write_new(args.output,{'runs':[run(c,a,args.controlled) for c in cases for a in arms]})

if __name__=='__main__':main()
