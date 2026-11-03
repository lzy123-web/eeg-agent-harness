"""Issue55 live session driver and money guard over the original client/leases.

CLI never resets an allowance. Explicit first initialization requires reviewed
zero-history evidence; runs require cumulative transactions and rate attestation.
Tests use explicit test-only attestations and temporary ledgers, no credentials.
"""
import argparse
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

from ..llm import OpenAICompatibleClient, LLMServiceError
from ..task_plan_agent import TaskPlanEEGAgent
from .working_memory_issue50 import Issue50Client
from .working_memory_issue51 import _usage
from .task_memory_issue39_budget import _append, _rows, _ledger_lock, StageBudgetExhausted
from .integrated_method.v2_validation import JournaledBudgetClient
from .working_memory_issue55 import protocol, records_for, score_obligations, data_manifest, SPEC
from .working_memory_issue52 import write_new, encoded, protocol as development_protocol, records_for as development_records, audit_entries
from .task_memory import PROJECT_ROOT
from . import working_memory_issue60_recovery as recovery

GRANT='https://github.com/lzy123-web/eeg-agent-harness/issues/55#issuecomment-6546527306'
LIMITS={'development':(48,2000000),'confirmation':(96,4000000)}
FORMAL_LEDGER=PROJECT_ROOT/'artifacts/point1_task_memory/issue55/budget.jsonl'
ADDITIONAL_GRANT='https://github.com/lzy123-web/eeg-agent-harness/issues/55#issuecomment-6559557879'
REVISION_ID='issue55-development-6559557879'
ORIGINAL_CAPS={'calls':144,'tokens':6000000,'usd':'3','development':[48,2000000],'confirmation':[96,4000000]}
REVISED_CAPS={**ORIGINAL_CAPS,'calls':240,'development':[144,2000000]}
LIVE_GRANT='https://github.com/lzy123-web/eeg-agent-harness/issues/55#issuecomment-6568419952'
LIVE_REVISION='issue58-live-20261102-72c-1mt-1p20'
LIVE_PREFIX='6346c342723594590ab1fc2112824f403ca8cbf56f4070aadf5d631bc99264d1'
LIVE_CAPS={**REVISED_CAPS,'calls':293,'tokens':6234297,'development':[197,2234297],
           'stage_usd':'1.20','cumulative_usd':'1.6054206'}
SOURCE_GRANT='https://github.com/lzy123-web/eeg-agent-harness/issues/55#issuecomment-6573259620'
SOURCE_REVISION='issue59-live-20261102-144c-3mt-2p16'
SOURCE_PREFIX='0553c0359c68a8bcc603fcc392ddd9f8791cc0658efc243e15b1fc14af450c07'
SOURCE_CAPS={**LIVE_CAPS,'calls':407,'tokens':8877118,'development':[311,4877118],
             'stage_usd':'2.16','cumulative_usd':'2.7688482'}
CLOSEOUT_GRANT='https://github.com/lzy123-web/eeg-agent-harness/issues/55#issuecomment-6577641062'
CLOSEOUT_REVISION='issue59-v5-closeout-20261102-plus21c'
CLOSEOUT_PREFIX='4215c2d8505e40f8d3bcb2a513b003f7637f46580cbf505d062a5dba9796e68d'
CLOSEOUT_CAPS={**SOURCE_CAPS,'calls':428,'development':[332,4877118]}
INTERFACE_GRANT='https://github.com/lzy123-web/eeg-agent-harness/issues/55#issuecomment-6597995022'
INTERFACE_REVISION='issue60-20261103-192c-3500kt-1p70'
INTERFACE_PREFIX='14ee78772bf3bc3568b70354d05c721e2ef8b8701d38dba548b3d3667e2b122f'
INTERFACE_CAPS={**CLOSEOUT_CAPS,'calls':593,'tokens':11379334,'development':[497,7379334],
                'stage_usd':'1.70','cumulative_usd':'2.9496989'}
REVIEWED_PREFIXES={INTERFACE_REVISION:(INTERFACE_PREFIX,[305,3879334],'1.2496989'),LIVE_REVISION:(LIVE_PREFIX,[125,1234297],'0.4054206'),
                   SOURCE_REVISION:(SOURCE_PREFIX,[167,1877118],'0.6088482'),
                   CLOSEOUT_REVISION:(CLOSEOUT_PREFIX,[284,3586423],'1.1542944')}
AUTHORIZATION_CHAIN=((REVISION_ID,ADDITIONAL_GRANT,ORIGINAL_CAPS,REVISED_CAPS,48),
                     (LIVE_REVISION,LIVE_GRANT,REVISED_CAPS,LIVE_CAPS,125),
                     (SOURCE_REVISION,SOURCE_GRANT,LIVE_CAPS,SOURCE_CAPS,167),
                     (CLOSEOUT_REVISION,CLOSEOUT_GRANT,SOURCE_CAPS,CLOSEOUT_CAPS,284),
                     (INTERFACE_REVISION,INTERFACE_GRANT,CLOSEOUT_CAPS,INTERFACE_CAPS,305))


def authorization_limits(ledger,rows):
    """Only explicit reviewed grants, in order, over immutable prefixes."""
    revisions=[r for r in rows if r.get('event')=='authorization_revised']
    if not revisions:return deepcopy(ORIGINAL_CAPS)
    if len(revisions)>len(AUTHORIZATION_CHAIN):raise StageBudgetExhausted('Conflicting/repeated authorization records')
    data=Path(ledger).read_bytes()
    for r,(ident,grant,old,new,count) in zip(revisions,AUTHORIZATION_CHAIN):
        index=rows.index(r);prefix=rows[:index];size=r.get('prefix_bytes')
        if (r.get('revision_id')!=ident or r.get('grant')!=GRANT or r.get('additional_grant')!=grant
            or r.get('old_limits')!=old or r.get('new_limits')!=new
            or r.get('allowed_phases')!=['development'] or r.get('test_only')!=rows[0].get('test_only',False)
            or type(size) is not int or size<1 or hashlib.sha256(data[:size]).hexdigest()!=r.get('prefix_sha256')
            or [json.loads(x) for x in data[:size].decode('utf8').splitlines()]!=prefix
            or r.get('prior_usage')!=list(_usage(prefix))
            or r.get('prior_usd')!=str(money_totals(prefix,Decimal(rows[0]['rate_ceiling'])))):
            raise StageBudgetExhausted('Authorization prefix, snapshot or absolute limits changed')
        if _usage(prefix)[0]!=count or _usage(prefix,lambda c:c.get('phase')=='development')[0]!=count:
            raise StageBudgetExhausted('Authorization history count/phase changed')
        anchor=REVIEWED_PREFIXES.get(ident)
        if anchor and not r['test_only'] and (r['prefix_sha256']!=anchor[0]
                or r['prior_usage']!=anchor[1] or Decimal(r['prior_usd'])!=Decimal(anchor[2])):
            raise StageBudgetExhausted('Reviewed original authorization snapshot changed')
    return deepcopy(revisions[-1]['new_limits'])


