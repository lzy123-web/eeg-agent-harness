"""Offline Issue58 evidence; no service client, credential discovery or authorization."""
import argparse
import hashlib
import json
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch
from uuid import UUID
from decimal import Decimal
from types import SimpleNamespace

from ..task_plan_agent import TaskPlanEEGAgent
from ..working_memory import encoded
from .working_memory_issue52 import records_for, audit_entries, write_new
from .working_memory_issue56 import NativeReplay
from .task_memory import PROJECT_ROOT


SESSIONS = ('v3--T05-first', 'v4--T07-first')


def incremental_steps(case_id, *, legacy_revision=False):
    """Explicit migration of existing hand-written fixtures, never native output.

    Same scientific plan/tools/fields; omit redundant data dependencies and
    express T05's selected window delta. No additional read is forced.
    """
    from .working_memory_issue56 import interface_steps
    from ..working_memory import clone
    turns=interface_steps(case_id)
    def wrap(step):
        if isinstance(step,str):return step
        def choose(messages):
            view=json.loads(messages[1]['content'])
            name,args=step(messages) if callable(step) else clone(step)
            if name=='plan_tasks':
                for n in args['nodes']:
                    referenced={r['task_id'] for d in n['required_outputs'] for r in d.get('input_refs',[])}
                    if not legacy_revision:
                        n['dependencies']=[dep for dep in n.get('dependencies',[]) if dep not in referenced]
                if case_id=='T05' and args['nodes'][0]['task_id']=='alpha':
                    args['nodes'][0]['required_outputs'][0]['interpretation']={
                        'source_ref':view['scientific_source_frames'][0]['source_ref'],'time_reference':'record_absolute'}
            if case_id=='T05' and name=='revise_plan':
                current=next(n for n in view['plan'] if n['task_id']=='alpha')
                frames=[f for f in view['scientific_source_frames'] if f['source_ref'].startswith('u2:')]
                changes={'scope':{'start':4,'end':6},'interpretation':{'range_ref':frames[0]['source_ref']}}
                args={'task_id':'alpha','output_key':'alpha','revision':current['revision'],
                      'changes':changes,'reason':'用户明确改窗；保留原对象、旧值及B'}
                if legacy_revision:
                    rows=clone(current['declared_outputs'])
                    for key,value in changes.items():rows[0][key].update(value)
                    args={'task_id':'alpha','updates':{'required_outputs':rows},'reason':args['reason']}
            return name,args
        return choose
    return [[wrap(s) for s in turn] for turn in turns]


def native_replay(original_handles=False):
    index = json.loads((PROJECT_ROOT/'docs/research/evidence/issue57_real_development.json').read_text(encoding='utf8'))
    rows = []
    for name in SESSIONS:
        path = PROJECT_ROOT/'artifacts/point1_task_memory/issue57'/name
        originals = []
        for item in index['raw_local_index']:
            if Path(item['path']).parent.name == name:
                actual = PROJECT_ROOT/item['path']
                if hashlib.sha256(actual.read_bytes()).hexdigest() != item['sha256']:
                    raise ValueError('Original evidence changed: '+item['path'])
                originals.append(item)
        if not originals:
            raise ValueError('Missing original index for '+name)
        read = lambda f: [json.loads(l) for l in (path/f).read_text(encoding='utf8').splitlines()]
        requests, responses = read('requests.jsonl'), read('responses.jsonl')
        client = NativeReplay([], [])
        settings = json.loads((PROJECT_ROOT/'config/point1_working_memory_issue55.json').read_text(encoding='utf8'))['agent_settings']
        agent = TaskPlanEEGAgent(client, records_for('development'), arm='C', session_id='issue55-session', **settings)
        client.agent = agent
        turns = []
        for turn in (1, 2):
            positions = [i for i,r in enumerate(requests) if r['context']['turn']==turn]
            client.requests = [requests[i] for i in positions]
            client.responses = [responses[i] for i in positions]
            client.index = 0
            original = json.loads((path/f'turn-{turn}.json').read_text(encoding='utf8'))
            handles = [r['data']['observation']['result']['data']['artifact_id'] for r in original['result']['tool_results']
                       if r['tool_name']=='create_epochs' and r['success']]
            # Replay environment identity only. Actual samples, computations,
            # bindings and every original assistant proposal remain unchanged.
            allocator = patch('eeg_harness.events.uuid4', side_effect=[UUID(h.removeprefix('epochs-')) for h in handles]) if original_handles else nullcontext()
            with allocator:
                result = agent.run(original['user_request']) if turn==1 else agent.continue_run(original['user_request'])
            turns.append({'request':original['user_request'],'original_stop':original['result']['stop_reason'],
                          'original_score':original['score_at_deadline'],'result':result.to_dict()})
        rows.append({'session':name,'kind':'unaltered_native_proposals_not_autonomy',
            'originals':originals,'turns':turns,'views':client.views,
            'oracle':audit_entries(agent.working_memory.store)})
    return {'kind':'unaltered_native_proposals_not_autonomy','original_handle_allocator':original_handles,'external_completions':0,
            'actual_api_tokens':0,'results':rows}


