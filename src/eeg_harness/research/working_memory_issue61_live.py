"""Issue61 candidate/batch facts appended to the original ledger, no new budget.

Funding, historical incident dispositions and scientific candidates remain
separate facts. Original MoneyBudgetClient owns every reservation and retry.
"""
from decimal import Decimal
from pathlib import Path
from .task_memory_issue39_budget import _rows, _append, _ledger_lock, StageBudgetExhausted
from .working_memory_issue55_live import (REPAIR_CAPS, REPAIR_REVISION, authorization_limits,
    candidate_manifest, recovery, money_totals, _usage, actual_settings, validate_attestation,
    FORMAL_LEDGER, data_manifest, development_records, development_cases)

SCOPE='point1-plan-repair-20261104'
CONTINUATION_SCOPE='point1-operation-delivery-closeout-20261104'
CONTINUATION_PERMISSION='issue61-review-continuation-20261104'
CONTINUATION_RECEIPT='https://github.com/lzy123-web/eeg-agent-harness/issues/55#issuecomment-6623629958'


def register_continuation(raw,ledger,attestation,*,test_only=False):
    """Append a scope fact, never a seventh funding event or reset."""
    ledger=Path(ledger);validate_attestation(attestation,raw,test_only)
    if not test_only and ledger.resolve()!=FORMAL_LEDGER.resolve():raise StageBudgetExhausted('Unique original ledger required')
    with _ledger_lock(Path(str(ledger)+'.session')):
        with _ledger_lock(ledger):
            rows=_rows(ledger)
            if authorization_limits(ledger,rows)!=REPAIR_CAPS or recovery.active_stops(rows,recovery.SCOPE):
                raise StageBudgetExhausted('Original funding or active protection blocks scope')
            reserved={r['request_id'] for r in rows if r.get('event')=='reserved'}
            settled={r['request_id'] for r in rows if r.get('event')=='money_settled'}
            if reserved-settled:raise StageBudgetExhausted('Unsettled sends block scope')
            old=next((r for r in rows if r.get('event')=='scope_permission' and r.get('permission_id')==CONTINUATION_PERMISSION),None)
            if old:
                if old['receipt']!=CONTINUATION_RECEIPT or old['scope_id']!=CONTINUATION_SCOPE:
                    raise StageBudgetExhausted('Scope permission changed')
                return old
            frozen=[r for r in rows if r.get('event')=='candidate_final_frozen' and r.get('scope_id')==SCOPE]
            if len(frozen)!=1:raise StageBudgetExhausted('Original final freeze required')
            if sum(r.get('event')=='authorization_revised' for r in rows)!=6:
                raise StageBudgetExhausted('Exactly original six funding events required')
            prefix=ledger.read_bytes()
            if not test_only:
                import hashlib
                # The anchor may be followed by lawful append-only history;
                # locate its exact recorded prefix, never reissue its balance.
                anchor=Path('artifacts/point1_task_memory/issue61/budget-final.json')
                if not anchor.exists():raise StageBudgetExhausted('Original settled anchor required')
                import json
                expected=json.loads(anchor.read_text(encoding='utf8'))['ledger_sha256']
                if expected!='e0c53d5f3713410df7a30c583a3bf46c9d478a152e1be462327491e42aa40605':
                    raise StageBudgetExhausted('Original anchor changed')
                digest=hashlib.sha256();found=False
                for line in prefix.splitlines(keepends=True):
                    digest.update(line)
                    if digest.hexdigest()==expected:found=True;break
                if not found:raise StageBudgetExhausted('Original ledger prefix changed')
            receipt={'event':'scope_permission','scope_id':CONTINUATION_SCOPE,'permission_id':CONTINUATION_PERMISSION,
                'receipt':CONTINUATION_RECEIPT,'funding_revision':REPAIR_REVISION,'previous_scope':SCOPE,
                'previous_final':frozen[0],'max_candidates':2,'maximum_attempts':120,
                'development_order':['M01'],'prefix_sha256':__import__('hashlib').sha256(prefix).hexdigest(),
                'prefix_bytes':len(prefix),'prior_usage':list(_usage(rows)),
                'prior_usd':str(money_totals(rows,Decimal(rows[0]['rate_ceiling']))),'test_only':test_only}
            _append(ledger,receipt)
            return receipt


def behavior(source):
    # Science/prompt/schema live in the shared core. Include original tasks,
    # evaluators and protocols; exclude orchestration/accounting/report scripts.
    files={k:v for k,v in source['files'].items() if k.startswith('config/') or
           k.startswith('src/eeg_harness/') and '/research/' not in k or
           k in {'src/eeg_harness/research/working_memory_issue52.py',
                 'src/eeg_harness/research/working_memory_issue55.py',
                 'src/eeg_harness/research/task_memory.py'}}
    return recovery.digest(files)