def apply_authorization_revision(raw,ledger,attestation,authorization,*,test_only=False):
    """Append the approved revision to the same ledger; never reopen or reset."""
    ledger=Path(ledger)
    validate_attestation(attestation,raw,test_only)
    if not test_only and ledger.resolve()!=FORMAL_LEDGER.resolve():
        raise StageBudgetExhausted('Use the unique original formal ledger')
    spec=next((s for s in AUTHORIZATION_CHAIN if s[0]==authorization.get('revision_id')),None)
    if spec is None:raise StageBudgetExhausted('Unknown explicit authorization')
    ident,grant,old,new,count=spec
    if (authorization.get('grant')!=GRANT or authorization.get('additional_grant')!=grant
            or authorization.get('test_only') is not test_only or authorization.get('new_limits')!=new):
        raise StageBudgetExhausted('Exact explicit additional authorization required')
    with _ledger_lock(Path(str(ledger)+'.session')):
        # Reuse transaction validation, original-price recovery and stop guards.
        client=MoneyBudgetClient(JournaledBudgetClient(raw,ledger.parent/'unused-revision-journal'),ledger,
            attestation,'development',request_journal=ledger.parent/'unused-revision-requests',test_only=test_only)
        with _ledger_lock(ledger):
            rows=_rows(ledger);authorization_limits(ledger,rows)
            if any(r.get('event') in {'safety_stop','stage_closed','confirmation_frozen'} or
                   r.get('event')=='session_started' and r.get('phase')=='confirmation' for r in rows):
                raise StageBudgetExhausted('Existing stop/freeze cannot be overridden')
            previous=next((r for r in rows if r.get('event')=='authorization_revised' and r.get('revision_id')==ident),None)
            if previous:
                if authorization.get('prefix_sha256')!=previous['prefix_sha256']:
                    raise StageBudgetExhausted('Conflicting revision application')
                return previous # idempotent, even after later spending
            data=ledger.read_bytes();digest=hashlib.sha256(data).hexdigest()
            if digest!=authorization.get('prefix_sha256'):
                raise StageBudgetExhausted('Ledger changed since authorization snapshot')
            if authorization_limits(ledger,rows)!=old:
                raise StageBudgetExhausted('Prior approved amendment must precede this grant')
            anchor=REVIEWED_PREFIXES.get(ident)
            if anchor and not test_only and digest!=anchor[0]:
                raise StageBudgetExhausted('Require the reviewed original grant prefix')
            starts=[r for r in rows if r.get('event')=='reserved']
            if (_usage(rows)[0]!=count or _usage(rows,lambda c:c.get('phase')=='development')[0]!=count
                    or starts[-1].get('runtime')!=client.runtime or starts[-1].get('pricing')!=client.pricing):
                raise StageBudgetExhausted('Expected reviewed development calls and unchanged service/settings/prices')
            record={'event':'authorization_revised','revision_id':ident,'grant':GRANT,
                'additional_grant':grant,'test_only':test_only,'old_limits':old,
                'new_limits':new,'allowed_phases':['development'],'prefix_bytes':len(data),
                'prefix_sha256':digest,'prior_usage':list(_usage(rows)),
                'prior_usd':str(money_totals(rows,client.rate)),
                'runtime':actual_settings(raw),'pricing':client.pricing,'timestamp_utc':time.time()}
            _append(ledger,record)
            return record


def initialize_ledger(raw,ledger,attestation,reconciliation,*,test_only=False):
    """Explicit first opening, not recovery, with independently reviewed evidence.

    This checks the audit contract and immutable file links, not the truth of
    all historical activity. An unknown history must never be marked zero.
    Real runs have one canonical ledger; existing/closed files are untouched.
    """
    validate_attestation(attestation,raw,test_only)
    ledger, reconciliation=Path(ledger),Path(reconciliation)
    if not test_only and ledger.resolve()!=FORMAL_LEDGER.resolve():
        raise StageBudgetExhausted('First opening must use the unique Issue55 formal ledger')
    proof=json.loads(reconciliation.read_text(encoding='utf8'))
    if (proof.get('grant')!=GRANT or proof.get('test_only') is not test_only or
            proof.get('conclusion')!='no_prior_issue55_calls' or
            proof.get('prior_usage')!={'completions':0,'api_tokens':0,'usd':0} or
            proof.get('unsettled')!=[] or proof.get('prior_stage_closed') is not False or
            proof.get('prior_confirmation_started') is not False or not proof.get('coverage')):
        raise StageBudgetExhausted('Reviewed complete zero-history evidence required; unknown is not zero')
    evidence=proof.get('evidence',[])
    if not evidence:raise StageBudgetExhausted('Original audit evidence is required')
    for row in evidence:
        path=Path(row['path'])
        if not path.is_absolute():path=PROJECT_ROOT/path
        if hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:
            raise StageBudgetExhausted('Historical audit evidence changed')
    rate=max(Decimal(str(attestation[k])) for k in ('input_usd_per_million','output_usd_per_million'))
    header={'event':'opened','stage':'issue55','test_only':test_only,'grant':GRANT,
        'reconciled':True,'rate_ceiling':str(rate),'initialization':'first_after_history_review',
        'reconciliation_sha256':hashlib.sha256(reconciliation.read_bytes()).hexdigest(),
        'reconciliation_evidence':evidence,'timestamp_utc':time.time(),
        'max_requests':144,'max_tokens':6000000,'max_usd':'3','phase_limits':LIMITS}
    ledger.parent.mkdir(parents=True,exist_ok=True)
    with _ledger_lock(Path(str(ledger)+'.session')):
        with ledger.open('x',encoding='utf8') as stream:
            stream.write(json.dumps(header,ensure_ascii=False,allow_nan=False)+'\n')
            stream.flush()
            os.fsync(stream.fileno())
    return header


