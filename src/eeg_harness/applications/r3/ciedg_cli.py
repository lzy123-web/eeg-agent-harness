"""Offline, fixed-subset R3 application validation for the frozen CIEDG core."""

import argparse
import json
import os
from pathlib import Path

from ...pipeline import load_config
from .ciedg import application_config_snapshot, load_application_config
from .ciedg_validation import select_fixed_subset, validate_one_edf


PROJECT_ROOT = Path(__file__).resolve().parents[4]
PRIVATE_OUTPUT_ROOT = PROJECT_ROOT / "r3_outputs"


def _private_destination(value):
    destination = Path(value).expanduser().resolve()
    if not destination.is_relative_to(PRIVATE_OUTPUT_ROOT.resolve()):
        raise ValueError("Detailed R3 output must be inside the ignored r3_outputs directory")
    return destination


def _save_local(destination, payload):
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", default=os.environ.get("EEG_HARNESS_R3_DATA_ROOT"))
    parser.add_argument("--config", default=str(PROJECT_ROOT / "config" / "baseline.json"))
    parser.add_argument(
        "--application-config", default=str(PROJECT_ROOT / "config" / "r3_ciedg.example.json"),
    )
    parser.add_argument("--output", default=str(PRIVATE_OUTPUT_ROOT / "issue24_local_validation.json"))
    args = parser.parse_args(argv)
    if not args.data_root:
        parser.error("Provide --data-root or EEG_HARNESS_R3_DATA_ROOT")
    rules, tasks = load_application_config(args.application_config)
    if tasks != ("event_summary", "quality_bandpower"):
        parser.error("This fixed validation requires event_summary and quality_bandpower in that order")
    destination = _private_destination(args.output)
    selected, inventory = select_fixed_subset(args.data_root)
    if len(selected) != 4:
        parser.error("Fixed validation requires two EDFs in each of two storage partitions")
    payload = {
        "protocol": "issue24_fixed_two_per_two_sorted_storage_partitions_v1",
        "inventory": inventory,
        "application_config": application_config_snapshot(rules, tasks),
        "records": [],
    }
    config = load_config(args.config)
    for path in selected:
        try:
            result = validate_one_edf(path, config, rules)
        except Exception as exc:
            # The full path and exception remain only in the ignored local report.
            result = {
                "status": "failed",
                "resource": {"local_path": str(path.resolve())},
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }
        payload["records"].append(result)
        _save_local(destination, payload)
    passed = sum(item["status"] == "passed" for item in payload["records"])
    print(json.dumps({
        "tested": len(payload["records"]), "passed": passed,
        "failed": len(payload["records"]) - passed,
        "detailed_results_private": True,
    }, ensure_ascii=False))
    return 0 if passed == len(payload["records"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
