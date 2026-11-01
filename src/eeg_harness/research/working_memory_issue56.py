"""Offline native-message replay. Never imports or constructs a service client."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from ..task_plan_agent import TaskPlanEEGAgent
from ..working_memory import clone, encoded
from .working_memory_issue52 import protocol, records_for, audit_entries, write_new
from .task_memory import PROJECT_ROOT


def interface_steps(case_id):
    """Migration of already scripted valid fixtures, NOT original model output.

    Unique exact source text becomes a locator. Explicit owners come solely
    from the fixture's current node/output, never search another task. Ambiguous
    mapping raises rather than guessing. No scope/order/gold values change.
    """
    from .working_memory_issue55_repair import interpreted_actions
    from ..working_memory import NUMERIC_TOOLS
    turns=interpreted_actions(case_id)
    def wrap(step):
        if isinstance(step,str):return step # original controlled-client sentinel
        def action(messages):
            name,args=step(messages) if callable(step) else clone(step)
            args=clone(args);view=json.loads(messages[1]['content'])
            def locator(text):
                rows=[r for r in view['scientific_source_frames'] if r['span']==text]
                if len(rows)!=1:raise ValueError('Fixture source is not uniquely migratable')
                return rows[0]['source_ref']
            def migrate(obj):
                if isinstance(obj,list):
                    for v in obj:migrate(v)
                if not isinstance(obj,dict):return
                if 'time_reference' in obj and 'source_span' in obj:
                    obj['source_ref']=locator(obj.pop('source_span'))
                    if 'channel_reference' in obj:
                        ref=obj['channel_reference']
                        obj['channel_reference']={k.replace('_span','_ref'):locator(v) for k,v in ref.items()}
                for v in obj.values():migrate(v)
            if name in {'plan_tasks','revise_plan'}:migrate(args)
            if name in NUMERIC_TOOLS | {'compare_results'}:
                n=next(n for n in view['plan'] if n['task_id']==view['current_plan_task'])
                candidates=[d for d in n['required_outputs'] if d['capability']==name
                    and args.get('record',d['record'])==d['record']
                    and all(args.get(k,v)==v for k,v in d['scope'].items())]
                args['task_id']=n['task_id']
                if len(candidates)==1:args['output_key']=candidates[0]['key']
                elif name not in n.get('optional_operations',[]):raise ValueError('Fixture delivery is not uniquely migratable')
            if name=='finish_task' and args.get('status')=='clarification_required':
                args['clarifications']=[{'task_id':n['task_id'],'key':d['key'],'fields':['tmin','tmax']}
                    for n in view['plan'] if n['status']=='WAITING_INPUT' for d in n['required_outputs']
                    if d['capability']=='create_epochs' and not all(k in d['scope'] for k in ('tmin','tmax'))]
            return name,args
        return action
    return [[wrap(step) for step in turn] for turn in turns]


class NativeReplay:
    is_test_client = True
    def __init__(self, responses, requests, migrate=False):
        self.responses, self.requests = responses, requests
        self.index = 0
        self.agent = None
        self.views = []
        self.migrate=migrate
        self.migrations=[]

    def complete(self, messages, tools, **kwargs):
        self.views.append({'messages': clone(messages), 'tools': clone(tools)})
        request = self.requests[self.index]
        if request.get('tool_choice') == {'type':'function','function':{'name':'finish_task'}}:
            self.agent.working_memory.final_only = True
        original = self.responses[self.index]['raw_assistant_message']
        self.index += 1
        reply=clone(original)
        if self.migrate:
            from ..scientific_request_binding import source_catalog
            catalog=source_catalog(self.agent.working_memory.store)
            for call in reply.get('tool_calls',[]):
                try:args=json.loads(call['function']['arguments'])
                except (ValueError,TypeError):continue # preserve malformed originals
                before=clone(args)
                def walk(obj):
                    if isinstance(obj,list):
                        for x in obj:walk(x)
                    if not isinstance(obj,dict):return
                    if 'time_reference' in obj and 'source_span' in obj:
                        rows=[r for r in catalog if r['span']==obj['source_span']]
                        if len(rows)==1:obj['source_ref']=rows[0]['source_ref'];del obj['source_span']
                    if isinstance(obj.get('channel_reference'),dict):
                        ref=obj['channel_reference'];mapped={}
                        for key in ('source','target'):
                            rows=[r for r in catalog if r['span']==ref.get(key+'_span')]
                            if len(rows)==1:mapped[key+'_ref']=rows[0]['source_ref']
                        if len(mapped)==2:obj['channel_reference']=mapped
                    for x in list(obj.values()):walk(x)
                walk(args)
                if before!=args:
                    self.migrations.append({'call_id':call['id'],'original':before,'migrated':clone(args),
                        'rule':'unique exact full-parent text to source_ref only; no owner/scope/order repair'})
                    call['function']['arguments']=json.dumps(args,ensure_ascii=False)
        return reply


def replay_all(output,migrate=False):
    index_path=PROJECT_ROOT/'docs/research/evidence/issue55_real_development_20261101.json'
    index=json.loads(index_path.read_text(encoding='utf8'))
    rows=[]
    for session in index['sessions']:
        files={Path(r['path']).name:r for r in session['artifacts']}
        for item in files.values():
            p=PROJECT_ROOT/item['path']
            if hashlib.sha256(p.read_bytes()).hexdigest()!=item['sha256']:
                raise ValueError('Historical original changed: '+item['path'])
        def lines(name):return [json.loads(x) for x in (PROJECT_ROOT/files[name]['path']).read_text(encoding='utf8').splitlines()]
        case=next(c for c in protocol()['cases'] if c['id']==session['case'])
        client=NativeReplay(lines('responses.jsonl'),lines('requests.jsonl'),migrate)
        settings=json.loads((PROJECT_ROOT/'config/point1_working_memory_issue55.json').read_text(encoding='utf8'))['agent_settings']
        agent=TaskPlanEEGAgent(client,records_for('development'),arm='C',session_id='issue55-session',**settings)
        client.agent=agent
        result=agent.run(case['requests'][0])
        rows.append({'session':session['name'],'evidence_class':('mechanically_migrated_source_refs_controlled_replay' if migrate else 'unaltered_native_message_replay_not_autonomy'),
            'historical_candidate':session['candidate'],'originals':list(files.values()),
            'original_messages':client.responses,'original_result':session['turns'][0]['stop_reason'],
            'result':result.to_dict(),'oracle':audit_entries(agent.working_memory.store),
            'schema_bytes':len(encoded(client.views[0]['tools'])),
            'initial_view_bytes':len(encoded(client.views[0]['messages'])),
            'views':client.views,'migrations':client.migrations})
    hashes={p.relative_to(PROJECT_ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(list((PROJECT_ROOT/'src').rglob('*.py'))+list((PROJECT_ROOT/'config').rglob('*.json')))}
    report={'candidate':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'working_source':{'files':hashes,'sha256':hashlib.sha256(encoded(hashes)).hexdigest()},
        'external_completions':0,'results':rows,'original_index_sha256':hashlib.sha256(index_path.read_bytes()).hexdigest()}
    write_new(Path(output),report)
    print(json.dumps([{'session':r['session'],'stop':r['result']['stop_reason'],
        'oracle_checks':len(r['oracle']),'schema_bytes':r['schema_bytes']} for r in rows]))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True)
    p.add_argument('--migrate-source-refs',action='store_true')
    args=p.parse_args();replay_all(args.output,args.migrate_source_refs)
