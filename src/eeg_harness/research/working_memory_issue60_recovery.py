"""Narrow append-only HTTP503 disposition policy for the existing Issue55 ledger.

No client, allowance, scientific state or executor lives here. Uncertain sends
remain charged and blocked. Dispositions only become effective with their
matching independently reserved retry; an orphan disposition unlocks nothing.
"""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from .task_memory_issue39_budget import StageBudgetExhausted

SCOPE = 'issue60-http503-recovery-20261103'
PERMISSION = 'https://github.com/lzy123-web/eeg-agent-harness/issues/55#issuecomment-6603781591'
RECEIPT = 'https://github.com/lzy123-web/eeg-agent-harness/issues/55#issuecomment-6605978071'
KNOWN_REQUEST = '4b118ce8-c7b8-4396-bad4-a514b673cfb4'
BASELINE_SOURCE = '6b98d4b75239fdec4a1c676801df12127b622b56da43778f5424c1a38bd87841'
CASES = ['T05', 'T07', 'M01', 'M02']
# Only transport/accounting orchestration may differ from the reviewed science.
RECOVERY_FILES = {
    'src/eeg_harness/research/working_memory_issue55_live.py',
    'src/eeg_harness/research/working_memory_issue50.py',
    'src/eeg_harness/research/integrated_method/v2_validation.py',
    'src/eeg_harness/research/working_memory_issue60_recovery.py',
}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def policy(rows):
    found = [r for r in rows if r.get('event') == 'http503_recovery_permission']
    if not found:
        return None
    if len(found) != 1:
        raise StageBudgetExhausted('Conflicting recovery permissions')
    p = found[0]
    if (p.get('scope_id') != SCOPE or p.get('permission') != PERMISSION or
            p.get('receipt') != RECEIPT or p.get('max_retries_per_request') != 2 or
            p.get('max_total_retries') != 8 or p.get('delays_seconds') != [15, 45] or
            p.get('cases') != CASES or p.get('funding_revision') != 'issue60-20261103-192c-3500kt-1p70' or
            p.get('test_only') != rows[0].get('test_only', False)):
        raise StageBudgetExhausted('Recovery scope or limits changed')
    return p


def reservation(rows, ident):
    found = [r for r in rows if r.get('event') == 'reserved' and r.get('request_id') == ident]
    if len(found) != 1:
        raise StageBudgetExhausted('Recovery requires exactly one original reservation')
    return found[0]


def incident(rows, ident):
    """Only durable, request-linked explicit 503 with conservative settlement."""
    start = reservation(rows, ident)
    failed = [r for r in rows if r.get('event') == 'failed' and r.get('request_id') == ident]
    if len(failed) != 1 or any(r.get('event') == 'received' and r.get('request_id') == ident for r in rows):
        raise StageBudgetExhausted('No recoverable failed-only transaction')
    error = failed[0].get('error')
    if not error:
        imports = [r for r in rows if r.get('event') == 'http503_historical_evidence' and r.get('request_id') == ident]
        if len(imports) != 1:
            raise StageBudgetExhausted('Missing explicit historical HTTP status evidence')
        error = imports[0]['error']
    if error.get('status') != 503 or error.get('code') != 'SERVICE_UNAVAILABLE':
        raise StageBudgetExhausted('Only explicit HTTP503 is covered')
    ends = [r for r in rows if r.get('event') == 'money_settled' and r.get('request_id') == ident]
    stops = [r for r in rows if r.get('event') == 'safety_stop' and r.get('request_id') == ident]
    if (len(ends) != 1 or ends[0].get('basis') != 'conservative_reservation' or
            Decimal(ends[0]['charged_usd']) != Decimal(start['reserved_usd']) or
            ends[0].get('reconciliation_required') is not True or
            len(stops) != 1 or stops[0].get('reason') != 'unverified_response_or_interruption'):
        raise StageBudgetExhausted('Original conservative settlement/stop must remain intact')
    return start


def recovery_info(rows, start):
    info = start.get('recovery')
    if info is None:
        imports = [r for r in rows if r.get('event') == 'http503_historical_evidence'
                   and r.get('request_id') == start['request_id']]
        if len(imports) == 1:
            info = imports[0]['recovery']
    if not info or info.get('scope_id') != SCOPE:
        raise StageBudgetExhausted('Transaction has no authorized recovery context')
    return info


