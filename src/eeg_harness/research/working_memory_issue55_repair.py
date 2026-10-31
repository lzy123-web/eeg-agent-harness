"""Issue55 repair evidence: controlled decisions, unchanged original requests.

This runner contains evaluator interventions, never passed to a real LLM.
T04 adds the explicit field-reference interface; T07 uses unchanged actions.
"""
import argparse
import hashlib
import json
from pathlib import Path
from .task_memory import PROJECT_ROOT
from .working_memory_issue52 import controlled_steps, run_case, write_new


def repaired_actions(case):
    actions=controlled_steps(case)
    if case=='T04':
        actions[0][2][1]['channel_reference']={
            'source_span':'记录A的SYNTH-C1只分析0到2秒的RMS',
            'target_span':'记录B的同名通道只分析2到4秒的RMS'}
    return actions


def compact_access(log):
    return [{**{k:v for k,v in row.items() if k not in {'dependencies'}},
        **({'presented_payload_sha256':hashlib.sha256(json.dumps(row['dependencies'],sort_keys=True).encode()).hexdigest(),
            'presented_dependency_count':len(row['dependencies'])} if 'dependencies' in row else {})}
        for row in log]


def compact_plan(nodes):
    return [{k:n[k] for k in ('task_id','revision','status','outputs','output_status','unresolved') if k in n}
            for n in nodes]


def report(raw_path):
    before_path=PROJECT_ROOT/'docs/research/evidence/issue52_offline_paired_diagnostic.json'
    before=json.loads(before_path.read_text(encoding='utf8'))
    rows=[run_case(case,arm,actions=repaired_actions(case))
        for case in ('T01','T02','T03','T04','T05','T06','T07','T08')
        for arm in ('A','B','C')]
    write_new(raw_path,{'kind':'controlled_repair_replay_not_autonomy','results':rows})
    public=[]
    for row in rows:
        snapshots=row['raw_agent_results']
        public.append({'case_id':row['case_id'],'arm':row['arm'],
            'requests':row['user_requests_sent'],'record_sha256':row['record_sha256'],
            'stops':row['metrics']['stop_reasons'],'numeric_executions':row['metrics']['numeric_executions'],
            'oracle':row['oracle'],'control_errors':row['metrics']['controlled_errors'],
            'actions':[d['controlled_action'] for d in row['decisions']],
            'evidence_access':compact_access(row['metrics']['read_restore_log']),
            'plans':[compact_plan(s['working_memory']['plan']) for s in snapshots]})
    return {'kind':'public_synthetic_controlled_repair_evidence_not_LLM_success',
        'historical_candidate':'9e5347c63d3fc3ca9add42ea8be68b0abd9b59db',
        'historical_public_sha256':hashlib.sha256(before_path.read_bytes()).hexdigest(),
        'historical_failures_location':'docs/research/evidence/issue52_offline_paired_diagnostic.json#first_failures',
        'external_completions_this_run':0,'api_tokens_this_run':0,
        'raw_sha256':hashlib.sha256(Path(raw_path).read_bytes()).hexdigest(),
        'raw_location':'artifacts/point1_task_memory/issue55/repair-replay-full.json',
        'interface_change':'T04 supplies model-proposed channel_reference with original complete source/target parents. No requested values or ranges changed. T07 actions unchanged.',
        'results':public}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw-output',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    value=report(args.raw_output)
    write_new(args.output,value)
    checks=[c for r in value['results'] for c in r['oracle']]
    print(json.dumps({'paths':len(value['results']),'oracle':len(checks),
        'passed':sum(c['passed'] for c in checks),'external_completions':0}))

if __name__=='__main__':main()
