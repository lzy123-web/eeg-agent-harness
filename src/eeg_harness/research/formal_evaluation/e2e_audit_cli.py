"""Audit an immutable real-LLM evaluation report."""

import argparse
import json
from pathlib import Path

from .e2e_audit import audit_recorded_report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = json.loads(args.input.read_text(encoding="utf-8"))
    audit = audit_recorded_report(report)
    args.output.write_text(json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False),
                           encoding="utf-8")
    print(json.dumps(audit["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