def register_candidate(raw,ledger,attestation,candidate_id,*,rationale,final=False,test_only=False,scope=SCOPE):
    ledger=Path(ledger);validate_attestation(attestation,raw,test_only)
    if not test_only and ledger.resolve()!=FORMAL_LEDGER.resolve():raise StageBudgetExhausted('Unique original ledger required')
    source=candidate_manifest();fingerprint=behavior(source)
    gate=attestation.get('mechanism_gate',{})
    if (gate.get('status')!='passed' or gate.get('source_sha256')!=source['sha256'] or
            not gate.get('evidence_sha256') or not attestation.get('readonly_review_sha256')):
        raise StageBudgetExhausted('Exact-source offline and readonly design review required')
    with _ledger_lock(Path(str(ledger)+'.session')):
        with _ledger_lock(ledger):
            rows=_rows(ledger)
            if authorization_limits(ledger,rows)!=REPAIR_CAPS or recovery.active_stops(rows,recovery.SCOPE):
                raise StageBudgetExhausted('Issue61 funding or active protection blocks candidate')
            p=recovery.policy(rows)
            if not p or p['runtime']!=actual_settings(raw):raise StageBudgetExhausted('Original service/recovery policy required')
            if scope not in {SCOPE,CONTINUATION_SCOPE}:raise StageBudgetExhausted('Unknown candidate scope')
            if scope==CONTINUATION_SCOPE and not any(r.get('event')=='scope_permission' and
                    r.get('permission_id')==CONTINUATION_PERMISSION and r.get('receipt')==CONTINUATION_RECEIPT for r in rows):
                raise StageBudgetExhausted('Explicit continuation scope permission required')
            all_candidates=[r for r in rows if r.get('event')=='candidate_registered']
            candidates=[r for r in all_candidates if r.get('scope_id')==scope]
            frozen=[r for r in rows if r.get('event')=='candidate_final_frozen' and r.get('scope_id')==scope]
            if any(r['candidate_id']==candidate_id and r.get('scope_id')!=scope for r in all_candidates):
                raise StageBudgetExhausted('Candidate ID must be globally unique')
            old=next((r for r in candidates if r['candidate_id']==candidate_id),None)
            if scope==CONTINUATION_SCOPE and final:
                initial=candidates[0]['candidate_id'] if candidates else None
                done={r.get('execution_id') for r in rows if r.get('event')=='recovery_session_finished'}
                if not initial or not any(r.get('event')=='session_started' and r.get('candidate_id')==initial and
                        r.get('case')=='M01' and r.get('execution_id') in done for r in rows):
                    raise StageBudgetExhausted('Initial candidate must diagnose M01 before final freeze')
            if frozen and (frozen[0]['candidate_id']!=candidate_id or frozen[0]['behavior']!=fingerprint):
                raise StageBudgetExhausted('Final scientific candidate is frozen')
            if old:
                if old['behavior']!=fingerprint or old['source']!=source:raise StageBudgetExhausted('Registered candidate changed')
            else:
                if len(candidates)>=(2 if scope==CONTINUATION_SCOPE else 3) or any(r['behavior']==fingerprint for r in all_candidates):
                    raise StageBudgetExhausted('At most initial plus two substantive revisions, no hash-only resampling')
                if not rationale or candidates and not rationale.get('new_real_root_cause_evidence'):
                    raise StageBudgetExhausted('Real new root cause required for a revised candidate')
                order=(['M01'] if not candidates else []) if scope==CONTINUATION_SCOPE else (rationale.get('affected_cases',[]) if candidates else ['T07','M01'])
                if scope==CONTINUATION_SCOPE and candidates and not final:
                    raise StageBudgetExhausted('Only revised final candidate, no second diagnostic')
                if (not order and not final) or len(order)!=len(set(order)) or any(c not in recovery.CASES for c in order):
                    raise StageBudgetExhausted('Revised candidate needs explicit affected original cases')
                reserve_coverage(rows,[],test_only)
                old={'event':'candidate_registered','scope_id':scope,'funding_revision':REPAIR_REVISION,
                    'candidate_id':candidate_id,'behavior':fingerprint,'source':source,
                    'runtime':actual_settings(raw),'data':data_manifest(development_records()),
                    'cases':development_cases(),'development_order':order,'rationale':rationale,'gate':gate,
                    'readonly_review_sha256':attestation['readonly_review_sha256']}
                _append(ledger,old)
            if final and not frozen:
                _append(ledger,{'event':'candidate_final_frozen','scope_id':scope,'candidate_id':candidate_id,
                    'behavior':fingerprint,'rationale':rationale})
            return old


def reserve_coverage(rows,covered,test_only):
    pending=[c for c in recovery.CASES if c not in covered]
    reserve={'calls':24*len(pending),'tokens':450000*len(pending),'usd':str(Decimal('.1875')*len(pending))}
    calls,tokens=_usage(rows)
    if (649-calls<reserve['calls'] or 9328790-tokens<reserve['tokens'] or
            Decimal('3.7417127')-money_totals(rows,Decimal(rows[0]['rate_ceiling']))<Decimal(reserve['usd'])):
        raise StageBudgetExhausted('Final same-version uncovered coverage reserve does not fit')
    return pending,reserve


