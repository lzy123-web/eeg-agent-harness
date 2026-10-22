import argparse
import json
from pathlib import Path

from .evaluation import run_evaluation


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run frozen EEG semantic-planning pilot")
    parser.add_argument("--suite", default="config/point1_semantic_planning_v1.json")
    parser.add_argument("--output")
    parser.add_argument("--demo", choices=("branch", "events"))
    args = parser.parse_args(argv)
    result = run_evaluation(args.suite)
    if args.demo:
        wanted = "dev_line_two_branches" if args.demo == "branch" else "dev_event_feature_chain"
        result = {
            "demo": args.demo,
            "cases": [row for row in result["cases"] if row["case_id"] == wanted],
        }
    text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
        print(f"Semantic planning result written to {path}")
    else:
        print(text)


if __name__ == "__main__":
    main()
