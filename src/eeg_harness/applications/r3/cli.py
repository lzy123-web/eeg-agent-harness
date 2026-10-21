"""Local, de-identified R3 resource diagnostic."""

import argparse
import json
import os
from pathlib import Path

from .adapter import diagnose_r3_files


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        default=os.environ.get("EEG_HARNESS_R3_DATA_ROOT"),
        help="Local root containing R3 EDF resources (or EEG_HARNESS_R3_DATA_ROOT)",
    )
    args = parser.parse_args(argv)
    if not args.data_root:
        parser.error("Provide --data-root or EEG_HARNESS_R3_DATA_ROOT")
    files = sorted(Path(args.data_root).expanduser().rglob("*.edf"))
    print(json.dumps(diagnose_r3_files(files), ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
