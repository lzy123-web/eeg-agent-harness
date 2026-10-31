"""Issue55: evaluator-only obligations, original Executor oracle and zero-API preflight.

No client is constructed here. Confirmation requests, not evaluator plans, are
passed to run/continue. CLI refuses paid runs until a separately authorized
stage ledger and frozen manifest have been installed.
"""
import argparse
from collections import Counter
from dataclasses import replace, asdict
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from ..task_plan_agent import TaskPlanEEGAgent, SYSTEM
from ..tooling import ToolRequest
from ..working_memory import WorkingMemoryStore
from .task_memory import PROJECT_ROOT, synthetic_records
from .task_memory_v2 import independent_oracle
from .working_memory_issue52 import encoded, write_new, run_case, ControlledPlanClient, controlled_steps, records_for as old_records, protocol as old_protocol

SPEC = PROJECT_ROOT / 'config/point1_working_memory_issue55.json'


class Issue55BudgetClient:
    """Factory for the existing wire/final-lease implementation, new ledger only.

    Authority is an explicit caller-supplied receipt of a separate user grant;
    protocol's proposed budget is never treated as authorization.
    """
    def __new__(cls, client, ledger, *, authorization=None, phase='development',
                arm='C', request_journal=None):
        from .working_memory_issue50 import Issue50Client
        from .working_memory_issue51 import _usage
        from .task_memory_issue39_budget import _append, _rows, _ledger_lock, StageBudgetExhausted
        proposal = protocol()['proposed_budget']
        expected = {'stage':'issue55','completions':proposal['completions'],
                    'api_tokens':proposal['api_tokens']}
        if not authorization or any(authorization.get(k)!=v for k,v in expected.items()) or not authorization.get('user_grant'):
            raise StageBudgetExhausted('No separate Issue55 user authorization; zero allowance')
        if phase not in {'development','confirmation'} or arm not in {'A','B','C','A-equivalent'}:
            raise ValueError('Unknown phase or arm')
        class Budget(Issue50Client):
            def _fits(self, rows, calls, tokens):
                if any(r.get('event')=='stage_closed' for r in rows):return False
                used = _usage(rows)
                phase_used = _usage(rows, lambda c:c.get('phase')==phase)
                return (used[0]+calls<=proposal['completions'] and used[1]+tokens<=proposal['api_tokens']
                    and phase_used[0]+calls<=proposal[phase+'_completions']
                    and phase_used[1]+tokens<=proposal[phase+'_tokens'])
        obj=object.__new__(Budget)
        obj.client,obj.ledger=client,Path(ledger)
        obj.context={'phase':phase,'arm':arm}
        obj.request_journal=Path(request_journal) if request_journal else None
        obj.final_only,obj.delivery_checkpoint,obj._lease=False,None,None
        obj.ledger.parent.mkdir(parents=True,exist_ok=True)
        header={'event':'opened',**expected,'authorization':authorization,
                'protocol_sha256':hashlib.sha256(SPEC.read_bytes()).hexdigest()}
        with _ledger_lock(obj.ledger):
            rows=_rows(obj.ledger)
            if rows and rows[0]!=header:
                raise StageBudgetExhausted('Different stage/grant/protocol; never reuse or resize a ledger')
            if any(r.get('event')=='stage_closed' for r in rows):
                raise StageBudgetExhausted('Closed stage cannot be reopened')
            if not rows:_append(obj.ledger,header)
        return obj


def protocol():
    return json.loads(SPEC.read_text(encoding='utf8'))


def records_for():
    settings = protocol()['synthetic_data']
    return {k: replace(r, data=r.data * settings['scales'][k] +
        settings['added_sine_volts'] * np.sin(2*np.pi*settings['added_sine_hz']*
            np.arange(r.data.shape[-1])/r.sfreq)[None, :],
        source=f'synthetic://issue55-{k}') for k, r in synthetic_records().items()}


def data_manifest(records):
    return {k: {'samples_sha256': hashlib.sha256(r.data.tobytes()).hexdigest(),
        'shape': list(r.data.shape), 'sfreq': r.sfreq, 'channels': list(r.channel_names),
        'source': r.source, 'events': [asdict(e) for e in r.events.events],
        'reference': r.reference, 'montage': r.montage} for k, r in records.items()}


def field_at(value, path):
    for part in path:
        value = value[part]
    return value


