"""Frozen shared fixtures, faults, contracts and independent numerical oracle."""

from dataclasses import replace
import json
from pathlib import Path

import numpy as np

from ...context import ExecutionContext
from ...events import EEGEvent, EventSet
from ...executor import Executor
from ...pipeline import load_config
from ...planning import Plan, TaskSpec
from ...profiles import get_profile
from ...tooling import ToolResult
from ..evidence_phase.synthetic import build_quality_selection_record
from ..integrated_method.contracts import Obligation, ObligationLedger
from .tool import build_extensibility_registry


CASES_PATH = Path("config/point1_extensibility_cases_v1.json")


def load_cases(path=CASES_PATH):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload["protocol_id"] != "point1-extensibility-v1" or len(payload["cases"]) != 7:
        raise ValueError("Extensibility protocol identity or case count changed")
    return payload


class ExtensionFaultExecutor:
    """Method-independent, one-shot fault injection at the Executor boundary."""

    def __init__(self, base, kind):
        self.base = base
        self.kind = kind
        self.registry = base.registry
        self.config = base.config
        self.resources = base.resources
        self.applied = False

    def execute(self, record, profile, request, session_resources=None):
        trigger = (
            self.kind == "one_shot_variance_failure" and request.name == "epoch_variance"
        ) or (
            self.kind in {"effective_artifact_expiry", "source_content_change"}
            and request.name == "event_bandpower"
        )
        if trigger and not self.applied:
            self.applied = True
            if self.kind == "one_shot_variance_failure":
                return ToolResult(
                    request.request_id, request.name, False,
                    error_code="INJECTED_TRANSIENT_FAILURE",
                    error_message="Frozen one-shot extensibility failure",
                )
            store = (session_resources or {}).get("artifact_store", {})
            if self.kind == "effective_artifact_expiry":
                store.pop(request.arguments["artifact_id"], None)
            else:
                record.data[0] += np.float32(1e-6)
                store.clear()
        return self.base.execute(record, profile, request, session_resources)


def build_context(case):
    record, truth = build_quality_selection_record(tuple(case["fixture"]["anomalous"]))
    labels = tuple(case["fixture"]["labels"])
    events = EventSet(tuple(
        EEGEvent(label, event.onset_seconds, source_index=event.source_index)
        for label, event in zip(labels, record.events.events)
    ), source=f"synthetic://extensibility/{case['id']}/events")
    record = replace(
        record, events=events, source=f"synthetic://extensibility/{case['id']}/record",
        metadata={**dict(record.metadata), "extensibility_case_id": case["id"]},
    )
    base_profile = get_profile("edf_native")
    profile = replace(
        base_profile,
        compatible_tools=base_profile.compatible_tools + ("epoch_variance",),
    )
    executor = Executor(build_extensibility_registry(), load_config("config/baseline.json"))
    if case["fault"] != "none":
        executor = ExtensionFaultExecutor(executor, case["fault"])
    return ExecutionContext(record, profile, executor, task_id=f"ext-{case['id']}"), truth


def compile_case(case, context):
    params = dict(case["task"]["parameters"])
    objectives = tuple(case["task"]["objectives"])
    task = TaskSpec(
        "event_workflow", {**params, "objectives": list(objectives)},
        task_id=f"ext-task-{case['id']}",
    )
    expected = ["list_events", "create_epochs"]
    mapping = {
        "epoch_quality": "epoch_quality",
        "trial_selection": "select_quality_epochs",
        "epoch_rereference": "rereference_epochs",
        "epoch_variance": "epoch_variance",
        "event_bandpower": "event_bandpower",
    }
    expected.extend(mapping[item] for item in objectives if item in mapping)
    ledger = ObligationLedger(
        context.task_id, "event_workflow",
        (Obligation("objectives", "objectives", list(objectives)),
         Obligation("evidence", "successful_tools", expected)),
        tuple(case["forbidden_tools"]),
    )
    plan = Plan(task.task_id, "ready", state_summary={"context_id": context.task_id})
    return task, ledger, plan, {"valid": True, "code": None, "violations": []}


def oracle_effective(case, record):
    params = case["task"]["parameters"]
    labels = set(params["labels"])
    count = int(round((params["tmax"] - params["tmin"]) * record.sfreq))
    rows, row_labels, source_indices = [], [], []
    for event in record.events.events:
        if event.label not in labels:
            continue
        start = int(round((event.onset_seconds + params["tmin"]) * record.sfreq))
        rows.append(record.data[:, start:start + count].astype(np.float64, copy=True))
        row_labels.append(event.label)
        source_indices.append(event.source_index)
    data = np.stack(rows)
    if "trial_selection" in case["task"]["objectives"]:
        anomalous = set(case["fixture"]["anomalous"])
        keep = [i for i, source_index in enumerate(source_indices) if source_index not in anomalous]
        data = data[keep]
        row_labels = [row_labels[i] for i in keep]
    if "epoch_rereference" in case["task"]["objectives"]:
        channel_index = {name: i for i, name in enumerate(record.channel_names)}
        refs = [channel_index[name] for name in params["reference_channels"]]
        data = data - data[:, refs, :].mean(axis=1, keepdims=True)
    output = {}
    for label in sorted(set(row_labels)):
        selected = data[[i for i, value in enumerate(row_labels) if value == label]]
        channels = {}
        for channel_index, channel in enumerate(record.channel_names):
            values = selected[:, channel_index, :].reshape(-1)
            mean = sum(float(value) for value in values) / len(values)
            channels[channel] = sum((float(value) - mean) ** 2 for value in values) / len(values)
        output[label] = {"epoch_count": int(selected.shape[0]), "channels": channels}
    return output
