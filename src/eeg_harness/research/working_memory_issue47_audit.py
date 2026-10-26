"""Read-only posthoc audit of Issue47 synthetic logs; never calls a model.

Checks every requested power band (including C2 event power), independently
from raw synthetic samples. Numerical agreement is not task completion or
authorization. This module is not imported by the Agent or its context builder.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

import numpy as np

from .task_memory_v2 import independent_oracle
from .working_memory_issue47 import ROOT, SPEC, records_for


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_audit(root=ROOT):
    root = Path(root)
    rows = [json.loads(s) for s in (root / "budget.jsonl").read_text(encoding="utf8").splitlines()]
    starts = {r["request_id"]: r for r in rows if r["event"] == "reserved"}
    ends = {r["request_id"]: r for r in rows if r["event"] in {"received", "failed"}}
    costs = defaultdict(lambda: dict(calls=0, tokens=0, input_tokens=0, output_tokens=0))
    for key, start in starts.items():
        end = ends.get(key, {})
        cost = costs[start["context"]["case"]]
        cost["calls"] += 1
        usage = end.get("usage") or {}
        cost["tokens"] += end.get("total_tokens") if end.get("total_tokens") is not None else start["reserved_tokens"]
        cost["input_tokens"] += usage.get("prompt_tokens", 0)
        cost["output_tokens"] += usage.get("completion_tokens", 0)
    turns, checks, hashes = [], [], {}
    for path in sorted(root.glob("*/turn-*.json")):
        run = json.loads(path.read_text(encoding="utf8"))
        development = path.parent.name.startswith("development")
        records = records_for("original" if development else "confirmation")
        actions = run["tool_results"]
        turns.append({"log": path.parent.name + "/" + path.name,
                      "stop_reason": run["stop_reason"], "rounds": run["rounds"],
                      "tool_calls": run["tool_calls"], "final_answer": run["final_answer"],
                      "declared_contracts": [(a.get("data") or {})["contract"] for a in actions
                                             if "contract" in (a.get("data") or {})],
                      "actions": [{"tool": a["tool_name"], "success": a["success"],
                                   "error": (a.get("error") or {}).get("code")} for a in actions]})
        for action in actions:
            obs = (action.get("data") or {}).get("observation")
            if not obs or not obs["result"]["success"]:
                continue
            name, data, params = obs["request"]["name"], obs["result"]["data"], obs["scope"]
            if name in {"psd", "amplitude"}:
                paths = [[c, k] for c in params["channels"]
                         for k in (["rms"] if name == "amplitude" else list(data[c]))]
            elif name == "event_bandpower":
                paths = [["conditions", label, "channels", channel, band]
                         for label, condition in data["conditions"].items()
                         for channel, bands in condition["channels"].items() for band in bands]
            elif name == "epoch_summary":
                paths = [["valid_epoch_count"]]
            else:
                continue
            for field in paths:
                value = data
                for key in field:
                    value = value[key]
                # The established oracle handles one condition at a time.
                scope = dict(params, labels=[field[1]]) if name == "event_bandpower" else params
                expected = independent_oracle(records[obs["record"]], {"capability": name, "parameters": scope}, field)
                actual = float(value)
                checks.append({"log": turns[-1]["log"], "result_id": obs["result_id"],
                               "capability": name, "record": obs["record"], "scope": scope,
                               "source": obs["source"], "path": field, "actual": actual, "oracle": expected,
                               "absolute_error": abs(actual-expected),
                               "rtol": .005 if name in {"amplitude", "psd"} else 1e-6,
                               "atol": 5e-13,
                               "valid": bool(np.isclose(actual, expected,
                                   rtol=.005 if name in {"amplitude", "psd"} else 1e-6, atol=5e-13))})
    for path in sorted(root.glob("**/*.json*")):
        if path.name in {"budget.jsonl", "responses.jsonl", "pre_fix_reproduction.json"} or path.name.startswith("turn-"):
            hashes[path.relative_to(root).as_posix()] = sha(path)
    return {"stage": "issue47", "data": "synthetic only", "protocol_sha256": sha(SPEC),
            "development_code": "f29f139", "confirmation_code": "83e2c00",
            "requested_model": "deepseek-chat",
            "reported_models": dict(Counter(r.get("response_model_reported") for r in ends.values())),
            "ledger_unsettled": len(set(starts)-set(ends)), "costs": dict(costs),
            "total": {k: sum(c[k] for c in costs.values()) for k in ("calls", "tokens", "input_tokens", "output_tokens")},
            "pre_fix": json.loads((root / "pre_fix_reproduction.json").read_text(encoding="utf8")),
            "turns": turns, "numerical_checks": checks, "private_log_hashes": hashes,
            "interpretation": "Posthoc numeric checks only; mixed delivery/continuation and clarification FAILED. Short information request completed. No autonomous historical trajectory restore occurred. Unspecified event window was guessed in the clarification case. No comparative efficacy claim."}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    audit = build_audit()
    with args.output.open("x", encoding="utf8") as f:
        json.dump(audit, f, ensure_ascii=False, allow_nan=False, indent=2)
    print(json.dumps({"budget": audit["total"], "numeric_fields": len(audit["numerical_checks"]),
                      "numeric_pass": all(c["valid"] for c in audit["numerical_checks"]),
                      "unsettled": audit["ledger_unsettled"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
