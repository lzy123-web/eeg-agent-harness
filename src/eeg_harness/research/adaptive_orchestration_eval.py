"""Reproducible synthetic scientific oracle and three-arm Issue #32 evaluation."""

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import time

import numpy as np
from scipy.signal import welch

from ..context import ExecutionContext
from ..demo import build_synthetic_event_record, build_synthetic_no_event_record
from ..events import EEGEvent, EventSet
from ..executor import Executor
from ..pipeline import load_config
from ..profiles import EDF_NATIVE
from ..record import EEGRecord
from ..tools import build_default_registry
from .adaptive_orchestration import ScientificTask, run_adaptive
from .adaptive_orchestration_baselines import run_fixed_plan, run_strong_expert
from .integrated_method.v3 import GoalInstance


ARMS = {"adaptive": run_adaptive, "fixed": run_fixed_plan, "strong_expert": run_strong_expert}
CONFIG = load_config(Path(__file__).resolve().parents[3] / "config" / "baseline.json")


@dataclass(frozen=True)
class Case:
    case_id: str
    goals: tuple[GoalInstance, ...]
    minimum: dict
    expected_code: str | None
    data_kind: str = "default"
    forbidden: tuple[str, ...] = ()


def _psd_goal(channel="SYNTH-C1"):
    return GoalInstance("p", "psd", {"channels": [channel], "start": 0, "end": 2})


def _event_goal(label="stimulus"):
    return GoalInstance("e", "event_bandpower", {"labels": [label], "tmin": 0, "tmax": 1})


DEV = (
    Case("D1", (_psd_goal(),), {}, None, "no_events"),
    Case("D2", (_event_goal(),), {"e": 2}, None),
    Case("D3", (_event_goal("control"),), {"e": 2}, "INSUFFICIENT_EVENT_COUNT"),
    Case("D4", (_event_goal(),), {"e": 3}, "INSUFFICIENT_VALID_EPOCHS"),
    Case("D5", (_psd_goal(), _event_goal("control")), {"e": 2}, "INSUFFICIENT_EVENT_COUNT"),
    Case("D6", (_psd_goal(), _event_goal()), {"e": 2}, None),
    Case("D7", (_event_goal(),), {"e": 2}, None, forbidden=("list_events",)),
    Case("D8", (GoalInstance("e", "event_bandpower", {"tmin": 0, "tmax": 1}),),
         {}, "MISSING_EVENT_LABELS"),
    Case("D9", (GoalInstance("m", "seizure_detection", {
        "channels": ["SYNTH-C1"], "start": 0, "end": 1,
    }),), {}, "INCOMPATIBLE_PROFILE"),
)

HOLDOUT = (
    Case("H1", (_psd_goal(), _event_goal("target")), {"e": 3}, None, "three_target"),
    Case("H2", (_event_goal("target"),), {"e": 2}, "EPOCH_CREATION_FAILED", "boundary_target"),
    Case("H3", (_psd_goal(), _event_goal("target")), {"e": 2},
         "INSUFFICIENT_EVENT_COUNT", "no_events"),
    Case("H4", (_psd_goal("ABSENT"), _event_goal("target")), {},
         "INVALID_PARAMETERS", "three_target"),
    Case("H5", (_event_goal("target"),), {"e": 1}, None,
         "two_target", ("list_events",)),
)

# Post-protocol development probe: not a holdout score. It exposes whether an
# atomic multi-scope request commits a consumer before checking every scope.
PROBE = (
    Case("D10-posthoc", (
        GoalInstance("e1", "event_bandpower", {"labels": ["stimulus"], "tmin": 0, "tmax": 1}),
        GoalInstance("e2", "event_bandpower", {"labels": ["control"], "tmin": 0, "tmax": 1}),
    ), {"e1": 2, "e2": 2}, "INSUFFICIENT_EVENT_COUNT"),
)


def _record(kind):
    if kind == "default":
        return build_synthetic_event_record()
    if kind == "no_events":
        return build_synthetic_no_event_record()
    duration = 12 if kind in {"three_target", "two_target"} else 8
    times = np.arange(int(duration * 128), dtype=float) / 128
    data = np.vstack([20e-6 * np.sin(2 * np.pi * 10 * times),
                      15e-6 * np.sin(2 * np.pi * 6 * times)]).astype(np.float32)
    onsets = {"three_target": (2, 4, 6), "two_target": (2, 4),
              "boundary_target": (7.2, 7.7)}[kind]
    events = EventSet(tuple(EEGEvent("target", float(onset)) for onset in onsets),
                      source=f"synthetic://adaptive-{kind}")
    return EEGRecord(data, 128.0, ("SYNTH-C1", "SYNTH-C2"),
                     "synthetic native reference", "synthetic two-channel layout",
                     f"synthetic://adaptive-{kind}",
                     metadata={"profile_id": "edf_native", "is_synthetic": True}, events=events)


