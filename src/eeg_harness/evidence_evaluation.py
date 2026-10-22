"""Frozen synthetic evaluation for evidence-driven adaptive analysis."""

import json
from pathlib import Path

import mne
import numpy as np

from .adaptive import EvidenceGoal, EvidencePolicy, EvidenceRequirement
from .applications.r3.adapter import R3_PROFILE
from .context import ExecutionContext
from .events import events_from_mne_raw
from .executor import Executor
from .pipeline import load_config
from .profiles import EDF_NATIVE, TUEV_BIPOLAR_22
from .record import EEGRecord
from .tools import build_default_registry


def load_evidence_suite(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("frozen_before_results") is not True:
        raise ValueError("Evidence benchmark must be frozen before results")
    return payload


def _profile(name):
    return {"native": EDF_NATIVE, "tuev": TUEV_BIPOLAR_22, "r3": R3_PROFILE}[name]


def make_evidence_context(case, config):
    profile = _profile(case["profile"])
    sfreq = profile.target_sfreq or 256.0
    channels = profile.required_channels or ("C1", "C2")
    time = np.arange(int(sfreq * 4)) / sfreq
    data = np.vstack([
        20e-6 * np.sin(2 * np.pi * (10 + index % 3) * time)
        for index in range(len(channels))
    ]).astype(np.float32)
    injection = case["injection"]
    if injection in ("flat_c1", "flat_first"):
        data[0] = 0
    elif injection == "spike_c1":
        data[0, ::20] = 500e-6
    elif injection == "line50_c1":
        data[0] += (80e-6 * np.sin(2 * np.pi * 50 * time)).astype(np.float32)
    elif injection in ("bad_epoch_one", "bad_epoch_two"):
        data[0, int(.4 * sfreq):int(.7 * sfreq)] = 500e-6
        if injection == "bad_epoch_two":
            data[0, int(1.5 * sfreq):int(1.8 * sfreq)] = 500e-6
    raw = mne.io.RawArray(data, mne.create_info(channels, sfreq, "eeg"), verbose=False)
    if case["kind"] == "event_bandpower":
        onsets = [0.05, 3.8] if injection == "boundary_events" else [.5, 1.6, 2.7]
        raw.set_annotations(mne.Annotations(onsets, [0] * len(onsets), ["A"] * len(onsets)))
    processing = ()
    if profile is R3_PROFILE:
        processing = (
            {"operation": "bandpass_filter", "l_freq": 1.0, "h_freq": 40.0},
            {"operation": "notch_filter", "frequency": 50.0},
            {"operation": "average_reference"},
        )
    elif profile is TUEV_BIPOLAR_22:
        processing = (
            {"operation": "bandpass_filter", "l_freq": .5, "h_freq": 70.0},
            {"operation": "notch_filter", "frequency": 60.0},
        )
    record = EEGRecord(
        data, sfreq, channels, profile.reference, profile.montage,
        f"synthetic://evidence/{case['case_id']}", processing,
        {"profile_id": profile.profile_id},
        events_from_mne_raw(raw, f"synthetic://evidence/{case['case_id']}"),
    )
    return ExecutionContext(
        record, profile, Executor(build_default_registry(), config),
        task_id=f"evidence-{case['case_id']}",
    )


def _goal(case):
    return EvidenceGoal(
        case["kind"], case["arguments"], tuple(case.get("alternatives", ())),
        EvidenceRequirement(
            min_usable_epochs_per_condition=case.get("min_usable_epochs", 1),
            max_tool_calls=case.get("max_tool_calls", 6),
            require_line_noise_valid=case.get("require_line_noise_valid", False),
        ),
        case["case_id"],
    )


def _detection_counts(case, result):
    if case["kind"] == "window_psd":
        quality = next((
            item["data"] for item in result.tool_results
            if item["tool_name"] == "record_quality" and item["success"]
        ), None)
        if quality is None:
            return None
        truth = set(case.get("truth_flagged_channels", ()))
        predicted = set(quality["flagged_channels"])
        universe = set(quality["channel_metrics"])
        return {
            "tp": len(truth & predicted), "fp": len(predicted - truth),
            "fn": len(truth - predicted), "tn": len(universe - truth - predicted),
        }
    quality = next((
        item["data"] for item in result.tool_results
        if item["tool_name"] == "epoch_quality" and item["success"]
    ), None)
    if quality is None:
        return None
    return {
        "expected_flagged_epochs": case.get("truth_flagged_epochs", 0),
        "observed_flagged_epochs": quality["epoch_counts"]["quality_flagged"],
    }


def run_evidence_benchmark(suite_path="config/evidence_benchmark_v1.json",
                           config_path="config/baseline.json"):
    suite = load_evidence_suite(suite_path)
    config = load_config(config_path)
    outcomes = []
    for mode in ("fixed", "expert", "candidate"):
        for case in suite["cases"]:
            result = EvidencePolicy(make_evidence_context(case, config), mode).run(_goal(case))
            correct = (
                case["expected"] == "complete" and result.status == "completed"
                and result.evidence_satisfied
            ) or (
                case["expected"] == "reject"
                and result.status in ("insufficient_evidence", "budget_exhausted", "rejected")
            )
            outcomes.append({
                "policy": mode, "case_id": case["case_id"], "split": case["split"],
                "profile": case["profile"], "injection_truth": case["injection"],
                "expected": case["expected"], "status": result.status,
                "evidence_satisfied": result.evidence_satisfied,
                "outcome_correct": correct, "reason_code": result.reason_code,
                "tool_calls": len(result.tool_results), "duration_ms": result.duration_ms,
                "detection": _detection_counts(case, result),
                "decision_trace": list(result.decision_trace),
            })
    summary = {}
    for mode in ("fixed", "expert", "candidate"):
        rows = [item for item in outcomes if item["policy"] == mode]
        complete = [item for item in rows if item["expected"] == "complete"]
        reject = [item for item in rows if item["expected"] == "reject"]
        confusion = [item["detection"] for item in rows if item["detection"] and "tp" in item["detection"]]
        epoch_detection = [item["detection"] for item in rows if item["detection"] and "observed_flagged_epochs" in item["detection"]]
        summary[mode] = {
            "evidence_goal_success_rate": sum(item["outcome_correct"] for item in complete) / len(complete),
            "correct_insufficient_evidence_rate": sum(item["outcome_correct"] for item in reject) / len(reject),
            "overall_case_accuracy": sum(item["outcome_correct"] for item in rows) / len(rows),
            "tool_calls": sum(item["tool_calls"] for item in rows),
            "mean_duration_ms": sum(item["duration_ms"] for item in rows) / len(rows),
            "channel_detection": {
                key: sum(item[key] for item in confusion) for key in ("tp", "fp", "fn", "tn")
            },
            "epoch_flag_count_exact": sum(
                item["expected_flagged_epochs"] == item["observed_flagged_epochs"]
                for item in epoch_detection
            ),
            "epoch_cases_measured": len(epoch_detection),
        }
    payload = {
        "suite_version": suite["suite_version"],
        "case_count": len(suite["cases"]),
        "policies": ["fixed", "expert", "candidate"],
        "summary": summary,
        "outcomes": outcomes,
        "limits": [
            "synthetic injection truth only; no clinical ground truth",
            "thresholds are empirical and not device-calibrated",
            "suite was frozen after pilot policy code, before result execution",
        ],
    }
    json.dumps(payload, ensure_ascii=False, allow_nan=False)
    return payload
