"""Issue #34 frozen synthetic cross-task evaluation; no candidate method changes."""

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import time

import numpy as np
from scipy.signal import welch

from ..agent import EEGAgent
from ..context import ExecutionContext
from ..demo import (build_synthetic_event_record, build_synthetic_no_event_record,
                    build_synthetic_tuev_record)
from ..events import EEGEvent, EventSet
from ..executor import Executor
from ..llm import OpenAICompatibleClient
from ..pipeline import load_config
from ..profiles import EDF_NATIVE, TUEV_BIPOLAR_22
from ..tooling import ToolRegistry, ToolRequest
from ..tools import build_default_registry
from .integrated_method.v2_validation import JournaledBudgetClient, PRIVATE_ROOT, PROJECT_ROOT
from .integrated_method.v3 import GoalInstance, InstanceTaskRequest, run_instances
from .integrated_method.v3_agent import InstanceGoalEEGAgent


PROTOCOL = PROJECT_ROOT / "config" / "point1_composition_protocol_v1.json"
CONFIG = PROJECT_ROOT / "config" / "baseline.json"
MODEL_RESOURCE = (PROJECT_ROOT.parent / "EEGAgent-main" / "EEGAgent-main" / "tools"
                  / "localModels" / "seiz&normal.pth")
EVENT_GOALS = frozenset({"epoch_summary", "epoch_quality", "event_bandpower"})
PRIVATE_DIR = PRIVATE_ROOT / "point1_composition"


def load_protocol():
    return json.loads(PROTOCOL.read_text(encoding="utf-8"))


def build_fixture(name):
    if name == "native_no_events":
        return build_synthetic_no_event_record(), EDF_NATIVE
    if name == "bipolar_22":
        return build_synthetic_tuev_record(), TUEV_BIPOLAR_22
    record = build_synthetic_event_record()
    if name == "native_events":
        return record, EDF_NATIVE
    if name == "native_events_alt":
        events = (("target", 1.5), ("target", 3.5), ("control", 5.5))
    elif name == "native_events_edge":
        events = (("late", 7.6),)
    else:
        raise ValueError("Unknown frozen fixture")
    return replace(record, events=EventSet(tuple(
        EEGEvent(label, onset, source_index=index)
        for index, (label, onset) in enumerate(events)
    ), "synthetic://issue34-frozen-events")), EDF_NATIVE


def new_context(case, arm):
    record, profile = build_fixture(case["fixture"])
    resources = {"seizure_model": str(MODEL_RESOURCE)} if MODEL_RESOURCE.is_file() else {}
    return ExecutionContext(record, profile,
                            Executor(build_default_registry(), load_config(CONFIG), resources),
                            f"issue34-{arm}-{case['id']}")


def _goal_key(name, parameters):
    return name, json.dumps(parameters, sort_keys=True, ensure_ascii=False)


def _result_goals(result):
    return [_goal_key(item["capability"], item["parameters"])
            for item in result.get("evidence_bundle", {}).get("goals", [])]


def _gold_goals(case):
    return [_goal_key(item["capability"], item["parameters"]) for item in case["gold"]]


def _oracle_value(record, name, parameters, config):
    if name == "amplitude":
        data = record.slice(parameters["start"], parameters["end"], parameters["channels"])
        return {channel: {"mean_abs": float(np.mean(np.abs(values))),
                          "rms": float(np.sqrt(np.mean(np.square(values)))),
                          "max_val": float(np.max(values)), "min_val": float(np.min(values))}
                for channel, values in zip(parameters["channels"], data)}
    if name == "psd":
        data = record.slice(parameters["start"], parameters["end"], parameters["channels"])
        return {channel: _bands(values, record.sfreq, config)
                for channel, values in zip(parameters["channels"], data)}
    if name in EVENT_GOALS:
        selected = [event for event in record.events.events
                    if event.label in parameters["labels"]] if record.events else []
        samples = int(round((parameters["tmax"] - parameters["tmin"]) * record.sfreq))
        grouped = {}
        for event in selected:
            start = int(round((event.onset_seconds + parameters["tmin"]) * record.sfreq))
            end = start + samples
            if start < 0 or end > record.data.shape[1]:
                continue
            grouped.setdefault(event.label, []).append(record.data[:, start:end])
        if name == "epoch_summary":
            return {"valid_epoch_count": sum(map(len, grouped.values())),
                    "rejected_epoch_count": len(selected) - sum(map(len, grouped.values()))}
        if name == "event_bandpower":
            return {label: {channel: {band: float(np.mean([
                _bands(epoch[index], record.sfreq, config)[band] for epoch in epochs]))
                for band in config["freq_bands"]}
                for index, channel in enumerate(record.channel_names)}
                for label, epochs in grouped.items()}
    return None


