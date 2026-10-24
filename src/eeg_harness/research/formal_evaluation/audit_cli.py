"""Audit a frozen formal-evaluation result without changing its primary score."""

import argparse
import json
from pathlib import Path

from .invariant_audit import audit_report
from .protocol import load_cases


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = json.loads(args.input.read_text(encoding="utf-8"))
    protocol, _ = load_cases()
    audit = audit_report(report, protocol["cases"])
    args.output.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "protocol_invalid_cases": audit["protocol_invalid_cases"],
        "valid_rows": audit["valid_rows"],
        "valid_rows_passing_all_audited_invariants":
            audit["valid_rows_passing_all_audited_invariants"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