def admit_candidate_session(ledger,rows,case,manifest,attestation,candidate_id,test_only):
    all_candidates=[r for r in rows if r.get('event')=='candidate_registered']
    selected=next((r for r in all_candidates if r['candidate_id']==candidate_id),None)
    scope=selected['scope_id'] if selected else SCOPE
    if scope==SCOPE and any(r.get('event')=='scope_permission' and r.get('scope_id')==CONTINUATION_SCOPE for r in rows):
        raise StageBudgetExhausted('Previous scope remains frozen; continuation permission is separate')
    candidates=[r for r in all_candidates if r.get('scope_id')==scope]
    if not candidate_id or not candidates or candidates[-1]['candidate_id']!=candidate_id:
        raise StageBudgetExhausted('Latest registered Issue61 candidate required')
    c=candidates[-1]
    equivalent={r['candidate_id'] for r in all_candidates if r['behavior']==c['behavior']}
    if any(r.get('event')=='session_started' and r.get('candidate_id') in equivalent and r.get('case')==case['id'] for r in rows):
        raise StageBudgetExhausted('Same task and behavior already attempted across scopes')
    if (c['source']!=manifest['source'] or c['behavior']!=behavior(manifest['source']) or
            c['runtime']!=manifest['runtime'] or c['data']!=manifest['data'] or case not in c['cases']):
        raise StageBudgetExhausted('Candidate science, protocol, data or service changed')
    prior=[r for r in rows if r.get('event')=='session_started' and r.get('candidate_id')==candidate_id]
    if any(r['case']==case['id'] for r in prior):raise StageBudgetExhausted('Same task and behavior already attempted')
    if prior and not any(r.get('event')=='recovery_session_finished' and r.get('execution_id')==prior[-1]['execution_id'] for r in rows):
        raise StageBudgetExhausted('Incomplete previous session; do not restart or silently skip')
    covered=[r['case'] for r in prior]
    final=any(r.get('event')=='candidate_final_frozen' and r.get('candidate_id')==candidate_id for r in rows)
    expected=[case_id for case_id in (recovery.CASES if final else c['development_order']) if case_id not in covered]
    if not expected or case['id']!=expected[0]:raise StageBudgetExhausted('Development/final candidate order mismatch')
    pending,reserve=reserve_coverage(rows,covered,test_only)
    _append(ledger,{'event':'candidate_coverage_reserve','scope_id':scope,'candidate_id':candidate_id,
        'covered':covered,'uncovered':pending,'reserve':reserve,'kind':'planning only, not funding'})


def continuation_request_fits(rows,candidate_id,calls,tokens,future_money):
    """Keep final coverage space during actual attempts; no future debit."""
    candidates=[r for r in rows if r.get('event')=='candidate_registered' and r.get('scope_id')==CONTINUATION_SCOPE]
    c=next((r for r in candidates if r['candidate_id']==candidate_id),None)
    if not c:return True
    starts=[r for r in rows if r.get('event')=='session_started' and r.get('candidate_id') in {c['candidate_id'] for c in candidates}]
    executions={r['execution_id'] for r in starts}
    spent=sum(r.get('event')=='reserved' and r.get('recovery',{}).get('execution_id') in executions for r in rows)
    if spent+calls>120:return False
    final=any(r.get('event')=='candidate_final_frozen' and r.get('candidate_id')==candidate_id for r in rows)
    covered={r['case'] for r in starts if r.get('candidate_id')==candidate_id} if final else set()
    pending=[case for case in recovery.CASES if case not in covered]
    used_calls,used_tokens=_usage(rows)
    return (649-used_calls-calls>=24*len(pending) and
        9328790-used_tokens-tokens>=450000*len(pending) and
        Decimal('3.7417127')-future_money>=Decimal('.1875')*len(pending))


def main():
    import argparse,json
    from ..llm import OpenAICompatibleClient
    from .working_memory_issue55_live import run_session
    p=argparse.ArgumentParser(description=__doc__)
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--register',action='store_true');mode.add_argument('--run',action='store_true')
    mode.add_argument('--register-continuation',action='store_true')
    p.add_argument('--ledger',type=Path,default=FORMAL_LEDGER)
    p.add_argument('--attestation',type=Path,required=True);p.add_argument('--candidate-id')
    p.add_argument('--scope',choices=[SCOPE,CONTINUATION_SCOPE],default=SCOPE)
    p.add_argument('--rationale',type=Path);p.add_argument('--final',action='store_true')
    p.add_argument('--case',choices=recovery.CASES);p.add_argument('--output',type=Path)
    args=p.parse_args();a=json.loads(args.attestation.read_text(encoding='utf8'))
    raw=OpenAICompatibleClient.from_env() # construction only, no paid ping
    if args.register_continuation:
        register_continuation(raw,args.ledger,a)
    elif args.register:
        if not args.rationale:p.error('--register requires --rationale')
        if not args.candidate_id:p.error('--register requires --candidate-id')
        register_candidate(raw,args.ledger,a,args.candidate_id,
            rationale=json.loads(args.rationale.read_text(encoding='utf8')),final=args.final,scope=args.scope)
    else:
        if not args.case or not args.output:p.error('--run requires --case and --output')
        case=next(c for c in development_cases() if c['id']==args.case)
        run_session(raw,args.ledger,a,case,args.output,candidate_id=args.candidate_id)

if __name__=='__main__':main()