def _bands(values, sfreq, config):
    frequency, density = welch(values, fs=sfreq, nperseg=min(len(values), int(round(sfreq))))
    return {name: float(np.trapz(density[(frequency >= low) & (frequency <= high)],
                                frequency[(frequency >= low) & (frequency <= high)]))
            for name, (low, high) in config["freq_bands"].items()}


def _numerical_check(record, name, parameters, data, config):
    oracle = _oracle_value(record, name, parameters, config)
    if oracle is None:
        if name == "seizure_detection":
            valid = (isinstance(data, list) and len(data) ==
                     int(parameters["end"] - parameters["start"]))
            for item in data if isinstance(data, list) else []:
                for channel in parameters["channels"]:
                    scores = item.get(channel, {})
                    valid = valid and set(scores) == {"Non-seiz", "seiz"}
                    valid = valid and all(np.isfinite(float(value)) for value in scores.values())
            return bool(valid), "one_second_shape_and_finite_scores_only"
        return True, "structural_only"
    if name == "epoch_summary":
        return all(data.get(key) == value for key, value in oracle.items()), "independent_epoch_count"
    if name == "event_bandpower":
        actual = {label: item["channels"] for label, item in data.get("conditions", {}).items()}
    else:
        actual = data
    try:
        for outer, channels in oracle.items():
            for inner, measures in channels.items():
                observed = actual[outer][inner]
                if isinstance(measures, dict):
                    for key, value in measures.items():
                        if not np.isclose(float(observed[key]), value, rtol=5e-3, atol=5e-13):
                            return False, f"numeric_mismatch:{outer}:{inner}:{key}"
                elif not np.isclose(float(observed), measures, rtol=5e-3, atol=5e-13):
                    return False, f"numeric_mismatch:{outer}:{inner}"
    except (KeyError, TypeError, ValueError):
        return False, "numeric_shape_mismatch"
    return True, "independent_numeric_oracle"


def score_candidate(case, context, result):
    expected = case["expected"]
    completed = result["status"] == "completed"
    should_complete = expected == "complete" or (expected == "complete_if_resource_available"
                                                   and MODEL_RESOURCE.is_file())
    goal_match = sorted(_result_goals(result)) == sorted(_gold_goals(case)) if should_complete else None
    forbidden = [item for item in result.get("tool_results", [])
                 if item.get("tool_name") in case["forbid"]]
    numeric = []
    for item in result.get("evidence_bundle", {}).get("goals", []):
        valid, reason = _numerical_check(context.record, item["capability"],
                                         item["parameters"], item["result"],
                                         context.executor.config)
        numeric.append({"goal": item["instance_id"], "valid": valid, "oracle": reason})
    if should_complete:
        pass_case = completed and goal_match and not forbidden and all(x["valid"] for x in numeric)
    else:
        pass_case = (not completed and not forbidden and
                     not result.get("evidence_bundle", {}).get("goals"))
    return {"pass": bool(pass_case), "expected": expected, "status": result["status"],
            "goal_match": goal_match, "forbidden_calls": [x["tool_name"] for x in forbidden],
            "numeric_oracles": numeric, "tool_count": len(result.get("tool_results", []))}