def actual_settings(raw):
    return {'endpoint_sha256':hashlib.sha256(getattr(raw,'base_url','TEST-ONLY').encode()).hexdigest(),
        'model':raw.model,'thinking':getattr(raw,'thinking','disabled'),'timeout':raw.timeout,
        'max_output_tokens':raw.max_tokens,'max_retries':raw.max_retries}


def candidate_manifest():
    """Hash actual code, prompts, protocol and evaluator, including dirty edits."""
    paths=sorted(list((PROJECT_ROOT/'src').rglob('*.py'))+list((PROJECT_ROOT/'config').rglob('*.json')))
    hashes={p.relative_to(PROJECT_ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    return {'files':hashes,'sha256':hashlib.sha256(encoded(hashes)).hexdigest()}


def register_http503_recovery(raw,ledger,attestation,*,baseline,original_output=None,test_only=False):
    """Register scope (not funding) only after the exact-source offline gate.

    Original evidence is verified before any append. Repeated receipts reuse
    the permission and never reset attempts or overwrite stops/settlements.
    """
    ledger=Path(ledger)
    validate_attestation(attestation,raw,test_only)
    if not test_only and ledger.resolve()!=FORMAL_LEDGER.resolve():
        raise StageBudgetExhausted('Recovery must use the original unique ledger')
    source=candidate_manifest()
    if hashlib.sha256(encoded(baseline['source']['files'])).hexdigest()!=baseline['source']['sha256']:
        raise StageBudgetExhausted('Baseline manifest file digest does not match its declared source')
    if not test_only and baseline['source']['sha256']!=recovery.BASELINE_SOURCE:
        raise StageBudgetExhausted('Use the reviewed original scientific freeze, not a new candidate')
    protected={k:v for k,v in source['files'].items() if k not in recovery.RECOVERY_FILES}
    if protected!={k:v for k,v in baseline['source']['files'].items() if k not in recovery.RECOVERY_FILES}:
        raise StageBudgetExhausted('Only the explicitly bounded recovery modules may change')
    gate=attestation.get('mechanism_gate',{})
    if not test_only and (gate.get('status')!='passed' or gate.get('source_sha256')!=source['sha256']
            or not gate.get('evidence_sha256') or not attestation.get('recovery_readonly_review_sha256')):
        raise StageBudgetExhausted('Exact-source offline and readonly recovery gates required')
    with _ledger_lock(Path(str(ledger)+'.session')):
        client=MoneyBudgetClient(JournaledBudgetClient(raw,ledger.parent/'unused-recovery-journal'),ledger,
            attestation,'development',request_journal=ledger.parent/'unused-recovery-requests',test_only=test_only)
        with _ledger_lock(ledger):
            rows=_rows(ledger);old=recovery.policy(rows)
            if old:
                if old['runtime']!=client.runtime or old['protected_source']!=protected or old['pricing']!=client.pricing:
                    raise StageBudgetExhausted('Conflicting recovery registration')
                return old
            if not test_only and (client.caps!=INTERFACE_CAPS or original_output is None):
                raise StageBudgetExhausted('Original Issue60 funding/evidence required')
            orphan=next((r for r in rows if r.get('event')=='http503_historical_evidence'),None)
            evidence=(recovery.historical_initial_evidence(original_output,rows,
                      orphan['recovery']['execution_id'] if orphan else str(uuid.uuid4()),baseline['source'])
                      if original_output is not None else None)
            if orphan and orphan!=evidence:raise StageBudgetExhausted('Historical recovery evidence conflict')
            if evidence and not test_only and evidence['request_id']!=recovery.KNOWN_REQUEST:
                raise StageBudgetExhausted('Only reviewed historical incident may be imported')
            proposed=rows+([evidence] if evidence and not orphan else [])
            if evidence:recovery.incident(proposed,evidence['request_id'])
            blocked=recovery.active_stops(rows,recovery.SCOPE)
            if any(r.get('event')!='safety_stop' or not evidence or r.get('request_id')!=evidence['request_id'] for r in blocked):
                raise StageBudgetExhausted('Other active stop/freeze not covered by recovery')
            data=ledger.read_bytes()
            p={'event':'http503_recovery_permission','scope_id':recovery.SCOPE,
                'permission':recovery.PERMISSION,'receipt':recovery.RECEIPT,'test_only':test_only,
                'funding_revision':INTERFACE_REVISION,'max_retries_per_request':2,'max_total_retries':8,
                'delays_seconds':[15,45],'cases':recovery.CASES,'protected_source':protected,
                'baseline_source':baseline['source'],'runtime':client.runtime,'pricing':client.pricing,
                'data':data_manifest(development_records()),'prefix_bytes':len(data),
                'prefix_sha256':hashlib.sha256(data).hexdigest(),'timestamp_utc':time.time()}
            # Import first: a crash here cannot unlock anything without scope.
            if evidence and not orphan:_append(ledger,evidence)
            _append(ledger,p)
            return p


def development_cases():
    """Original cases plus preregistered synthetic development transfers."""
    extra=PROJECT_ROOT/'config/point1_working_memory_issue60.json'
    return development_protocol()['cases']+(json.loads(extra.read_text(encoding='utf8'))['cases'] if extra.exists() else [])


def scored_case(case,phase):
    case=deepcopy(case)
    if phase=='development' and any(case==c for c in development_protocol()['cases']):
        inventory=json.loads((PROJECT_ROOT/'config/point1_working_memory_issue55_development_scoring.json').read_text(encoding='utf8'))
        case['evaluation_only']['obligations']=[dict(zip(inventory['format'],row)) for row in inventory['cases'][case['id']]]
    return case


def followup_decision(case,turn,result,controller,scoring):
    """Evaluator-only policy gate: internal waiting is never an outward ask."""
    stops=case.get('evaluation_only',{}).get('allowed_stops',[])
    policies=json.loads((PROJECT_ROOT/'config/point1_working_memory_followup_policies.json').read_text(encoding='utf8'))['policies']
    kind=('clarification' if len(stops)>=turn and stops[turn-1]=='clarification_required'
          else policies.get(case.get('followup_policy'),'ordinary' if not case.get('followup_policy') else 'review_required'))
    if kind=='ordinary':return {'allowed':True,'reason':'ordinary_user_turn'}
    if kind=='review_required':return {'allowed':False,'reason':'unrecognized_policy_requires_review'}
    if result.stop_reason not in {'partial','clarification_required'} or not scoring.get('all_required_results_correct'):
        return {'allowed':False,'reason':'lawful_partial_delivery_missing'}
    expected=[d for d in case.get('evaluation_only',{}).get('obligations',[]) if d['turn']==turn+1]
    for q in controller.clarifications:
        if q['question'] not in result.final_answer or q['verification']!='missing_literal_window':continue
        n=controller.graph.nodes.get(q['task_id']);d=n.delivery(q['key']) if n else None
        if not d or n.revision!=q['revision']:continue
        missing=set(controller.store._required_fields(d.capability))-set(controller._effective_scope(d))
        if set(q['fields'])!=missing:continue
        if any(q['record']==e['record'] and controller.store._family(q['capability'])==controller.store._family(e['capability'])
                and all(e['scope'].get(k)==v for k,v in q['scope'].items()) and missing.issubset(e['scope']) for e in expected):
            return {'allowed':True,'reason':'validated_delivered_question','question':q}
    return {'allowed':False,'reason':'matching_delivered_clarification_absent_or_requires_review'}


def admit_session(ledger,case,phase,manifest,attestation,test_only,*,recovery_context=None):
    rows=_rows(ledger)
    caps=authorization_limits(ledger,rows)
    if caps!=ORIGINAL_CAPS and phase!='development':
        raise StageBudgetExhausted('Additional authorization forbids confirmation in this stage')
    starts=[r for r in rows if r.get('event')=='session_started']
    scope=recovery_context and recovery.SCOPE
    pending=recovery_context.get('resume_request') if recovery_context else None
    if recovery.active_stops(rows,scope,pending):
        raise StageBudgetExhausted('Stage stopped; audit existing evidence')
    if recovery_context:
        p=recovery.policy(rows)
        if (phase!='development' or not p or case['id'] not in p['cases'] or
                manifest['runtime']!=p['runtime'] or manifest['data']!=p['data']):
            raise StageBudgetExhausted('Recovery outside frozen original four conversations')
        protected={k:v for k,v in manifest['source']['files'].items() if k not in recovery.RECOVERY_FILES}
        if protected!=p['protected_source']:
            raise StageBudgetExhausted('Scientific implementation/prompt/data/protocol drift')
        prior=[r for r in rows if r.get('event')=='session_started' and r.get('recovery_scope')==recovery.SCOPE]
        if len(prior)>=len(p['cases']) or p['cases'][len(prior)]!=case['id']:
            raise StageBudgetExhausted('Recovery conversations are ordered and one-shot')
        if prior and not any(r.get('event')=='recovery_session_finished' and
                r.get('execution_id')==prior[-1]['execution_id'] for r in rows):
            raise StageBudgetExhausted('Previous recovery session incomplete; do not restart or skip it')
        if pending:
            imported=next(r for r in rows if r.get('event')=='http503_historical_evidence' and r['request_id']==pending)
            if imported['original_manifest']['case']!=case['id'] or prior:
                raise StageBudgetExhausted('Only the linked empty first conversation can resume')
        if not test_only:
            remaining=len(p['cases'])-len(prior)
            used_calls,used_tokens=_usage(rows)
            reserve={'calls':24*remaining-(1 if pending else 0),'tokens':450000*remaining,
                     'usd':str(Decimal('.1875')*remaining)}
            if (caps['development'][0]-used_calls<reserve['calls'] or
                    caps['development'][1]-used_tokens<reserve['tokens'] or
                    Decimal(caps['cumulative_usd'])-money_totals(rows,Decimal(rows[0]['rate_ceiling']))<Decimal(reserve['usd'])):
                raise StageBudgetExhausted('Remaining final coverage reserve does not fit original allowance')
            _append(ledger,{'event':'recovery_coverage_reserve','scope_id':recovery.SCOPE,
                'case':case['id'],'uncovered':p['cases'][len(prior):],'reserve':reserve,
                'kind':'planning reserve only, not additional funding'})
    if not test_only:
        gate=attestation.get('mechanism_gate',{})
        if (gate.get('status')!='passed' or gate.get('source_sha256')!=manifest['source']['sha256']
                or not gate.get('evidence_sha256')):
            raise StageBudgetExhausted('Mechanism regression gate must pass for this exact source before payment')
        expected=protocol()['cases'] if phase=='confirmation' else (development_cases() if caps==INTERFACE_CAPS else development_protocol()['cases'])
        if case not in expected:
            raise StageBudgetExhausted('Use original protocol requests, not a substituted case')
    if not test_only and caps==INTERFACE_CAPS and any(r.get('case')==case['id'] and r.get('source_sha256')==manifest['source']['sha256'] for r in starts):
        raise StageBudgetExhausted('Same task and frozen source already attempted; no resampling')
    confirmations=[r for r in starts if r['phase']=='confirmation']
    if phase=='development' and confirmations:
        raise StageBudgetExhausted('No development after confirmation freeze')
    if phase=='confirmation':
        order=protocol()['confirmation_order']
        if len(confirmations)>=len(order) or case['id']!=order[len(confirmations)]:
            raise StageBudgetExhausted('Confirmation is ordered, one-shot, including failed/interrupted attempts')
        freeze={'source':manifest['source']['sha256'],'data':manifest['data'],
                'protocol':manifest['protocol_sha256'],'attestation':attestation,'runtime':manifest['runtime']}
        previous=next((r['freeze'] for r in rows if r.get('event')=='confirmation_frozen'),None)
        if previous is not None and previous!=freeze:
            raise StageBudgetExhausted('Code/data/protocol/model/rates changed after freeze')
        if not test_only and not any(r.get('event')=='diagnostic_review' and r.get('status')=='passed'
                and r.get('source_sha256')==manifest['source']['sha256'] for r in rows):
            raise StageBudgetExhausted('Review finite development results before confirmation')
        if previous is None:_append(ledger,{'event':'confirmation_frozen','freeze':freeze})
    _append(ledger,{'event':'session_started','phase':phase,'case':case['id'],
        **({'recovery_scope':recovery.SCOPE,'execution_id':recovery_context['execution_id'],
            'resumes_request':pending} if recovery_context else {}),
        'source_sha256':manifest['source']['sha256'],'test_only':test_only,'timestamp_utc':time.time()})


def money_totals(rows, rate):
    starts={r['request_id']:r for r in rows if r.get('event')=='reserved'}
    settlements={r['request_id']:r for r in rows if r.get('event')=='money_settled'}
    return sum((Decimal(settlements[i]['charged_usd']) if i in settlements else
                Decimal(r['reserved_usd']) if 'reserved_usd' in r else
                Decimal(r['reserved_tokens'])*max(rate,Decimal(str(rows[0].get('rate_ceiling',rate))))/1000000) for i,r in starts.items())


def validate_attestation(a, raw, test_only):
    if a.get('grant') != GRANT or a.get('test_only') is not test_only:
        raise StageBudgetExhausted('A matching Issue55 grant/test boundary is required')
    if test_only != bool(getattr(raw,'is_test_client',False)):
        raise StageBudgetExhausted('Test authorization must never reach a real client')
    for k in ('input_usd_per_million','output_usd_per_million'):
        rate=Decimal(str(a.get(k)))
        if not rate.is_finite() or rate < 0:
            raise ValueError('Finite nonnegative verified rates required')
    models=a.get('accepted_response_models')
    if (not isinstance(a.get('rate_source'),str) or not a['rate_source'].strip() or
            not isinstance(models,list) or not models or any(not isinstance(m,str) or not m for m in models) or
            raw.model != a.get('model')):
        raise StageBudgetExhausted('Pin actual model, response IDs and rate evidence')
    if not test_only:
        if raw.model not in {'deepseek-flash','deepseek-chat'}:
            raise StageBudgetExhausted('Only the existing authorized Flash family is allowed')
        if hashlib.sha256(raw.base_url.encode()).hexdigest()!=a.get('endpoint_sha256'):
            raise StageBudgetExhausted('Actual endpoint does not match verified rate attestation')
    if raw.max_tokens!=2200 or raw.max_retries!=0:
        raise StageBudgetExhausted('Output must be 2200 and retries zero')


class MoneyBudgetClient(Issue50Client):
    """Reuse wire serialization, native loop hooks and immutable final lease.

    Reservations use the higher input/output price for every reserved token,
    including current-final lease tokens: conservative, never cache-discounted.
    Settlement uses noncached input and output counts; missing receipts retain
    the full reservation. Phase pools are independent and never resized.
    """
    def __init__(self,journal,ledger,attestation,phase,*,request_journal,test_only=False):
        validate_attestation(attestation,journal.client,test_only)
        if phase not in LIMITS:raise ValueError('Unknown phase')
        self.client,self.ledger=journal,Path(ledger)
        if not test_only and self.ledger.resolve()!=FORMAL_LEDGER.resolve():
            raise StageBudgetExhausted('Real calls must use the unique Issue55 ledger')
        self.attestation=deepcopy(attestation)
        self.rate=max(Decimal(str(attestation[k])) for k in ('input_usd_per_million','output_usd_per_million'))
        self.context={'phase':phase,'arm':'C'}
        self.request_journal=Path(request_journal)
        self.runtime=actual_settings(journal.client)
        self.pricing={k:deepcopy(attestation[k]) for k in ('model','accepted_response_models',
            'input_usd_per_million','output_usd_per_million','rate_source')}
        self.pricing['endpoint_sha256']=self.runtime['endpoint_sha256']
        self.final_only,self.delivery_checkpoint,self._lease=False,None,None
        rows=_rows(self.ledger)
        if not rows or rows[0].get('stage')!='issue55' or rows[0].get('test_only',False)!=test_only:
            raise StageBudgetExhausted('Require existing reconciled Issue55 ledger, never create a new allowance')
        p=recovery.policy(rows)
        if p and hashlib.sha256(self.ledger.read_bytes()[:p['prefix_bytes']]).hexdigest()!=p['prefix_sha256']:
            raise StageBudgetExhausted('Recovery original prefix changed')
        reconciliation=next((r for r in reversed(rows) if r.get('event')=='issue55_reconciled'),rows[0])
        if reconciliation.get('grant')!=GRANT or reconciliation.get('reconciled') is not True:
            raise StageBudgetExhausted('Cumulative calls/tokens/fees must be reconciled to the existing grant')
        if reconciliation.get('rate_ceiling')!=str(self.rate):
            raise StageBudgetExhausted('Ledger rate ceiling differs; audit migration, do not reset')
        if any(r.get('event')=='stage_closed' for r in rows):
            raise StageBudgetExhausted('Closed stage cannot reopen')
        self.caps=authorization_limits(self.ledger,rows)
        amendment=next((r for r in reversed(rows) if r.get('event')=='authorization_revised'),None)
        # The closeout adds calls only; Issue59's original money baseline stays.
        money_amendment=(next(r for r in rows if r.get('revision_id')==SOURCE_REVISION)
                         if amendment and amendment['revision_id']==CLOSEOUT_REVISION else amendment)
        self.stage_money_start=Decimal(money_amendment['prior_usd']) if money_amendment else Decimal('0')
        if amendment and (phase!='development' or self.runtime!=amendment['runtime'] or self.pricing!=amendment['pricing']):
            raise StageBudgetExhausted('Revised grant allows only development with the original service/settings/prices')
        starts=[r for r in rows if r.get('event')=='reserved']
        if len({r['request_id'] for r in starts})!=len(starts) or any(
                r.get('context',{}).get('phase') not in LIMITS or
                type(r.get('reserved_tokens')) is not int or r['reserved_tokens']<0 for r in starts):
            raise StageBudgetExhausted('Duplicate transactions or unassigned historical phase; reconcile without resetting')
        reservations={r['request_id']:r for r in starts}
        for event in ('money_settled','received','failed'):
            entries=[r for r in rows if r.get('event')==event]
            if len({r['request_id'] for r in entries})!=len(entries):
                raise StageBudgetExhausted('Repeated settlement or receipt requires reconciliation')
            for row in entries:
                if row['request_id'] not in reservations:
                    raise StageBudgetExhausted('Receipt without original reservation')
                if event=='money_settled':
                    amount=Decimal(row['charged_usd'])
                    if not amount.is_finite() or amount<0:raise StageBudgetExhausted('Invalid historical fee')
                if row.get('total_tokens') is not None and (type(row['total_tokens']) is not int or
                        not 0<=row['total_tokens']<=reservations[row['request_id']]['reserved_tokens']):
                    raise StageBudgetExhausted('Invalid historical token usage')
        self.scientific_guard=None
        self.recovery_context=None
        self._retry_of=None
        self._turn_started=None
        self._active_before=0
        self.recovery_state=None
        self.settle_pending()

    def enable_recovery(self, context, state):
        p=recovery.policy(_rows(self.ledger))
        if not p or p['runtime']!=self.runtime or p['pricing']!=self.pricing:
            raise StageBudgetExhausted('Missing matching recovery permission/runtime/pricing')
        self.recovery_context=deepcopy(context)
        self._retry_of=context.get('resume_request')
        self.recovery_state=state
        if self._retry_of:
            imported=next(r for r in _rows(self.ledger) if r.get('event')=='http503_historical_evidence'
                          and r['request_id']==self._retry_of)
            self._active_before=imported['active_seconds']

    def set_context(self, **values):
        changed='turn' in values and values['turn']!=self.context.get('turn')
        if changed:
            self._turn_started=time.monotonic()
            if values['turn']!=1:self._active_before=0
        super().set_context(**values)

    def _turn_attempts(self,rows):
        if not self.recovery_context:return 0
        return sum(r.get('event')=='reserved' and r.get('context',{}).get('turn')==self.context.get('turn')
            and recovery.recovery_info(rows,r).get('execution_id')==self.recovery_context['execution_id']
            for r in rows if r.get('event')=='reserved' and (r.get('recovery') or any(
                e.get('event')=='http503_historical_evidence' and e['request_id']==r['request_id'] for e in rows)))

    def _time_remaining(self):
        return 900-self._active_before-(time.monotonic()-self._turn_started if self._turn_started is not None else 0)

    def attempt_metadata(self,rows,ident,body):
        if not self.recovery_context:return {}
        current={'scope_id':recovery.SCOPE,'execution_id':self.recovery_context['execution_id'],
            'wire_sha256':recovery.digest(body),'state_sha256':self.recovery_state(),
            'logical_id':ident,'ordinal':0}
        if self._retry_of:
            current=recovery.retry_metadata(rows,ident,self._retry_of,current)
            old=recovery.reservation(rows,self._retry_of)
            if old['runtime']!=self.runtime or old['pricing']!=self.pricing or old['context']!=self.context:
                raise StageBudgetExhausted('Recovery original settings or turn changed')
            delay=[15,45][current['ordinal']-1]
            if getattr(self,'_waited_for',None)!=(self._retry_of,delay):
                raise StageBudgetExhausted('Retry requires its authorized backoff')
        return {'recovery':current}

    def commit_attempt(self,rows,ident,metadata):
        info=metadata.get('recovery',{})
        if info.get('retry_of'):
            _append(self.ledger,{'event':'http503_disposition','scope_id':recovery.SCOPE,
                'request_id':info['retry_of'],'retry_request_id':ident,'logical_id':info['logical_id'],
                'ordinal':info['ordinal'],'retains_unknown_usage':True,'billing_verified':False,
                'timestamp_utc':time.time()})

    def reservation_metadata(self,tokens):
        return {'pricing':deepcopy(self.pricing),'reserved_usd':str(Decimal(tokens)*self.rate/1000000),
                'runtime':deepcopy(self.runtime)}

    def settle_pending(self):
        """Recover using each transaction's original tariff, never today's."""
        with _ledger_lock(self.ledger):
            rows=_rows(self.ledger)
            settled={r['request_id'] for r in rows if r.get('event')=='money_settled'}
            ends={r['request_id']:r for r in rows if r.get('event') in {'received','failed'}}
            for start in [r for r in rows if r.get('event')=='reserved' and r['request_id'] not in settled]:
                pricing=start.get('pricing')
                if not pricing or 'reserved_usd' not in start:
                    if not any(r.get('event')=='safety_stop' and r.get('request_id')==start['request_id'] for r in rows):
                        _append(self.ledger,{'event':'safety_stop','request_id':start['request_id'],
                            'reason':'historical_pricing_missing','reconciliation_required':True})
                    continue  # Original reservation stays; do not invent a fee.
                end=ends.get(start['request_id'],{})
                usage=end.get('usage',{})
                inp,out=usage.get('prompt_tokens'),usage.get('completion_tokens')
                usage_valid=(type(inp) is int and type(out) is int and inp>=0 and 0<=out<=start['output_cap'] and
                    inp+out==end.get('total_tokens') and inp+out<=start['reserved_tokens'])
                model_valid=end.get('response_model_reported') in pricing['accepted_response_models']
                valid=usage_valid and model_valid and end.get('event')=='received'
                cost=(Decimal(inp)*Decimal(str(pricing['input_usd_per_million']))+
                    Decimal(out)*Decimal(str(pricing['output_usd_per_million'])))/1000000 if valid else Decimal(start['reserved_usd'])
                _append(self.ledger,{'event':'money_settled','request_id':start['request_id'],
                    'charged_usd':str(cost),'basis':'usage_noncache_price_upper_bound' if valid else 'conservative_reservation',
                    'pricing':pricing,'billing_receipt':False,'reconciliation_required':not valid})
                if not valid:
                    _append(self.ledger,{'event':'safety_stop','request_id':start['request_id'],
                        'reason':'unverified_response_or_interruption','reconciliation_required':True})
            # A crash can occur after settlement fsync but before stop fsync.
            # Repair the missing protection, never charge/refund it again.
            rows=_rows(self.ledger)
            stopped={r.get('request_id') for r in rows if r.get('event')=='safety_stop'}
            for end in rows:
                if (end.get('event')=='money_settled' and end.get('reconciliation_required') is True
                        and end['request_id'] not in stopped):
                    _append(self.ledger,{'event':'safety_stop','request_id':end['request_id'],
                        'reason':'unverified_response_or_interruption','reconciliation_required':True})

    def _fits(self,rows,calls,tokens):
        if recovery.active_stops(rows,recovery.SCOPE if self.recovery_context else None,self._retry_of):return False
        if self.recovery_context and (self._turn_attempts(rows)+calls>12 or self._time_remaining()<self.client.client.timeout):return False
        total=_usage(rows)
        phase=_usage(rows,lambda c:c.get('phase')==self.context['phase'])
        cap=self.caps[self.context['phase']]
        future_money=money_totals(rows,self.rate)+Decimal(tokens)*self.rate/1000000
        if 'stage_usd' in self.caps and (future_money-self.stage_money_start>Decimal(self.caps['stage_usd'])
                or future_money>Decimal(self.caps['cumulative_usd'])):return False
        return (total[0]+calls<=self.caps['calls'] and total[1]+tokens<=self.caps['tokens'] and
                phase[0]+calls<=cap[0] and phase[1]+tokens<=cap[1] and
                future_money<=Decimal(self.caps['usd']))

    def complete(self,messages,tools,tool_choice='auto'):
        if self.recovery_context:
            with _ledger_lock(Path(str(self.ledger)+'.attempt')):
                return self._recovering_complete(messages,tools,tool_choice)
        return self._complete_once(messages,tools,tool_choice)

    def _recovering_complete(self,messages,tools,tool_choice):
        original=deepcopy((messages,tools,tool_choice))
        while True:
            if self._retry_of:
                rows=_rows(self.ledger)
                current={'scope_id':recovery.SCOPE,'execution_id':self.recovery_context['execution_id'],
                    'wire_sha256':recovery.digest(self.wire(*original)),'state_sha256':self.recovery_state()}
                meta=recovery.retry_metadata(rows,'pending',self._retry_of,current)
                delay=[15,45][meta['ordinal']-1]
                if self._time_remaining()<delay+self.client.client.timeout:
                    raise LLMServiceError('STAGE_BUDGET_EXHAUSTED','No active time for authorized retry')
                # Keep the immutable final lease while retrying a decision.
                reserve=self.reservation(*original)
                if not self._fits(rows,1+(0 if self.final_only else 1),reserve+(0 if self.final_only else (self._lease or {}).get('reserved_tokens',0))):
                    raise LLMServiceError('STAGE_BUDGET_EXHAUSTED','Retry plus original final lease does not fit')
                _append(self.request_journal,{'event':'http503_backoff','request_id':self._retry_of,
                    'seconds':delay,'ordinal':meta['ordinal'],'timestamp_utc':time.time()})
                time.sleep(delay)
                self._waited_for=(self._retry_of,delay)
            before=getattr(self,'last_request_id',None)
            try:
                response=self._complete_once(*original)
            except LLMServiceError as exc:
                ident=getattr(self,'last_request_id',None)
                if exc.status!=503 or exc.code!='SERVICE_UNAVAILABLE' or not ident or ident==before:
                    raise
                self._retry_of=ident
                continue
            self._retry_of=None
            return response

    def _complete_once(self,messages,tools,tool_choice='auto'):
        self.settle_pending()
        if actual_settings(self.client.client)!=self.runtime:
            raise LLMServiceError('CONFIGURATION_CHANGED','Actual client settings differ from the reserved/frozen settings')
        if self.scientific_guard is not None:
            self.scientific_guard()
        try:
            response=super().complete(messages,tools,tool_choice)
        finally:
            # Also accounts failed calls; interruption before this point leaves
            # a conservative reserved transaction in the persistent ledger.
            self.settle_pending()
        if recovery.active_stops(_rows(self.ledger),recovery.SCOPE if self.recovery_context else None):
            raise LLMServiceError('STAGE_BUDGET_EXHAUSTED','Unexpected response model or invalid usage; stop and audit')
        return response


def run_session(raw,ledger,attestation,case,output,*,phase='development',test_only=False,recovery_scope=None):
    """No gold is sent to the Agent; scores are written at each turn deadline."""
    output=Path(output)
    validate_attestation(attestation,raw,test_only)
    # Session lock prevents concurrent decision/final reservations consuming
    # the same stage allowance. All protected files are exclusive/append-only.
    with _ledger_lock(Path(str(ledger)+'.session')):
        if output.exists():raise FileExistsError(output)
        caps=authorization_limits(ledger,_rows(ledger))
        journal=JournaledBudgetClient(raw,output/'responses.jsonl',max_requests=caps['calls'],max_total_tokens=caps['tokens'])
        client=MoneyBudgetClient(journal,ledger,attestation,phase,request_journal=output/'requests.jsonl',test_only=test_only)
        client.settle_pending()
        records=records_for() if phase=='confirmation' else development_records()
        agent=TaskPlanEEGAgent(client,records,arm='C',session_id='issue55-session',**protocol()['agent_settings'])
        recovery_context=None
        if recovery_scope is not None:
            if recovery_scope!=recovery.SCOPE:raise StageBudgetExhausted('Unknown recovery scope')
            rows=_rows(Path(ledger));p=recovery.policy(rows)
            if not p:raise StageBudgetExhausted('Register reviewed recovery permission first')
            imported=next((r for r in rows if r.get('event')=='http503_historical_evidence'
                           and r['original_manifest']['case']==case['id']),None)
            recovery_context={'execution_id':imported['recovery']['execution_id'] if imported else str(uuid.uuid4()),
                              'resume_request':imported['request_id'] if imported else None}
            def recovery_state():
                wm=agent.working_memory
                if not wm.graph.nodes and not wm.store.entries and not wm.graph.history and not wm.action_transitions:
                    return 'empty_initial_state'
                return recovery.digest(wm.snapshot())
            client.enable_recovery(recovery_context,recovery_state)
        manifest={'phase':phase,'case':case['id'],'test_only':test_only,
            'candidate':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'protocol_sha256':hashlib.sha256(SPEC.read_bytes()).hexdigest(),
            'data':data_manifest(records),'attestation':attestation,'source':candidate_manifest(),'runtime':actual_settings(raw)}
        with _ledger_lock(Path(ledger)):
            admit_session(Path(ledger),case,phase,manifest,attestation,test_only,recovery_context=recovery_context)
        if recovery_context:manifest['recovery']={**recovery_context,'scope_id':recovery.SCOPE}
        output.mkdir(parents=True)
        write_new(output/'manifest.json',manifest)
        case=scored_case(case,phase)
        results=[]
        def scientific_guard():
            store=agent.working_memory.store
            problems=[{'kind':'numeric_oracle','row':r} for r in audit_entries(store) if not r['passed']]
            # Gold measures delivery, not which route is allowed. Observe all
            # actual entries, including metadata and intermediate artifacts.
            for entry in store.entries:
                spec=store.contexts[entry.record].executor.registry.get(entry.capability)
                expected_time='event_relative' if spec.consumes_artifact or spec.produces_artifact else 'record_absolute'
                observation=entry.tool_trace[-1]
                actual_scope=store._scientific_scope(entry.capability,observation['request']['arguments'],store.contexts[entry.record])
                if (not store._binding_valid(entry) or entry.evidence['source']!=store.records[entry.record].source or
                    entry.evidence['analysis_configuration']['time_reference']!=expected_time or
                    actual_scope!=entry.parameters or observation['record']!=entry.record):
                    problems.append({'kind':'actual_binding_mismatch','result_id':entry.task_id})
            if problems:
                with _ledger_lock(Path(ledger)):
                    _append(Path(ledger),{'event':'safety_stop','reason':'scientific_execution_mismatch','problems':problems})
                raise LLMServiceError('SCIENTIFIC_SAFETY_STOP','Preserve first wrong execution; stop further calls')
        client.scientific_guard=scientific_guard
        try:
            for turn,request in enumerate(case['requests'],1):
                client.set_context(turn=turn,case_id=case['id'])
                result=agent.run(request) if turn==1 else agent.continue_run(request)
                snapshot=result.to_dict()
                scoring=(score_obligations(case,agent.working_memory.store,turn)
                         if case.get('evaluation_only',{}).get('obligations') else
                         {'numeric':audit_entries(agent.working_memory.store),'whole_request_correct':None,
                          'review_checklist':case.get('evaluation_only',{}).get('checks',[])})
                scoring['review_checklist']=case.get('evaluation_only',{}).get('checks',case.get('evaluation_only',{}).get('review',[]))
                write_new(output/f'turn-{turn}.json',{'user_request':request,'result':snapshot,'score_at_deadline':scoring,
                    'accepted_final_answer':result.final_answer,'cost_upper_bound_usd':str(money_totals(_rows(Path(ledger)),client.rate))})
                results.append(snapshot)
                try:scientific_guard()
                except LLMServiceError:break
                if result.stop_reason not in {'completed','clarification_required','partial'}:break
                if turn<len(case['requests']):
                    decision=followup_decision(case,turn,result,agent.working_memory,scoring)
                    write_new(output/f'followup-{turn}.json',decision)
                    if not decision['allowed']:break
        finally:
            write_new(output/'session-end.json',{'completed_turns':len(results),'usage':dict(raw.total_usage),
                'cost_upper_bound_usd':str(money_totals(_rows(Path(ledger)),client.rate)),
                'phase_usage':_usage(_rows(Path(ledger)),lambda c:c.get('phase')==phase)})
            if recovery_context:
                with _ledger_lock(Path(ledger)):
                    _append(Path(ledger),{'event':'recovery_session_finished',**recovery_context,
                        'case':case['id'],'turns':len(results),'stops':[r['stop_reason'] for r in results]})
        return results


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--real',action='store_true')
    mode.add_argument('--initialize-ledger',action='store_true')
    mode.add_argument('--apply-authorization',type=Path)
    mode.add_argument('--register-http503-recovery',action='store_true')
    p.add_argument('--ledger',type=Path,required=True)
    p.add_argument('--attestation',type=Path,required=True)
    p.add_argument('--reconciliation',type=Path)
    p.add_argument('--phase',choices=LIMITS)
    p.add_argument('--case')
    p.add_argument('--output',type=Path)
    p.add_argument('--recovery-scope',choices=[recovery.SCOPE])
    p.add_argument('--recovery-baseline',type=Path)
    p.add_argument('--original-output',type=Path)
    args=p.parse_args(argv)
    a=json.loads(args.attestation.read_text(encoding='utf8'))
    if a.get('test_only') is not False:p.error('Test attestation cannot authorize a real request')
    if args.apply_authorization:
        raw=OpenAICompatibleClient.from_env()
        apply_authorization_revision(raw,args.ledger,a,json.loads(args.apply_authorization.read_text(encoding='utf8')))
        return
    if args.register_http503_recovery:
        if not args.recovery_baseline or not args.original_output:p.error('Recovery requires frozen baseline and original failed output')
        register_http503_recovery(OpenAICompatibleClient.from_env(),args.ledger,a,
            baseline=json.loads(args.recovery_baseline.read_text(encoding='utf8')),original_output=args.original_output)
        return
    if args.initialize_ledger:
        if args.reconciliation is None:p.error('Reviewed history reconciliation required')
        raw=OpenAICompatibleClient.from_env()
        raw.max_tokens,raw.max_retries=2200,0
        initialize_ledger(raw,args.ledger,a,args.reconciliation)
        return
    if not all((args.phase,args.case,args.output)):p.error('--real requires phase, case and output')
    if not args.ledger.exists():p.error('Existing reconciled cumulative ledger required')
    cases=protocol()['cases'] if args.phase=='confirmation' else development_cases()
    case=next((c for c in cases if c['id']==args.case),None)
    if not case:p.error('Unknown case for phase')
    raw=OpenAICompatibleClient.from_env()
    raw.max_tokens,raw.max_retries=2200,0
    run_session(raw,args.ledger,a,case,args.output,phase=args.phase,recovery_scope=args.recovery_scope)

if __name__=='__main__':main()