def quality_oracle(record, scope):
    # Reconstruct original slices; do not call the production quality routine.
    accepted, rejected, bad, reasons, labels = [], 0, [], Counter(), []
    for event in record.events.events:
        if event.label not in scope['labels']:
            continue
        start, end = event.onset_seconds+scope['tmin'], event.onset_seconds+scope['tmax']
        if start < 0 or end > record.duration_seconds:
            rejected += 1
            continue
        accepted.append(record.slice(start, end))
        labels.append(event.label)
    for i, trial in enumerate(accepted):
        flagged = False
        for channel in trial:
            for reason, flag in [('FLATLINE', np.mean(np.abs(np.diff(channel)) <= 1e-8) >= .95),
                                 ('HIGH_AMPLITUDE', np.mean(np.abs(channel) >= 200e-6) >= .01)]:
                if flag:
                    reasons[reason] += 1
                    flagged = True
        if flagged:
            bad.append(i)
    n = len(accepted)
    return {'epoch_counts': {'requested_or_boundary_checked': n+rejected, 'created': n,
        'boundary_rejected': rejected, 'quality_flagged': len(bad), 'quality_usable': n-len(bad)},
        'condition_counts_before_quality': dict(Counter(labels)),
        'condition_counts_quality_usable': dict(Counter(v for i,v in enumerate(labels) if i not in bad)),
        'quality_flag_reasons': dict(reasons), 'flagged_epoch_indices': bad,
        'usable_fraction_of_created': (n-len(bad))/n if n else 0}


def numeric_check(record, obligation, result):
    rows = []
    for path in obligation['fields']:
        expected = independent_oracle(record, {'capability': obligation['capability'],
            'parameters': obligation['scope']}, path)
        actual = field_at(result, path)
        rows.append({'field': path, 'actual': actual, 'expected': expected,
            'passed': bool(np.isclose(float(actual), expected, rtol=.005, atol=1e-13))})
    if obligation['capability'] == 'epoch_quality':
        for key, expected in quality_oracle(record, obligation['scope']).items():
            rows.append({'field': [key], 'actual': result.get(key), 'expected': expected,
                'passed': result.get(key) == expected})
    return rows


def scientific_preflight():
    records = records_for()
    rows = []
    for case in protocol()['cases']:
        store = WorkingMemoryStore('offline55', records)
        artifacts = {}
        for item in case['evaluation_only']['obligations']:
            context = store.contexts[item['record']]
            args = item['scope'].copy()
            if item['capability'] in {'epoch_summary','event_bandpower','epoch_quality'}:
                key = encoded([item['record'], args])
                if key not in artifacts:
                    created = context.execute(ToolRequest('create_epochs', args))
                    if not created.success:
                        raise AssertionError(created.to_dict())
                    artifacts[key] = created.data['artifact_id']
                args = {'artifact_id': artifacts[key]}
            result = context.execute(ToolRequest(item['capability'], args))
            if not result.success:
                raise AssertionError(result.to_dict())
            checks = numeric_check(records[item['record']], item, result.data)
            rows.append({'case': case['id'], 'key': item['key'], 'result': result.to_dict(),
                         'oracle': checks, 'passed': bool(checks) and all(c['passed'] for c in checks)})
    return rows


def score_obligations(case, store, turn):
    """Independent request inventory; cannot be satisfied by a smaller model DAG.

    Tool existence/numbers do NOT certify delivered prose. Manual review of the
    accepted answer and exact input/response chain is a separate mandatory gate.
    """
    rows = []
    for item in case['evaluation_only']['obligations']:
        if item['turn'] > turn:
            continue
        matches = [e for e in store.entries if e.record == item['record'] and
            e.capability == item['capability'] and e.parameters == item['scope'] and
            store._binding_valid(e) and e.evidence['source'] == store.records[e.record].source and
            e.evidence['analysis_configuration']['time_reference'] ==
                ('event_relative' if 'labels' in item['scope'] else 'record_absolute')]
        checks = numeric_check(store.records[item['record']], item, matches[-1].result) if matches else []
        rows.append({'key':item['key'], 'result_id':matches[-1].task_id if matches else None,
            'passed':bool(matches) and bool(checks) and all(c['passed'] for c in checks), 'numeric':checks})
    return {'requirements':rows, 'all_required_results_correct': bool(rows) and all(r['passed'] for r in rows),
        'whole_request_correct':None, 'answer_review':'required: actual delivered answer, units, omissions, version, constraints and extra claims',
        'autonomous_memory_use':None}


def drive_requests(agent, requests):
    """Only user text enters Agent; no evaluator IDs, expected stops or actions.

    Explicit safe partial replies may be continued by the next original turn.
    Technical/resource failures stop the session without consuming future turns.
    Stage-level scientific audit must occur before starting another case.
    """
    results = []
    for i, request in enumerate(requests):
        result = agent.run(request) if i == 0 else agent.continue_run(request)
        results.append(result.to_dict())
        if result.stop_reason not in {'completed','partial','clarification_required'}:
            break
    return results