class OfflineWireClient:
    """No transport. Charges TEST usage at the existing wire reservation bound."""
    is_test_client=True
    model='deepseek-flash'
    max_tokens=2200
    max_retries=0
    timeout=90.0
    thinking='disabled'
    def __init__(self,case):
        from .working_memory_issue52 import ControlledPlanClient
        self.inner=ControlledPlanClient(incremental_steps(case))
        self.turn=None
        self.request_count=0
        self.total_usage={}
        self.last_usage={}
        self.last_response_model=self.model
        self.last_finish_reason='tool_calls'
        self.finish_reasons=[]

    def complete(self,messages,tools,tool_choice='auto'):
        from .working_memory_issue50 import Issue50Client
        turn=json.loads(messages[1]['content'])['current_turn']
        if turn!=self.turn:
            self.inner.begin_controlled_turn(turn-1);self.turn=turn
        reply=self.inner.complete(messages,tools,tool_choice=tool_choice)
        body=Issue50Client.wire(SimpleNamespace(client=SimpleNamespace(client=self),model=self.model),messages,tools,tool_choice)
        # These are deliberately simulated upper-bound receipts, never API usage.
        inp=len(encoded(body));out=self.max_tokens
        self.last_usage={'prompt_tokens':inp,'completion_tokens':out,'total_tokens':inp+out}
        self.total_usage={'total_tokens':self.total_usage.get('total_tokens',0)+inp+out}
        self.request_count+=1
        return reply


