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


def behavior(source):
    # Science/prompt/schema live in the shared core. Include original tasks,
    # evaluators and protocols; exclude orchestration/accounting/report scripts.
    files={k:v for k,v in source['files'].items() if k.startswith('config/') or
           k.startswith('src/eeg_harness/') and '/research/' not in k or
           k in {'src/eeg_harness/research/working_memory_issue52.py',
                 'src/eeg_harness/research/working_memory_issue55.py',
                 'src/eeg_harness/research/task_memory.py'}}
    return recovery.digest(files)


def register_candidate(raw,ledger,attestation,candidate_id,*,rationale,final=False,test_only=False):
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
            candidates=[r for r in rows if r.get('event')=='candidate_registered' and r.get('scope_id')==SCOPE]
            frozen=[r for r in rows if r.get('event')=='candidate_final_frozen' and r.get('scope_id')==SCOPE]
            old=next((r for r in candidates if r['candidate_id']==candidate_id),None)
            if frozen and (frozen[0]['candidate_id']!=candidate_id or frozen[0]['behavior']!=fingerprint):
                raise StageBudgetExhausted('Final scientific candidate is frozen')
            if old:
                if old['behavior']!=fingerprint or old['source']!=source:raise StageBudgetExhausted('Registered candidate changed')
            else:
                if len(candidates)>=3 or any(r['behavior']==fingerprint for r in candidates):
                    raise StageBudgetExhausted('At most initial plus two substantive revisions, no hash-only resampling')
                if not rationale or candidates and not rationale.get('new_real_root_cause_evidence'):
                    raise StageBudgetExhausted('Real new root cause required for a revised candidate')
                reserve_coverage(rows,[],test_only)
                old={'event':'candidate_registered','scope_id':SCOPE,'funding_revision':REPAIR_REVISION,
                    'candidate_id':candidate_id,'behavior':fingerprint,'source':source,
                    'runtime':actual_settings(raw),'data':data_manifest(development_records()),
                    'cases':development_cases(),'rationale':rationale,'gate':gate,
                    'readonly_review_sha256':attestation['readonly_review_sha256']}
                _append(ledger,old)
            if final and not frozen:
                _append(ledger,{'event':'candidate_final_frozen','scope_id':SCOPE,'candidate_id':candidate_id,
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
    candidates=[r for r in rows if r.get('event')=='candidate_registered' and r.get('scope_id')==SCOPE]
    if not candidate_id or not candidates or candidates[-1]['candidate_id']!=candidate_id:
        raise StageBudgetExhausted('Latest registered Issue61 candidate required')
    c=candidates[-1]
    if (c['source']!=manifest['source'] or c['behavior']!=behavior(manifest['source']) or
            c['runtime']!=manifest['runtime'] or c['data']!=manifest['data'] or case not in c['cases']):
        raise StageBudgetExhausted('Candidate science, protocol, data or service changed')
    prior=[r for r in rows if r.get('event')=='session_started' and r.get('candidate_id')==candidate_id]
    if any(r['case']==case['id'] for r in prior):raise StageBudgetExhausted('Same task and behavior already attempted')
    if prior and not any(r.get('event')=='recovery_session_finished' and r.get('execution_id')==prior[-1]['execution_id'] for r in rows):
        raise StageBudgetExhausted('Incomplete previous session; do not restart or silently skip')
    covered=[r['case'] for r in prior]
    final=any(r.get('event')=='candidate_final_frozen' and r.get('candidate_id')==candidate_id for r in rows)
    expected=[c for c in recovery.CASES if c not in covered] if final else [c for c in ['T07','M01'] if c not in covered]
    if not expected or case['id']!=expected[0]:raise StageBudgetExhausted('Development/final candidate order mismatch')
    pending,reserve=reserve_coverage(rows,covered,test_only)
    _append(ledger,{'event':'candidate_coverage_reserve','scope_id':SCOPE,'candidate_id':candidate_id,
        'covered':covered,'uncovered':pending,'reserve':reserve,'kind':'planning only, not funding'})


def main():
    import argparse,json
    from ..llm import OpenAICompatibleClient
    from .working_memory_issue55_live import run_session
    p=argparse.ArgumentParser(description=__doc__)
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--register',action='store_true');mode.add_argument('--run',action='store_true')
    p.add_argument('--ledger',type=Path,default=FORMAL_LEDGER)
    p.add_argument('--attestation',type=Path,required=True);p.add_argument('--candidate-id',required=True)
    p.add_argument('--rationale',type=Path);p.add_argument('--final',action='store_true')
    p.add_argument('--case',choices=recovery.CASES);p.add_argument('--output',type=Path)
    args=p.parse_args();a=json.loads(args.attestation.read_text(encoding='utf8'))
    raw=OpenAICompatibleClient.from_env() # construction only, no paid ping
    if args.register:
        if not args.rationale:p.error('--register requires --rationale')
        register_candidate(raw,args.ledger,a,args.candidate_id,
            rationale=json.loads(args.rationale.read_text(encoding='utf8')),final=args.final)
    else:
        if not args.case or not args.output:p.error('--run requires --case and --output')
        case=next(c for c in development_cases() if c['id']==args.case)
        run_session(raw,args.ledger,a,case,args.output,candidate_id=args.candidate_id)

if __name__=='__main__':main()
