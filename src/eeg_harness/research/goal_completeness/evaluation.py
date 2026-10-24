"""Offline evaluation for controlled EEG source-claim coverage."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .matcher import compare_contracts
from .models import ScientificContract
from .protocol import load_protocol, parse_controlled_request


FAULT_TO_ISSUE = {
    "omit_operation": "missing_operation",
    "authorization_conflict": "authorization_conflict",
    "stage_conflict": "stage_conflict",
    "relation_missing": "missing_relation",
    "extra_operation": "extra_operation",
}


def _semantic_dict(contract: ScientificContract) -> dict[str, Any]:
    payload = contract.to_dict(include_evidence=False)
    payload.pop("metadata", None)
    return payload


def evaluate_protocol(path: Path) -> dict[str, Any]:
    protocol, digest = load_protocol(path)
    rows = []
    parser_exact = 0
    oracle_primary_detected = 0
    controlled_primary_detected = 0
    exact_disposition_correct = 0
    exact_accept_total = 0
    exact_accept_false_clarify = 0
    fault_counts = Counter()
    for case in protocol["cases"]:
        gold = ScientificContract.from_dict(case["source_contract"])
        parsed = parse_controlled_request(case["request"])
        parser_ok = _semantic_dict(gold) == _semantic_dict(parsed)
        parser_exact += int(parser_ok)
        for candidate_spec in case["candidates"]:
            candidate = ScientificContract.from_dict(candidate_spec["contract"])
            oracle_report = compare_contracts(gold, candidate)
            controlled_report = compare_contracts(parsed, candidate)
            fault = candidate_spec["fault_type"]
            expected_primary = FAULT_TO_ISSUE.get(fault)
            oracle_detected = (
                expected_primary is None or expected_primary in oracle_report.issue_types())
            controlled_detected = (
                expected_primary is None or expected_primary in controlled_report.issue_types())
            if expected_primary is not None:
                fault_counts[fault] += 1
                oracle_primary_detected += int(oracle_detected)
                controlled_primary_detected += int(controlled_detected)
            else:
                exact_disposition_correct += int(
                    oracle_report.disposition == gold.expected_disposition
                    and controlled_report.disposition == gold.expected_disposition)
                if gold.expected_disposition == "accept":
                    exact_accept_total += 1
                    exact_accept_false_clarify += int(
                        controlled_report.disposition != "accept")
            rows.append({
                "case_id": case["id"],
                "split": case["split"],
                "language": case["language"],
                "template_family": case["template_family"],
                "candidate_id": candidate_spec["id"],
                "fault_type": fault,
                "expected_primary_issue": expected_primary,
                "parser_exact": parser_ok,
                "oracle_primary_detected": oracle_detected,
                "controlled_primary_detected": controlled_detected,
                "oracle": oracle_report.to_dict(),
                "controlled_parser": controlled_report.to_dict(),
            })

    fault_total = sum(fault_counts.values())
    case_total = len(protocol["cases"])
    result = {
        "experiment": "eeg_goal_completeness_no_annotator_pilot_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol_sha256": digest,
        "seed": protocol["seed"],
        "scope_label": "controlled synthetic, not independently annotated real NL",
        "uses_llm": False,
        "uses_eeg_waveforms": False,
        "summary": {
            "controlled_requests": case_total,
            "development_requests": sum(c["split"] == "development" for c in protocol["cases"]),
            "holdout_requests": sum(c["split"] == "holdout" for c in protocol["cases"]),
            "candidate_pairs": len(rows),
            "fault_pairs": fault_total,
            "parser_contract_exact": parser_exact,
            "oracle_primary_fault_detected": oracle_primary_detected,
            "controlled_primary_fault_detected": controlled_primary_detected,
            "exact_candidate_disposition_correct": exact_disposition_correct,
            "exact_accept_total": exact_accept_total,
            "exact_accept_false_clarify": exact_accept_false_clarify,
            "fault_type_counts": dict(sorted(fault_counts.items())),
        },
        "validity": {
            "demonstrates": [
                "frozen controlled grammar round-trip consistency",
                "typed matcher detection on known structured perturbations",
                "JSON-serializable auditable diagnostics",
            ],
            "does_not_demonstrate": [
                "free natural-language source extraction",
                "independent human annotation agreement",
                "ESOCC superiority over a strong semantic parser",
                "real-user or real-EEG generalization",
            ],
        },
        "cases": rows,
    }
    json.dumps(result, ensure_ascii=False, allow_nan=False)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=Path(
        "config/eeg_goal_completeness_cases_v1.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = evaluate_protocol(args.protocol)
    text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