def run_expert(case):
    """Independent conditional recipe over declared goals, not v3 graph/executor clone."""
    context = new_context(case, "expert")
    record = context.record
    log = []
    if not case["gold"]:
        # A typed planner cannot infer an omitted NL target from an empty gold
        # list. These intent-stop cases have no conditional expert score.
        return {"status": "not_assessed_no_structured_goal", "tool_results": log}

    def call(name, parameters):
        output = context.execute(ToolRequest(name, parameters, f"expert-{len(log) + 1}"))
        log.append({"tool_name": name, "arguments": parameters, "success": output.success,
                    "error_code": output.error_code, "data": output.data})
        return output

    # Atomically preflight the same visible scientific facts before data-producing work.
    for goal in case["gold"]:
        name, parameters = goal["capability"], goal["parameters"]
        spec = context.executor.registry.get(name)
        if (spec is None or not context.profile.supports_tool(name)
                or "*" not in spec.compatible_profiles
                and context.profile.profile_id not in spec.compatible_profiles):
            return {"status": "safe_stop_profile_incompatible", "tool_results": log}
        if name == "seizure_detection" and not MODEL_RESOURCE.is_file():
            return {"status": "safe_stop_missing_resource", "tool_results": log}
        if name in EVENT_GOALS and record.events is None:
            return {"status": "safe_stop_no_events", "tool_results": log}
        if name in {"psd", "amplitude", "seizure_detection"}:
            try:
                record.slice(parameters["start"], parameters["end"], parameters["channels"])
            except ValueError:
                return {"status": "safe_stop_invalid_window", "tool_results": log}
    outputs, artifacts = [], {}
    scopes = {_goal_key("epoch", goal["parameters"]) for goal in case["gold"]
              if goal["capability"] in EVENT_GOALS}
    if scopes:
        inventory = call("list_events", {})
        if not inventory.success:
            return {"status": "safe_stop_event_inventory_failure", "tool_results": log}
        for _, encoded in sorted(scopes):
            parameters = json.loads(encoded)
            if any(inventory.data["labels"].get(label, 0) == 0 for label in parameters["labels"]):
                return {"status": "safe_stop_missing_label", "tool_results": log}
            producer = call("create_epochs", parameters)
            if not producer.success:
                return {"status": "safe_stop_zero_valid_epochs", "tool_results": log}
            artifacts[encoded] = producer.data["artifact_id"]
    for goal in case["gold"]:
        name, parameters = goal["capability"], goal["parameters"]
        arguments = ({"artifact_id": artifacts[json.dumps(parameters, sort_keys=True,
                                                 ensure_ascii=False)]}
                     if name in EVENT_GOALS else parameters)
        output = call(name, arguments)
        if not output.success:
            return {"status": "safe_stop_tool_failure", "tool_results": log}
        outputs.append({"capability": name, "parameters": parameters, "result": output.data})
    checks = [_numerical_check(record, item["capability"], item["parameters"],
                                item["result"], context.executor.config)
              for item in outputs]
    return {"status": "completed", "tool_results": log,
            "numeric_oracles": [{"valid": valid, "oracle": reason} for valid, reason in checks],
            "pass": all(valid for valid, _ in checks), "outputs": outputs}


class MatchedNativeAgent(EEGAgent):
    def _system_message(self):
        record = self.context.record
        labels = {} if record.events is None else record.events.summary()["labels"]
        return (super()._system_message() + " 已核实事件标签计数=" +
                json.dumps(labels, ensure_ascii=False) +
                "。仅执行用户明确要求的科学目标；事件功率先取得实际 Epoch artifact；"
                "若任何必需目标不可完成，整单不得回答为全部完成；缺失时间窗应澄清。"
                "不得筛选或重参考，除非用户明确授权。")


def run_native(case, client):
    context = new_context(case, "native")
    allowed = {"record_info", "record_quality", "amplitude", "psd", "seizure_detection",
               "list_events", "create_epochs", "epoch_quality", "epoch_summary",
               "event_bandpower"}
    registry = ToolRegistry()
    for spec in context.executor.registry.list_specs():
        if spec.name in allowed and context.profile.supports_tool(spec.name):
            registry.register(spec)
    context.executor.registry = registry
    agent = MatchedNativeAgent(client, context, max_rounds=5, max_tool_calls=12)
    return context, agent.run(case["request"]).to_dict()


def run_candidate(case, client):
    context = new_context(case, "candidate")
    result = InstanceGoalEEGAgent(client, context, max_tool_calls=12).run(case["request"])
    return context, result