def active_stops(rows, scope_id=None, pending_retry=None):
    """A caller without the explicit scope retains the historical hard stop."""
    stops = [r for r in rows if r.get('event') in {'safety_stop', 'stage_closed', 'confirmation_frozen'}]
    if scope_id != SCOPE:
        return [r for r in stops if r.get('event') != 'confirmation_frozen']
    if not policy(rows):
        return stops
    cleared = set()
    for d in (r for r in rows if r.get('event') == 'http503_disposition'):
        if d.get('scope_id') != SCOPE:
            raise StageBudgetExhausted('Unknown disposition scope')
        old = incident(rows, d['request_id'])
        children = [r for r in rows if r.get('event') == 'reserved' and r.get('request_id') == d['retry_request_id']]
        if not children:  # crash between disposition and reservation: not cleared
            continue
        child = children[0]
        a, b = recovery_info(rows, old), recovery_info(rows, child)
        if (b.get('retry_of') != old['request_id'] or b.get('logical_id') != a['logical_id'] or
                b.get('ordinal') != a['ordinal'] + 1 or b['ordinal'] > 2 or
                any(b.get(k) != a.get(k) for k in ('execution_id', 'wire_sha256', 'state_sha256')) or
                child['context'] != old['context'] or child['runtime'] != old['runtime'] or
                child['pricing'] != old['pricing']):
            raise StageBudgetExhausted('Disposition does not match its retry reservation')
        cleared.add(old['request_id'])
    if pending_retry is not None:
        # Temporary admission only for that still-unconsumed retry, under lock.
        incident(rows, pending_retry)
        recovery_info(rows, reservation(rows, pending_retry))
        cleared.add(pending_retry)
    return [r for r in stops if r.get('event') != 'safety_stop' or r.get('request_id') not in cleared]


def retry_metadata(rows, ident, previous, current):
    p = policy(rows)
    if not p or active_stops(rows, SCOPE, previous):
        raise StageBudgetExhausted('Uncovered active stop/freeze')
    old = incident(rows, previous)
    a = recovery_info(rows, old)
    if any(r.get('event') == 'reserved' and r.get('recovery', {}).get('retry_of') == previous for r in rows):
        raise StageBudgetExhausted('Retry already reserved; pending sends cannot be replayed')
    count = sum(r.get('event') == 'reserved' and r.get('recovery', {}).get('scope_id') == SCOPE
                and r['recovery'].get('ordinal', 0) > 0 for r in rows)
    if a['ordinal'] >= 2 or count >= 8:
        raise StageBudgetExhausted('HTTP503 retry allowance exhausted')
    if any(current.get(k) != a.get(k) for k in ('execution_id', 'wire_sha256', 'state_sha256')):
        raise StageBudgetExhausted('Recovery input/scientific checkpoint differs')
    return {**current, 'logical_id': a['logical_id'], 'ordinal': a['ordinal'] + 1, 'retry_of': previous}


def historical_initial_evidence(root, rows, execution_id, source):
    """The only cross-process reconstruction: a proven empty first-call state.

    Existing response journals lacked HTTP status. Link their sole failure to
    the actual turn error, request ID and exact old source/data manifest.
    """
    root = Path(root)
    files = {n: (root/n).read_bytes() for n in ('requests.jsonl', 'responses.jsonl', 'turn-1.json', 'manifest.json')}
    reqs = [json.loads(x) for x in files['requests.jsonl'].decode().splitlines()]
    resp = [json.loads(x) for x in files['responses.jsonl'].decode().splitlines()]
    turn, manifest = (json.loads(files[n]) for n in ('turn-1.json', 'manifest.json'))
    if len(reqs) != 1 or len(resp) != 1:
        raise StageBudgetExhausted('Historical recovery is only a single empty first-call failure')
    req, response, result = reqs[0], resp[0], turn['result']
    ident = req['request_id']; start = reservation(rows, ident)
    error = result['llm']['error']; wm = result['working_memory']
    if (error.get('status') != 503 or error.get('code') != 'SERVICE_UNAVAILABLE' or
            response.get('status') != 'failed' or response.get('request_index') != 1 or
            response.get('error_code') != error['code'] or result['llm']['request_count'] != 1 or
            result['tool_calls'] != 0 or result['tool_results'] or wm['plan'] or wm['graph_history'] or
            result['execution_trace']['events'] or start['context'] != req['context'] or
            start['input_bytes'] != req['actual_wire_payload_bytes'] or
            manifest['runtime'] != start['runtime'] or manifest['case'] != req['context']['case_id'] or
            req['context']['turn'] != 1 or manifest['source'] != source or
            req['settings']['model'] != manifest['runtime']['model']):
        raise StageBudgetExhausted('Historical first-call evidence mismatch/nonempty execution')
    trace = result['execution_trace']
    elapsed = (datetime.fromisoformat(trace['ended_at_utc'].replace('Z', '+00:00')) -
               datetime.fromisoformat(trace['started_at_utc'].replace('Z', '+00:00'))).total_seconds()
    body = {'model': manifest['runtime']['model'], 'messages': req['messages'], 'max_tokens': start['output_cap'],
            'stream': False, 'thinking': {'type': manifest['runtime']['thinking']}}
    if req['tools']: body.update(tools=req['tools'], tool_choice=req['tool_choice'])
    return {'event': 'http503_historical_evidence', 'request_id': ident, 'error': error,
            'artifacts': {n: hashlib.sha256(b).hexdigest() for n, b in files.items()},
            'active_seconds': elapsed, 'original_manifest': manifest, 'original_request': req,
            'recovery': {'scope_id': SCOPE, 'execution_id': execution_id, 'logical_id': ident,
                         'ordinal': 0, 'wire_sha256': digest(body), 'state_sha256': 'empty_initial_state'}}
