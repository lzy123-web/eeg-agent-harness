"""Run a structured planning task on deterministic synthetic EEG."""

import argparse
import json
from pathlib import Path

from .pipeline import load_config
from .planning import ConstrainedPlanRunner, TaskSpec
from .planning_evaluation import _task_from_dict, make_synthetic_context, run_benchmark


DEMOS = {
    "window": {
        "goal": "tool",
        "arguments": {
            "tool_name": "psd",
            "parameters": {"channels": ["C1"], "start": 0, "end": 1},
        },
    },
    "event": {
        "goal": "event_bandpower",
        "arguments": {
            "labels": ["A"], "tmin": -0.25, "tmax": 0.75,
            "baseline": [-0.25, 0],
        },
    },
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--demo", choices=sorted(DEMOS))
    source.add_argument("--task", help="JSON TaskSpec file")
    source.add_argument("--benchmark", action="store_true")
    parser.add_argument("--variant", default="native_events")
    parser.add_argument("--config", default="config/baseline.json")
    parser.add_argument("--suite", default="config/planning_benchmark_v1.json")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    if args.benchmark:
        payload = run_benchmark(args.suite, args.config)
    else:
        task_payload = DEMOS[args.demo] if args.demo else json.loads(
            Path(args.task).read_text(encoding="utf-8")
        )
        task = _task_from_dict(task_payload, "plan-cli-task")
        context = make_synthetic_context(
            args.variant, "plan-cli-context", load_config(args.config)
        )
        result = ConstrainedPlanRunner(context).run(task)
        payload = {
            "input_kind": "deterministic_synthetic",
            "task": task.to_dict(),
            "result": result.to_dict(),
            "reproducibility": context.reproducibility_bundle(),
        }
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    print("Planning result written")


if __name__ == "__main__":
    main()
