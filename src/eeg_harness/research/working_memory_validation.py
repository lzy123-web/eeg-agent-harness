"""Input/after-run numerical audit only; no method actions or gold in Agent input."""

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json

import numpy as np

from ..events import EventSet
from ..working_memory_cli import PRIVATE, LEDGER, budgeted_client, run_requests
from .task_memory import PROJECT_ROOT, synthetic_records
from .task_memory_v2 import independent_oracle
from .task_memory_issue39_budget import ledger_totals


SPEC = PROJECT_ROOT / "config" / "point1_working_memory_issue45.json"


def records_for(kind):
    records = synthetic_records()
    if kind == "renamed":
        for key, record in records.items():
            mapping = {"stimulus": "pulse" if key == "A" else "click", "control": "quiet"}
            events = EventSet(tuple(replace(e, label=mapping[e.label]) for e in record.events.events),
                              f"synthetic://issue45-confirm-{key}-events")
            records[key] = replace(record, events=events, data=record.data * 1.13,
                                    source=f"synthetic://issue45-confirm-{key}")
    return records


def audit_entries(store):
    rows = []
    for entry in store.entries:
        if entry.capability == "psd":
            path = [entry.parameters["channels"][0], "alpha"]
        elif entry.capability == "amplitude":
            path = [entry.parameters["channels"][0], "rms"]
        elif entry.capability == "event_bandpower":
            path = ["conditions", entry.parameters["labels"][0], "channels", "SYNTH-C1", "alpha"]
        elif entry.capability == "epoch_summary":
            path = ["valid_epoch_count"]
        else:
            continue
        observed = entry.result
        for key in path:
            observed = observed[key]
        expected = independent_oracle(store.records[entry.record], {
            "capability": entry.capability, "parameters": entry.parameters}, path)
        rows.append({"task_id": entry.task_id, "record": entry.record,
                     "capability": entry.capability, "parameters": entry.parameters,
                     "revision_of": entry.revision_of, "path": path,
                     "actual": observed, "oracle": expected,
                     "numerically_valid": bool(np.isclose(float(observed), expected,
                         rtol=.005 if entry.capability in {"psd", "amplitude"} else 1e-6, atol=5e-13))})
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("development", "confirmation", "bounded_confirmation"), required=True)
    parser.add_argument("--real", required=True, action="store_true")
    args = parser.parse_args(argv)
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    client = budgeted_client(args.phase, phase_cap=36 if args.phase == "development" else 10)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    report = {"phase": args.phase, "protocol_sha256": hashlib.sha256(SPEC.read_bytes()).hexdigest(), "sessions": []}
    for case in spec[args.phase]:
        session = f"{args.phase}-{stamp}-{case['name']}"
        agent, results = run_requests(case["requests"], client, records=records_for(case["records"]), session_id=session)
        report["sessions"].append({"session": session, "requests": case["requests"],
                                   "outcomes": [{k: r[k] for k in ("stop_reason", "rounds", "final_answer")} for r in results],
                                   "numeric_audit": audit_entries(agent.working_memory.store),
                                   "events": agent.working_memory.store.events})
        if results and results[-1]["stop_reason"] in {"llm_error", "no_progress"}:
            break
    report["budget"] = ledger_totals(LEDGER)
    path = PRIVATE / f"{args.phase}-{stamp}-audit.json"
    with path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, allow_nan=False, indent=2)
    print(json.dumps({"audit_file": path.name, "budget": report["budget"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
