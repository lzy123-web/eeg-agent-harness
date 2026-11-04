"""Issue62 offline A/B delta comparison over preserved real prefixes.

A uses the shortest lawful original locator representation; B uses explicit
changed-field evidence. Both run the same Agent/Store/Executor and feedback.
Scripted choices are controlled experiments, never autonomous successes.
"""
import argparse,json,hashlib
from pathlib import Path
from dataclasses import asdict
from .working_memory_issue61_continuation import ReplayClient
from .working_memory_issue55_live import development_records,candidate_manifest
from .working_memory_issue55 import protocol
from .working_memory_issue52 import audit_entries,write_new
from .task_memory import PROJECT_ROOT
from ..task_plan_agent import TaskPlanEEGAgent,ARMS
from ..scientific_request_binding import source_catalog
from ..working_memory import clone,encoded

SOURCE=PROJECT_ROOT/'docs/research/evidence/issue61_plan_repair.json'
def historical(case):
    return json.loads(SOURCE.read_text(encoding='utf8'))['review_continuation']['final_v2']['cases'][case]
def run(case='T05',arm='C',variant='B'):
    original=historical(case);c=ReplayClient([],[]);c.boundary=None
    a=TaskPlanEEGAgent(c,development_records(),arm=arm,session_id='issue55-session',**protocol()['agent_settings']);c.agent=a
    raw=[r['raw_assistant_message'] for r in original['native_responses']];count=original['turns'][0]['result']['rounds']
    c.responses=clone(raw[:count]);results=[a.run(original['turns'][0]['user_request']).to_dict()];w=a.working_memory
    if variant=='original':
        for t in original['turns'][1:]:
            n=t['result']['rounds'];c.responses=clone(raw[count:count+n]);count+=n
            results.append(a.continue_run(t['user_request']).to_dict())
    else:
        if case not in {'T05','M01'}:raise ValueError('A/B controlled delta is defined only for the original existing-object changes')
        n=next(iter(w.graph.nodes.values()));key=n.required_outputs[0].key
        def change(messages):
            current=[f for f in source_catalog(w.store) if f['turn']==w.store.turn]
            ref=current[0]['source_ref']
            args={'task_id':n.task_id,'output_key':key,'revision':n.revision,'reason':'CONTROLLED original scientific delta',
                  'scope':{'start':4,'end':6} if case=='T05' else {'channels':['SYNTH-C2']}}
            if variant=='B':args['change_source']=ref
            else:args['interpretation']=({'range_ref':ref} if case=='T05' else {'source_ref':ref,'measurement_channels':['SYNTH-C2']})
            return 'revise_plan',args
        c.actions=[change,('psd' if case=='T05' else 'amplitude',{'task_id':n.task_id,'output_key':key}),
            ('finish_task',{'status':'partial','answer':'CONTROLLED revised measurement only; original comparison not performed.','unresolved':['comparison']})]
        results.append(a.continue_run(original['turns'][1]['user_request']).to_dict())
    return {'case':case,'arm':arm,'variant':variant,'kind':'original proposal replay' if variant=='original' else 'controlled A/B delta, not autonomous',
        'source':candidate_manifest(),'results':results,'views':c.views,'proposals':c.proposals,
        'write_bytes':sum(len(encoded(p)) for p in c.proposals if p['name']=='revise_plan'),
        'schema_bytes':len(encoded(w.tool_definitions())),'entries':[asdict(e) for e in w.store.entries],
        'numeric_audit':audit_entries(w.store),'sequence_boundary':c.boundary}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--case',choices=['T05','T07','M01','M02','all'],default='all')
    p.add_argument('--arm',choices=[*ARMS,'all'],default='C');p.add_argument('--variant',choices=['A','B','original'],default='original');p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();cases=(['T05','T07','M01','M02'] if args.variant=='original' else ['T05','M01']) if args.case=='all' else [args.case]
    arms=ARMS if args.arm=='all' else [args.arm];write_new(args.output,{'runs':[run(c,a,args.variant) for c in cases for a in arms]})
if __name__=='__main__':main()
