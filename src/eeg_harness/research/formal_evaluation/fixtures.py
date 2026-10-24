"""Deterministic fixtures and gold-only numerical oracles."""

from dataclasses import replace

import numpy as np

from ...context import ExecutionContext
from ...events import EEGEvent, EventSet
from ...executor import Executor
from ...pipeline import load_config
from ...profiles import get_profile
from ...tools import build_default_registry
from ..evidence_phase import build_quality_selection_record, oracle_event_bandpower


def build_fixture(case, config_path="config/baseline.json"):
    spec = case["fixture"]
    record, truth = build_quality_selection_record(tuple(spec["anomalous"]))
    labels = tuple(spec["labels"])
    events = EventSet(tuple(
        EEGEvent(label, event.onset_seconds, source_index=event.source_index)
        for label, event in zip(labels, record.events.events)
    ), source=f"synthetic://formal/{case['id']}/events")
    record = replace(
        record,
        events=events,
        source=f"synthetic://formal/{case['id']}/record",
        metadata={
            **dict(record.metadata),
            "profile_id": spec["profile"],
            "formal_case_id": case["id"],
            "fixture_seed": spec["seed"],
        },
    )
    config = load_config(config_path)
    profile = get_profile(spec["profile"])
    context = ExecutionContext(
        record, profile, Executor(build_default_registry(), config),
        task_id=f"formal-{case['id']}",
    )
    return context, truth, config


def oracle_source_epochs(record, labels, tmin, tmax):
    requested = set(labels)
    samples = int(round((tmax - tmin) * record.sfreq))
    rows, selected_labels, selected_onsets, source_indices = [], [], [], []
    for event in record.events.events:
        if event.label not in requested:
            continue
        start = int(round((event.onset_seconds + tmin) * record.sfreq))
        end = start + samples
        if start < 0 or end > record.data.shape[1] or samples <= 0:
            continue
        rows.append(record.data[:, start:end].copy())
        selected_labels.append(event.label)
        selected_onsets.append(event.onset_seconds)
        source_indices.append(event.source_index)
    if not rows:
        return None
    return {
        "data": np.stack(rows).astype(np.float32, copy=False),
        "labels": tuple(selected_labels),
        "onsets": tuple(selected_onsets),
        "source_indices": tuple(source_indices),
    }


def oracle_effective(case, record, config):
    task = case["task"]
    if task["disposition"] != "execute":
        return None
    params = task["parameters"]
    source = oracle_source_epochs(
        record, params["labels"], params["tmin"], params["tmax"],
    )
    if source is None:
        return None
    data = source["data"]
    labels = source["labels"]
    source_indices = source["source_indices"]
    transition = case["gold"]["transition"]
    if transition == "derived":
        anomalous = set(case["fixture"]["anomalous"])
        keep = [index for index, source_index in enumerate(source_indices) if source_index not in anomalous]
        data = data[keep]
        labels = tuple(labels[index] for index in keep)
    elif transition == "epoch_rereference":
        channel_index = {name: index for index, name in enumerate(record.channel_names)}
        refs = [channel_index[name] for name in params["reference_channels"]]
        data = (data - data[:, refs, :].mean(axis=1, keepdims=True)).astype(np.float32)
    return {
        "data": data,
        "labels": labels,
        "bandpower": oracle_event_bandpower(
            data, record.sfreq, record.channel_names, config["freq_bands"],
        ) if data.shape[0] else None,
    }
