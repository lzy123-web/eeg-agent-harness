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

from ..llm import OpenAICompatibleClient, LLMServiceError
from ..task_plan_agent import TaskPlanEEGAgent
from .working_memory_issue50 import Issue50Client
from .working_memory_issue51 import _usage
from .task_memory_issue39_budget import _append, _rows, _ledger_lock, StageBudgetExhausted
from .integrated_method.v2_validation import JournaledBudgetClient
from .working_memory_issue55 import protocol, records_for, score_obligations, data_manifest, SPEC
from .working_memory_issue52 import write_new, encoded, protocol as development_protocol, records_for as development_records, audit_entries
from .task_memory import PROJECT_ROOT

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
AUTHORIZATION_CHAIN=((REVISION_ID,ADDITIONAL_GRANT,ORIGINAL_CAPS,REVISED_CAPS,48),
                     (LIVE_REVISION,LIVE_GRANT,REVISED_CAPS,LIVE_CAPS,125))


def authorization_limits(ledger,rows):
    """Only the two explicit reviewed grants, in order, over immutable prefixes."""
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
        if ident==LIVE_REVISION and not r['test_only'] and (r['prefix_sha256']!=LIVE_PREFIX
                or r['prior_usage']!=[125,1234297] or Decimal(r['prior_usd'])!=Decimal('0.4054206')):
            raise StageBudgetExhausted('Issue58 reviewed original snapshot changed')
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
            if ident==LIVE_REVISION and not test_only and digest!=LIVE_PREFIX:
                raise StageBudgetExhausted('Require the reviewed 125-call Issue58 prefix')
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


def admit_session(ledger,case,phase,manifest,attestation,test_only):
    rows=_rows(ledger)
    caps=authorization_limits(ledger,rows)
    if caps!=ORIGINAL_CAPS and phase!='development':
        raise StageBudgetExhausted('Additional authorization forbids confirmation in this stage')
    starts=[r for r in rows if r.get('event')=='session_started']
    if any(r.get('event') in {'safety_stop','stage_closed'} for r in rows):
        raise StageBudgetExhausted('Stage stopped; audit existing evidence')
    if not test_only:
        gate=attestation.get('mechanism_gate',{})
        if (gate.get('status')!='passed' or gate.get('source_sha256')!=manifest['source']['sha256']
                or not gate.get('evidence_sha256')):
            raise StageBudgetExhausted('Mechanism regression gate must pass for this exact source before payment')
        expected=protocol()['cases'] if phase=='confirmation' else development_protocol()['cases']
        if case not in expected:
            raise StageBudgetExhausted('Use original protocol requests, not a substituted case')
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
        reconciliation=next((r for r in reversed(rows) if r.get('event')=='issue55_reconciled'),rows[0])
        if reconciliation.get('grant')!=GRANT or reconciliation.get('reconciled') is not True:
            raise StageBudgetExhausted('Cumulative calls/tokens/fees must be reconciled to the existing grant')
        if reconciliation.get('rate_ceiling')!=str(self.rate):
            raise StageBudgetExhausted('Ledger rate ceiling differs; audit migration, do not reset')
        if any(r.get('event')=='stage_closed' for r in rows):
            raise StageBudgetExhausted('Closed stage cannot reopen')
        self.caps=authorization_limits(self.ledger,rows)
        amendment=next((r for r in reversed(rows) if r.get('event')=='authorization_revised'),None)
        self.stage_money_start=Decimal(amendment['prior_usd']) if amendment else Decimal('0')
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
        self.settle_pending()

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

    def _fits(self,rows,calls,tokens):
        if any(r.get('event') in {'stage_closed','safety_stop'} for r in rows):return False
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
        if any(r.get('event')=='safety_stop' for r in _rows(self.ledger)):
            raise LLMServiceError('STAGE_BUDGET_EXHAUSTED','Unexpected response model or invalid usage; stop and audit')
        return response


def run_session(raw,ledger,attestation,case,output,*,phase='development',test_only=False):
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
        manifest={'phase':phase,'case':case['id'],'test_only':test_only,
            'candidate':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'protocol_sha256':hashlib.sha256(SPEC.read_bytes()).hexdigest(),
            'data':data_manifest(records),'attestation':attestation,'source':candidate_manifest(),'runtime':actual_settings(raw)}
        admit_session(Path(ledger),case,phase,manifest,attestation,test_only)
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
        return results


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--real',action='store_true')
    mode.add_argument('--initialize-ledger',action='store_true')
    mode.add_argument('--apply-authorization',type=Path)
    p.add_argument('--ledger',type=Path,required=True)
    p.add_argument('--attestation',type=Path,required=True)
    p.add_argument('--reconciliation',type=Path)
    p.add_argument('--phase',choices=LIMITS)
    p.add_argument('--case')
    p.add_argument('--output',type=Path)
    args=p.parse_args(argv)
    a=json.loads(args.attestation.read_text(encoding='utf8'))
    if a.get('test_only') is not False:p.error('Test attestation cannot authorize a real request')
    if args.apply_authorization:
        raw=OpenAICompatibleClient.from_env()
        apply_authorization_revision(raw,args.ledger,a,json.loads(args.apply_authorization.read_text(encoding='utf8')))
        return
    if args.initialize_ledger:
        if args.reconciliation is None:p.error('Reviewed history reconciliation required')
        raw=OpenAICompatibleClient.from_env()
        raw.max_tokens,raw.max_retries=2200,0
        initialize_ledger(raw,args.ledger,a,args.reconciliation)
        return
    if not all((args.phase,args.case,args.output)):p.error('--real requires phase, case and output')
    if not args.ledger.exists():p.error('Existing reconciled cumulative ledger required')
    cases=protocol()['cases'] if args.phase=='confirmation' else development_protocol()['cases']
    case=next((c for c in cases if c['id']==args.case),None)
    if not case:p.error('Unknown case for phase')
    raw=OpenAICompatibleClient.from_env()
    raw.max_tokens,raw.max_retries=2200,0
    run_session(raw,args.ledger,a,case,args.output,phase=args.phase)

if __name__=='__main__':main()