def budget_preflight(output):
    """Original live driver + final leases on a separate explicit TEST ledger."""
    from .working_memory_issue55_live import (FORMAL_LEDGER, GRANT, run_session, money_totals,
        candidate_manifest, authorization_limits)
    from .working_memory_issue51 import _usage
    from .task_memory_issue39_budget import _append, _rows
    from .working_memory_issue52 import protocol
    output=Path(output)
    root=output.parent/'TEST-wire-preflight'
    root.mkdir(parents=True,exist_ok=False)
    original=FORMAL_LEDGER.read_bytes()
    rows=[json.loads(l) for l in original.decode('utf8').splitlines()]
    starts={r['request_id'] for r in rows if r.get('event')=='reserved'}
    settled={r['request_id'] for r in rows if r.get('event')=='money_settled'}
    if starts-settled:raise ValueError('Unsettled formal history; preflight cannot presume zero occupancy')
    manifest=json.loads((PROJECT_ROOT/'artifacts/point1_task_memory/issue57/v4--T07-first/manifest.json').read_text(encoding='utf8'))
    rate=max(Decimal(manifest['attestation'][k]) for k in ('input_usd_per_million','output_usd_per_million'))
    ledger=root/'TEST-budget.jsonl'
    _append(ledger,{'event':'opened','stage':'issue55','test_only':True,'grant':GRANT,
                    'reconciled':True,'rate_ceiling':str(rate)})
    attestation={k:manifest['attestation'][k] for k in ('grant','model','accepted_response_models','input_usd_per_million','output_usd_per_million')}
    attestation.update(test_only=True,rate_source='TEST simulated usage; frozen historical rate basis: '+manifest['attestation']['rate_source'])
    sessions=[]
    for case_id in ('T05','T07'):
        case=next(c for c in protocol()['cases'] if c['id']==case_id)
        raw=OfflineWireClient(case_id)
        result=run_session(raw,ledger,attestation,case,root/case_id,test_only=True)
        if len(result)!=2 or any(r['stop_reason']!='completed' for r in result) or raw.inner.control_errors:
            raise AssertionError('Controlled live-driver witness did not complete both turns; preserve TEST artifacts')
        sessions.append({'case':case_id,'stops':[r['stop_reason'] for r in result],
            'fake_calls':raw.request_count,'simulated_reservation_bound':raw.total_usage,
            'controlled_errors':raw.inner.control_errors})
    simulated=_rows(ledger)
    reservations=[r for r in simulated if r.get('event')=='reserved']
    leases=[r for r in simulated if r.get('event')=='final_lease_decision']
    witness=sum(r['reserved_tokens'] for r in reservations)
    # One witnessed full run plus its largest in-flight final lease, rounded to
    # the next 100k. Not a guarantee for arbitrary 48-decision future paths.
    proposed_tokens=((witness+max(r['lease_reserve'] for r in leases)+99999)//100000)*100000
    calls,tokens=_usage(rows)
    old_caps=authorization_limits(FORMAL_LEDGER,rows)
    proposed={'development':[calls+48,tokens+proposed_tokens],
        'confirmation':old_caps['confirmation'],'calls':calls+48+old_caps['confirmation'][0],
        'tokens':tokens+proposed_tokens+old_caps['confirmation'][1],'usd':old_caps['usd']}
    report={'kind':'offline_live_driver_wire_and_final_lease_preflight_NOT_AUTHORIZATION',
        'research_api':{'calls':0,'tokens':0,'usd':0},'sessions':sessions,
        'formal_snapshot':{'sha256':hashlib.sha256(original).hexdigest(),'calls':calls,'tokens':tokens,
            'usd_upper_bound':str(money_totals(rows,rate)),'unsettled':[],'caps':old_caps},
        'witness':{'actual_serialized_wire_bytes':sum(r['input_bytes'] for r in reservations),
            'fake_call_count':len(reservations),'reservation_units':witness,
            'max_single_reservation':max(r['reserved_tokens'] for r in reservations),
            'max_final_lease':max(r['lease_reserve'] for r in leases),
            'max_decision_plus_final_lease':max(r['normal_reserve']+r['lease_reserve'] for r in leases),
            'final_lease_events':len(leases),'simulated_cost_not_billing':str(money_totals(simulated,rate))},
        'request_not_grant':{'session_order':['T05','T07'],'arm':'C','max_calls':48,
            'max_input_output_API_tokens':proposed_tokens,'max_usd_upper_bound':str(Decimal(proposed_tokens)*rate/1000000),
            'proposed_cumulative_caps':proposed,'additional_call_ceiling':proposed['calls']-old_caps['calls'],
            'additional_token_ceiling':proposed['tokens']-old_caps['tokens'],
            'conditions':'Explicit new authorization only; existing remaining19 is not used before it. Original ledger and confirmation pool retained.'},
        'freeze':{'source':candidate_manifest(),'runtime':manifest['runtime'],
            'historical_rate_basis':{k:manifest['attestation'][k] for k in ('model','accepted_response_models',
                'input_usd_per_million','output_usd_per_million','rate_source','verified_at_utc')},
            'original_tasks_sha256':hashlib.sha256((PROJECT_ROOT/'config/point1_working_memory_issue52.json').read_bytes()).hexdigest()},
        'limits':'Wire bytes are conservative reservation units, not API token measurements. Witness is a controlled path, not a bound on unknown autonomous choices. Every real decision/final still requires original guards.'}
    if FORMAL_LEDGER.read_bytes()!=original:raise AssertionError('Formal ledger changed during zero-API preflight')
    write_new(output,report)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--native-output')
    mode.add_argument('--preflight-output')
    parser.add_argument('--original-handles',action='store_true')
    args=parser.parse_args()
    if args.preflight_output:
        report=budget_preflight(args.preflight_output)
        print(json.dumps({'witness':report['witness'],'request_not_grant':report['request_not_grant']},ensure_ascii=False));return
    report=native_replay(args.original_handles)
    write_new(Path(args.native_output),report)
    print(json.dumps([{'session':r['session'],'stops':[t['result']['stop_reason'] for t in r['turns']]} for r in report['results']]))


if __name__=='__main__':main()
