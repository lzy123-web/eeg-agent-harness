import argparse
import json
from pathlib import Path

from .evidence_evaluation import run_evidence_benchmark


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the frozen evidence-adaptive benchmark")
    parser.add_argument("--suite", default="config/evidence_benchmark_v1.json")
    parser.add_argument("--config", default="config/baseline.json")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    payload = run_evidence_benchmark(args.suite, args.config)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print("Evidence evaluation written")


if __name__ == "__main__":
    main()
