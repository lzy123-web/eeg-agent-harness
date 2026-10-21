"""Frozen pilot comparison for three planning/execution strategies."""

from dataclasses import dataclass
import json
from pathlib import Path
import time

import mne
import numpy as np

from .context import ExecutionContext
from .events import events_from_mne_raw
from .executor import Executor, _validate_schema
from .pipeline import load_config
from .planning import ConstrainedPlanRunner, StateAwareConstrainedPlanner, TaskSpec
from .profiles import EDF_NATIVE, TUEV_BIPOLAR_22, ProfileValidationError
from .record import EEGRecord
from .tooling import ToolRequest
from .tools import build_default_registry


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    split: str
    variant: str
    expected: str
    task: TaskSpec
    setup: str | None = None


def _task_from_dict(payload, task_id):
    return TaskSpec(
        goal=payload["goal"],
        arguments=payload.get("arguments", {}),
        subtasks=tuple(
            _task_from_dict(item, f"{task_id}-sub{index}")
            for index, item in enumerate(payload.get("subtasks", ()), 1)
        ),
        task_id=task_id,
    )


def load_frozen_suite(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("frozen_before_strategy_results") is not True:
        raise ValueError("Benchmark suite must declare frozen_before_strategy_results")
    cases = tuple(
        BenchmarkCase(
            item["case_id"], item["split"], item["variant"], item["expected"],
            _task_from_dict(item["task"], item["case_id"]), item.get("setup"),
        )
        for item in payload["cases"]
    )
    return payload["suite_version"], cases


def make_synthetic_context(variant, task_id, config):
    profile = TUEV_BIPOLAR_22 if variant.startswith("tuev") else EDF_NATIVE
    sfreq = 128.0 if variant == "tuev_wrong_sfreq" else (profile.target_sfreq or 128.0)
    channels = profile.required_channels or ("C1", "C2")
    samples = int(sfreq * 4)
    times = np.arange(samples) / sfreq
    data = np.vstack([
        np.sin(2 * np.pi * (6 + index % 5) * times)
        for index in range(len(channels))
    ]).astype(np.float32)
    raw = mne.io.RawArray(data, mne.create_info(channels, sfreq, "eeg"), verbose=False)
    if variant != "native_no_events":
        raw.set_annotations(mne.Annotations([1.0, 2.5], [0, 0], ["A", "B"]))
    record = EEGRecord(
        data, sfreq, channels, profile.reference, profile.montage,
        f"synthetic://benchmark/{task_id}",
        metadata={"profile_id": profile.profile_id},
        events=events_from_mne_raw(raw, f"synthetic://benchmark/{task_id}"),
    )
    return ExecutionContext(record, profile, Executor(build_default_registry(), config), task_id)


def _prepare(case, context):
    task = case.task
    if case.setup != "existing_artifact_then_drop":
        return task, False
    created = context.execute(ToolRequest(
        "create_epochs", {"labels": ["A"], "tmin": -0.25, "tmax": 0.75},
        request_id="benchmark-setup",
    ))
    arguments = dict(task.arguments)
    arguments["artifact_id"] = created.data["artifact_id"]
    return TaskSpec(task.goal, arguments, task.subtasks, task.task_id), True


def _policy_payload(status, results, preflight_rejected, duration_ms, replans=0):
    failures = [item for item in results if not item["success"]]
    signatures = [json.dumps([item["tool_name"], item.get("data")], sort_keys=True) for item in results]
    return {
        "status": status,
        "preflight_rejected": preflight_rejected,
        "tool_results": results,
        "tool_calls": len(results),
        "runtime_errors": len(failures),
        "pre_execution_invalid_calls": 0 if preflight_rejected else len(failures),
        "redundant_calls": len(signatures) - len(set(signatures)),
        "replans": replans,
        "duration_ms": duration_ms,
    }


def _direct_tool(task):
    arguments = dict(task.arguments)
    tool_name = arguments.pop("tool_name", None)
    return tool_name, arguments.pop("parameters", arguments)


def _execution_only(task, context, drop_artifact=False):
    started = time.perf_counter()
    results = []
    if drop_artifact:
        context.artifacts.clear()

    def invoke(current):
        if current.goal == "tool":
            name, arguments = _direct_tool(current)
        elif current.goal == "event_bandpower":
            name = "event_bandpower"
            arguments = {"artifact_id": current.arguments.get("artifact_id", "unplanned-artifact")}
        elif current.goal == "sequence":
            for item in current.subtasks:
                invoke(item)
            return
        else:
            name, arguments = current.goal, dict(current.arguments)
        results.append(context.execute(ToolRequest(name, arguments)).to_dict())

    invoke(task)
    status = "completed" if results and all(item["success"] for item in results) else "execution_failed"
    return _policy_payload(status, results, False, round((time.perf_counter() - started) * 1000, 3))


def _expert_preflight_tool(context, name, arguments):
    spec = context.executor.registry.get(name)
    if spec is None or not context.profile.supports_tool(name):
        return False
    try:
        context.profile.validate_record(context.record)
        _validate_schema(arguments, spec.parameters)
        if spec.required_sfreq is not None and context.record.sfreq != spec.required_sfreq:
            return False
        for resource in spec.required_resources:
            path = context.executor.resources.get(resource)
            if not path or not Path(path).expanduser().is_file():
                return False
        if spec.requires_window:
            context.record.slice(arguments["start"], arguments["end"], arguments["channels"])
        if name in ("epoch_summary", "event_bandpower"):
            if arguments["artifact_id"] not in context.artifacts:
                return False
    except (ProfileValidationError, TypeError, ValueError, KeyError):
        return False
    return True


def _expert(task, context, drop_artifact=False):
    started = time.perf_counter()
    results = []

    def reject():
        return _policy_payload("rejected", results, True, round((time.perf_counter() - started) * 1000, 3))

    def run_task(current):
        nonlocal drop_artifact
        if current.goal == "sequence":
            for item in current.subtasks:
                if not run_task(item):
                    return False
            return True
        if current.goal == "tool":
            name, arguments = _direct_tool(current)
            if not _expert_preflight_tool(context, name, arguments):
                return False
            if drop_artifact:
                context.artifacts.clear()
                drop_artifact = False
            results.append(context.execute(ToolRequest(name, arguments)).to_dict())
            return results[-1]["success"]
        if current.goal != "event_bandpower":
            return False
        arguments = dict(current.arguments)
        existing = arguments.get("artifact_id")
        if existing:
            if not _expert_preflight_tool(context, "event_bandpower", {"artifact_id": existing}):
                return False
            if drop_artifact:
                context.artifacts.clear()
                drop_artifact = False
            results.append(context.execute(ToolRequest("event_bandpower", {"artifact_id": existing})).to_dict())
            return results[-1]["success"]
        events = context.record.events
        labels = arguments.get("labels", [])
        if not events or not events.events or not labels or any(label not in events.labels for label in labels):
            return False
        try:
            tmin, tmax = float(arguments["tmin"]), float(arguments["tmax"])
            if tmax - tmin < 1 or tmin >= tmax:
                return False
            baseline = arguments.get("baseline")
            if baseline is not None:
                start = tmin if baseline[0] is None else float(baseline[0])
                end = tmax if baseline[1] is None else float(baseline[1])
                if start < tmin or end > tmax or start >= end:
                    return False
        except (KeyError, TypeError, ValueError, IndexError):
            return False
        epoch_args = {"labels": labels, "tmin": tmin, "tmax": tmax}
        if "baseline" in arguments:
            epoch_args["baseline"] = arguments["baseline"]
        created = context.execute(ToolRequest("create_epochs", epoch_args, "expert-create"))
        results.append(created.to_dict())
        if not created.success:
            return False
        results.append(context.execute(ToolRequest(
            "event_bandpower", {"artifact_id": created.data["artifact_id"]}, "expert-power"
        )).to_dict())
        return results[-1]["success"]

    success = run_task(task)
    if success:
        return _policy_payload("completed", results, False, round((time.perf_counter() - started) * 1000, 3))
    if results and any(not item["success"] for item in results):
        return _policy_payload("execution_failed", results, False, round((time.perf_counter() - started) * 1000, 3))
    return reject()


def _planner(task, context, drop_artifact=False, max_replans=1):
    runner = ConstrainedPlanRunner(context, max_replans=max_replans)
    plan = runner.planner.plan(task)
    if drop_artifact:
        context.artifacts.clear()
    result = runner.execute_plan(task, plan)
    payload = result.to_dict()
    return _policy_payload(
        result.status,
        list(payload["tool_results"]),
        result.status == "rejected",
        result.duration_ms,
        result.replans,
    )


def _blind_dependency(task, context, drop_artifact=False):
    """Ablation: dependency templates without state-aware preflight."""
    if task.goal != "event_bandpower":
        return _execution_only(task, context, drop_artifact)
    started = time.perf_counter()
    if drop_artifact:
        context.artifacts.clear()
    arguments = dict(task.arguments)
    if arguments.get("artifact_id"):
        result = context.execute(ToolRequest("event_bandpower", {"artifact_id": arguments["artifact_id"]}))
        results = [result.to_dict()]
    else:
        epoch_args = {key: arguments[key] for key in ("labels", "tmin", "tmax", "baseline") if key in arguments}
        created = context.execute(ToolRequest("create_epochs", epoch_args, "blind-create"))
        results = [created.to_dict()]
        if created.success:
            results.append(context.execute(ToolRequest(
                "event_bandpower", {"artifact_id": created.data["artifact_id"]}, "blind-power"
            )).to_dict())
    status = "completed" if all(item["success"] for item in results) else "execution_failed"
    return _policy_payload(status, results, False, round((time.perf_counter() - started) * 1000, 3))


POLICIES = {
    "execution_only": _execution_only,
    "expert_dag": _expert,
    "constrained_planner": _planner,
    "ablation_no_state": _blind_dependency,
    "ablation_no_replanning": lambda task, context, drop=False: _planner(task, context, drop, 0),
    "ablation_parameter_validation_only": _execution_only,
}


def _summarize_rows(rows):
    executable = [row for row in rows if row["expected"] == "complete"]
    rejectable = [row for row in rows if row["expected"] == "reject"]
    return {
        "valid_task_completion_rate": sum(row["status"] == "completed" for row in executable) / len(executable),
        "correct_rejection_rate": sum(row["status"] == "rejected" for row in rejectable) / len(rejectable),
        "pre_execution_invalid_call_rate": sum(row["pre_execution_invalid_calls"] for row in rows) / max(1, sum(row["tool_calls"] for row in rows)),
        "runtime_errors": sum(row["runtime_errors"] for row in rows),
        "tool_calls": sum(row["tool_calls"] for row in rows),
        "mean_duration_ms": sum(row["duration_ms"] for row in rows) / len(rows),
        "redundant_calls": sum(row["redundant_calls"] for row in rows),
        "replans": sum(row["replans"] for row in rows),
    }


def _summarize(outcomes, cases):
    summaries = {}
    for policy in POLICIES:
        rows = [item for item in outcomes if item["policy"] == policy]
        summaries[policy] = _summarize_rows(rows)
    return summaries


def run_benchmark(suite_path, config_path="config/baseline.json"):
    version, cases = load_frozen_suite(suite_path)
    config = load_config(config_path)
    outcomes = []
    for policy_name, policy in POLICIES.items():
        for case in cases:
            context = make_synthetic_context(case.variant, f"{policy_name}-{case.case_id}", config)
            task, drop = _prepare(case, context)
            outcome = policy(task, context, drop)
            outcomes.append({
                "policy": policy_name,
                "case_id": case.case_id,
                "split": case.split,
                "expected": case.expected,
                **{key: value for key, value in outcome.items() if key != "tool_results"},
                "error_codes": [
                    item["error"]["code"] for item in outcome["tool_results"] if item["error"]
                ],
            })
    payload = {
        "suite_version": version,
        "case_count": len(cases),
        "policies": list(POLICIES),
        "summary": _summarize(outcomes, cases),
        "summary_by_split": {
            split: _summarize(
                [item for item in outcomes if item["split"] == split],
                [item for item in cases if item.split == split],
            )
            for split in ("development", "holdout")
        },
        "outcomes": outcomes,
        "interpretation_limits": [
            "synthetic deterministic pilot, not clinical evidence",
            "event bandpower is whole-Epoch Welch power, not ERD/ERS",
            "latency is descriptive and environment-dependent",
        ],
    }
    json.dumps(payload, ensure_ascii=False, allow_nan=False)
    return payload