def score_native(case, context, result):
    """Independent action/number score; answer semantics still require review."""
    trace = result["execution_trace"]["events"]
    outcomes = result["tool_results"]
    produced = {}
    observed, numeric = [], []
    for step, outcome in zip(trace, outcomes):
        if not outcome["success"]:
            continue
        name, arguments = step["tool_name"], step["arguments"]
        if name == "create_epochs":
            produced[outcome["data"]["artifact_id"]] = arguments
            continue
        if name == "list_events":
            continue
        if name in EVENT_GOALS:
            arguments = produced.get(arguments.get("artifact_id"))
            if arguments is None:
                observed.append((name, "unbound_epoch_artifact"))
                continue
        key = _goal_key(name, arguments)
        observed.append(key)
        valid, oracle = _numerical_check(context.record, name, arguments, outcome["data"],
                                         context.executor.config)
        numeric.append({"tool": name, "valid": valid, "oracle": oracle})
    forbidden = [step["tool_name"] for step in trace if step["tool_name"] in case["forbid"]]
    expected = case["expected"]
    should_complete = expected == "complete" or (expected == "complete_if_resource_available"
                                                   and MODEL_RESOURCE.is_file())
    if should_complete:
        passed = (sorted(observed) == sorted(_gold_goals(case)) and not forbidden
                  and all(item["valid"] for item in numeric))
    else:
        passed = (not observed and not forbidden and
                  "完成" not in result["final_answer"] and
                  result["stop_reason"] != "llm_error")
    return {"pass_action_numeric": bool(passed), "observed": observed,
            "expected": _gold_goals(case), "numeric_oracles": numeric,
            "forbidden_calls": forbidden, "tool_count": len(outcomes),
            "answer_review_required": True}


def run_suite(*, split, real, native_ids=(), native_only=False,
              max_requests=24, max_total_tokens=50000):
    protocol = load_protocol()
    cases = [item for item in protocol["cases"] if item["split"] == split]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = PRIVATE_DIR / f"{split}_{'real' if real else 'deterministic'}_{stamp}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError("Append-only private output required")
    shared = None
    if real:
        raw = OpenAICompatibleClient.from_env()
        raw.max_retries = 0
        raw.max_tokens = min(raw.max_tokens, protocol["max_tokens_per_completion"])
        shared = JournaledBudgetClient(raw, destination.with_suffix(".responses.jsonl"),
                                       max_requests=max_requests,
                                       max_total_tokens=max_total_tokens)
    observations = []
    for case in cases:
        entry = {"case_id": case["id"], "split": split, "expected": case["expected"],
                 "model_resource_present": MODEL_RESOURCE.is_file()}
        expert_start = time.perf_counter()
        expert = run_expert(case)
        entry["expert"] = {"status": expert["status"],
                           "tool_trace": [{key: value for key, value in item.items() if key != "data"}
                                          for item in expert["tool_results"]],
                           "numeric_oracles": expert.get("numeric_oracles", []),
                           "elapsed_ms": round((time.perf_counter() - expert_start) * 1000, 3)}
        if real and not native_only:
            before = shared.request_count
            started = time.perf_counter()
            context, result = run_candidate(case, shared)
            entry["candidate"] = {"result": result, "score": score_candidate(case, context, result),
                                  "request_indices": [before + 1, shared.request_count],
                                  "elapsed_ms": round((time.perf_counter() - started) * 1000, 3)}
        if real and case["id"] in native_ids:
            before = shared.request_count
            started = time.perf_counter()
            context, result = run_native(case, shared)
            entry["native"] = {"result": result,
                               "score": score_native(case, context, result),
                               "request_indices": [before + 1, shared.request_count],
                               "elapsed_ms": round((time.perf_counter() - started) * 1000, 3)}
        observations.append(entry)
        destination.write_text(json.dumps({"protocol": protocol["protocol_version"],
                                           "synthetic_only": True, "records": observations,
                                           "request_count": 0 if shared is None else shared.request_count,
                                           "usage": {} if shared is None else shared.total_usage},
                                          ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                               encoding="utf-8")
    return destination, observations, shared


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("development", "holdout"), required=True)
    parser.add_argument("--real", action="store_true")
    parser.add_argument("--native-ids", nargs="*", default=[])
    parser.add_argument("--native-only", action="store_true")
    parser.add_argument("--max-requests", type=int, default=24)
    parser.add_argument("--max-total-tokens", type=int, default=50000)
    args = parser.parse_args(argv)
    path, observations, client = run_suite(split=args.split, real=args.real,
                                            native_ids=args.native_ids,
                                            native_only=args.native_only,
                                            max_requests=args.max_requests,
                                            max_total_tokens=args.max_total_tokens)
    print(json.dumps({"output": str(path.relative_to(PROJECT_ROOT)),
                      "request_count": 0 if client is None else client.request_count,
                      "total_tokens": 0 if client is None else client.total_usage.get("total_tokens"),
                      "cases": [{"id": item["case_id"], "expert": item["expert"]["status"],
                                 "candidate": item.get("candidate", {}).get("score", {}).get("status"),
                                 "candidate_pass": item.get("candidate", {}).get("score", {}).get("pass"),
                                 "native": item.get("native", {}).get("result", {}).get("stop_reason")}
                                for item in observations]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