def _independent_power(signal, sfreq):
    frequency, density = welch(signal, fs=sfreq, nperseg=min(len(signal), round(sfreq)))
    mask = (frequency >= 8) & (frequency <= 13)
    return float(np.trapz(density[mask], frequency[mask]))


def _oracle(case, record, result):
    """Independent array/time calculation, never consult policy's validator."""
    expected_status = "completed" if case.expected_code is None else "not_completed"
    status_ok = (result["status"] == "completed") == (expected_status == "completed")
    code_ok = result["code"] == case.expected_code
    publication_ok = result["evidence_bundle"]["publication"] == (
        "all_goals" if case.expected_code is None else "none"
    )
    numerical_ok = True
    checks = {}
    if case.expected_code is None:
        by_id = {item["instance_id"]: item for item in result["evidence_bundle"]["goals"]}
        numerical_ok = set(by_id) == {g.instance_id for g in case.goals}
        for goal in case.goals:
            if goal.capability == "psd" and goal.instance_id in by_id:
                channel = record.channel_names.index(goal.parameters["channels"][0])
                a = int(goal.parameters["start"] * record.sfreq)
                b = int(goal.parameters["end"] * record.sfreq)
                expected = "{:.2e}".format(_independent_power(record.data[channel, a:b], record.sfreq))
                observed = by_id[goal.instance_id]["result"][goal.parameters["channels"][0]]["alpha"]
                checks[goal.instance_id] = {"expected_alpha": expected, "observed_alpha": observed}
                numerical_ok &= observed == expected
            if goal.capability == "event_bandpower" and goal.instance_id in by_id:
                label = goal.parameters["labels"][0]
                samples = int(round((goal.parameters["tmax"] - goal.parameters["tmin"]) * record.sfreq))
                values = []
                for event in record.events.events:
                    if event.label != label:
                        continue
                    start = int(round((event.onset_seconds + goal.parameters["tmin"]) * record.sfreq))
                    end = start + samples
                    if start >= 0 and end <= record.data.shape[1]:
                        values.append(_independent_power(record.data[0, start:end], record.sfreq))
                observed = by_id[goal.instance_id]["result"]["conditions"][label]["channels"]["SYNTH-C1"]["alpha"]
                expected = float(np.mean(values))
                checks[goal.instance_id] = {"expected_valid_trials": len(values),
                                            "expected_alpha": expected, "observed_alpha": observed}
                numerical_ok &= len(values) >= case.minimum.get(goal.instance_id, 1)
                numerical_ok &= bool(np.isclose(observed, expected, rtol=1e-6, atol=1e-15))
    forbidden_ok = not any(item["tool_name"] in case.forbidden for item in result["tool_results"])
    global_gate_ok = (case.case_id != "D10-posthoc" or
                      [item["tool_name"] for item in result["tool_results"]] == ["list_events"])
    return {"status_ok": bool(status_ok), "code_ok": bool(code_ok),
            "publication_ok": bool(publication_ok), "numerical_ok": bool(numerical_ok),
            "forbidden_ok": bool(forbidden_ok), "global_gate_ok": bool(global_gate_ok),
            "numeric_checks": checks,
            # Cost/ordering is a separate endpoint, never a scientific failure.
            "all_ok": bool(status_ok and code_ok and publication_ok and numerical_ok and forbidden_ok)}


def evaluate(cases):
    output = []
    for case in cases:
        for arm_name, policy in ARMS.items():
            record = _record(case.data_kind)
            context = ExecutionContext(record, EDF_NATIVE,
                                       Executor(build_default_registry(), CONFIG),
                                       task_id=f"issue32-{case.case_id}-{arm_name}")
            task = ScientificTask(case.goals, case.minimum, case.forbidden)
            started = time.perf_counter()
            result = policy(context, task)
            elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
            oracle = _oracle(case, record, result)
            output.append({"case_id": case.case_id, "arm": arm_name,
                           "expected_code": case.expected_code,
                           "observed_status": result["status"], "observed_code": result["code"],
                           "oracle": oracle,
                           "tool_calls": len(result["tool_results"]),
                           "tool_sequence": [item["tool_name"] for item in result["tool_results"]],
                           "tool_duration_ms": round(sum(item["duration_ms"] for item in result["tool_results"]), 3),
                           "wall_ms": elapsed_ms,
                           "raw_result": result})
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", choices=("dev", "probe", "holdout"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    rows = evaluate({"dev": DEV, "probe": PROBE, "holdout": HOLDOUT}[args.set])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"protocol": "issue32-v1", "split": args.set,
                                       "rows": rows}, indent=2, ensure_ascii=False,
                                      allow_nan=False), encoding="utf-8")
    for arm in ARMS:
        subset = [row for row in rows if row["arm"] == arm]
        print(arm, sum(row["oracle"]["all_ok"] for row in subset), "/", len(subset),
              "calls", sum(row["tool_calls"] for row in subset))
    if not all(row["oracle"]["all_ok"] for row in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