class ProbeClient:
    model = 'offline-no-network'
    request_count = 0
    total_usage = {}
    def __init__(self):
        self.messages = self.tools = None
    def complete(self, messages, tools, **kwargs):
        self.messages, self.tools = messages, tools
        raise RuntimeError('Offline initial-input capture; no external request')


def reservation(messages, tools, choice='auto'):
    body = {'model':'deepseek-chat', 'messages':messages,'tools':tools,'tool_choice':choice,
            'max_tokens':2200,'stream':False,'thinking':{'type':'disabled'}}
    return len(encoded(body))+2200


def final_capacity_witness(case_id, arm):
    class Client(ControlledPlanClient):
        def complete(self, messages, tools, **kwargs):
            final, final_tools = self.controller.build_final_messages()
            self.reserves.append({'normal': reservation(messages, tools),
                'final': reservation(final, final_tools,
                    {'type':'function','function':{'name':'finish_task'}})})
            return super().complete(messages, tools, **kwargs)
    client = Client(controlled_steps(case_id))
    client.reserves = []
    agent = TaskPlanEEGAgent(client, old_records(), arm=arm, session_id='capacity55',
                            **protocol()['agent_settings'])
    client.controller = agent.working_memory
    requests = next(c['requests'] for c in old_protocol()['cases'] if c['id']==case_id)
    for i, request in enumerate(requests):
        client.begin_controlled_turn(i)
        result = agent.run(request) if i == 0 else agent.continue_run(request)
        if result.stop_reason not in {'completed','clarification_required'}:
            break
    return {'case':case_id,'arm':arm,'decision_and_final_snapshots':client.reserves,
        'sum_normal':sum(r['normal'] for r in client.reserves),
        'maximum_normal_plus_final':max(r['normal']+r['final'] for r in client.reserves)}


def preflight():
    spec = protocol()
    initial = []
    for case in spec['cases']:
        for arm in ('A','B','C','A-equivalent'):
            client = ProbeClient()
            agent = TaskPlanEEGAgent(client, records_for(), arm=arm, session_id='capture55', **spec['agent_settings'])
            agent.run(case['requests'][0])
            final, tools = agent.working_memory.build_final_messages()
            initial.append({'case':case['id'],'arm':arm,
                'normal_reserve':reservation(client.messages,client.tools),
                'final_reserve':reservation(final,tools,{'type':'function','function':{'name':'finish_task'}}),
                'messages_sha256':hashlib.sha256(encoded(client.messages)).hexdigest(),
                'tools_sha256':hashlib.sha256(encoded(client.tools)).hexdigest()})
    # Development trajectories are already known; never label these confirmation.
    witnesses = []
    for case_id in ('T04','T07','T06','T08'):
        for arm in ('A','B','C'):
            row = run_case(case_id, arm)
            witnesses.append({'case':case_id,'arm':arm,'metrics':row['metrics'],
                'oracle':row['oracle'], 'final_input_reserves':[
                    d['conservative_token_reservation'] for d in row['decisions']
                    if d['controlled_action']['name']=='finish_task']})
    science = scientific_preflight()
    return {'stage':'issue55','authorization':'NONE','external_completions':0,'actual_api_tokens':0,
        'protocol_sha256':hashlib.sha256(SPEC.read_bytes()).hexdigest(),
        'system_sha256':hashlib.sha256(SYSTEM.encode()).hexdigest(), 'data':data_manifest(records_for()),
        'initial_inputs':initial,'known_development_witnesses':witnesses,'science':science,
        'full_final_capacity':[final_capacity_witness(c,a) for c in ('T06','T08') for a in ('A','B','C')],
        'interpretation':'Wire bytes + maximum output are reservations, not API tokens. Initial and known-path final inputs are witnesses, not bounds on unseen autonomous trajectories.'}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preflight',action='store_true')
    mode.add_argument('--real',action='store_true')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    if args.real:
        parser.error('Issue55 has conditional authorization, but this offline CLI cannot launch paid runs: a verified endpoint, cost ledger and end-to-end live driver are required')
    result=preflight()
    write_new(args.output,result)
    print(json.dumps({'external_completions':0,'science_checks':sum(len(r['oracle']) for r in result['science']),
        'science_passed':all(r['passed'] for r in result['science']),
        'maximum_initial_reserve':max(r['normal_reserve'] for r in result['initial_inputs'])}))


if __name__=='__main__':
    main()
