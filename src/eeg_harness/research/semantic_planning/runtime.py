"""Execution of semantic operations through the existing Registry/Executor/Context."""

from dataclasses import replace
import math

import mne
import numpy as np
from scipy.signal import butter, sosfiltfilt, welch

from ...context import ExecutionContext
from ...events import EEGEvent, EventSet, create_epoch_set
from ...executor import Executor
from ...profiles import TaskProfile
from ...quality import record_quality
from ...record import EEGRecord
from ...tooling import ToolRegistry, ToolRequest, ToolSpec
from .contracts import build_contracts
from .models import ArtifactPayload, ScientificRequirement, SemanticArtifact


TOOL_NAMES = tuple(contract.name for contract in build_contracts())


def build_semantic_profile():
    return TaskProfile(
        profile_id="semantic_research_synthetic",
        description="Isolated synthetic profile for Issue #8 scientific-semantic pilot",
        adapter="synthetic_semantic",
        reference="declared by synthetic source",
        montage="synthetic",
        required_channels=(), target_sfreq=None, max_window_seconds=None,
        compatible_tools=TOOL_NAMES,
    )


def _payload(arguments, resources):
    artifact_id = arguments["input_artifact_id"]
    try:
        value = resources["artifact_store"][artifact_id]
    except KeyError as exc:
        raise LookupError(f"Semantic artifact not found: {artifact_id}") from exc
    if not isinstance(value, ArtifactPayload):
        raise ValueError("Artifact is not a semantic research artifact")
    return value


def _requirement(arguments):
    params = dict(arguments.get("parameters", {}))
    return ScientificRequirement("runtime", arguments["goal_kind"], params)


def _contract(name):
    return next(item for item in build_contracts() if item.name == name)


def _store(name, payload, requirement, resources, actual_value):
    semantic, evidence, error = _contract(name).apply(payload.semantic, requirement)
    if semantic is None:
        raise ValueError(error or "Scientific precondition failed")
    expected = resources.get("expected_output_artifact_id")
    if expected and semantic.artifact_id != expected:
        raise ValueError("Planned and executed semantic artifact identifiers differ")
    resources["artifact_store"][semantic.artifact_id] = ArtifactPayload(semantic, actual_value)
    return {
        "artifact": semantic.to_dict(),
        "validity_evidence": list(evidence),
    }


def _lowpass(record, arguments, config, resources):
    payload = _payload(arguments, resources)
    requirement = _requirement(arguments)
    source = payload.value
    if not isinstance(source, EEGRecord):
        raise ValueError("Low-pass requires an EEGRecord payload")
    h_freq = float(requirement.parameters.get("require_lowpass_hz", 40.0))
    sos = butter(4, h_freq / (source.sfreq / 2), btype="lowpass", output="sos")
    filtered = sosfiltfilt(sos, source.data, axis=1).astype(np.float32)
    output = replace(
        source, data=filtered,
        processing_metadata=source.processing_metadata + ({"operation": "lowpass_filter", "h_freq": h_freq},),
    )
    return _store("sp_lowpass", payload, requirement, resources, output)


def _resample(record, arguments, config, resources):
    payload = _payload(arguments, resources)
    requirement = _requirement(arguments)
    source = payload.value
    if not isinstance(source, EEGRecord) or source.events is None:
        raise ValueError("Joint resampling requires an EEGRecord with events")
    target = float(requirement.parameters["target_sfreq"])
    info = mne.create_info(list(source.channel_names), source.sfreq, ch_types="eeg")
    raw = mne.io.RawArray(source.data.astype(float), info, verbose="ERROR")
    labels = sorted(source.events.labels)
    label_codes = {label: index + 1 for index, label in enumerate(labels)}
    events = np.asarray([
        [int(round(item.onset_seconds * source.sfreq)), 0, label_codes[item.label]]
        for item in source.events.events
    ], dtype=int)
    raw, resampled_events = raw.resample(target, events=events, verbose="ERROR")
    reverse = {value: key for key, value in label_codes.items()}
    event_set = EventSet(tuple(
        EEGEvent(reverse[int(row[2])], float(row[0]) / target, source_index=index,
                 metadata={"joint_resample_sample": int(row[0])})
        for index, row in enumerate(resampled_events)
    ), source=source.events.source, time_reference="seconds_from_record_start_on_resampled_grid")
    output = replace(
        source, data=raw.get_data().astype(np.float32), sfreq=target, events=event_set,
        processing_metadata=source.processing_metadata + ({
            "operation": "resample_with_events", "from_sfreq": source.sfreq,
            "to_sfreq": target, "method": "mne.io.Raw.resample(events=events)",
        },),
    )
    return _store("sp_resample_with_events", payload, requirement, resources, output)


def _epochs(record, arguments, config, resources):
    payload = _payload(arguments, resources)
    requirement = _requirement(arguments)
    source = payload.value
    epochs = create_epoch_set(
        source, requirement.parameters["labels"],
        requirement.parameters.get("tmin", -0.1), requirement.parameters.get("tmax", 0.4),
    )
    result = _store("sp_create_epochs", payload, requirement, resources, epochs)
    stored = resources["artifact_store"][result["artifact"]["artifact_id"]]
    counts = {label: stored.value.event_labels.count(label) for label in sorted(set(stored.value.event_labels))}
    semantic = replace(
        stored.semantic,
        condition_counts=tuple(sorted(counts.items())),
        properties=tuple({
            **dict(stored.semantic.properties),
            "epoch_labels_by_index": list(stored.value.event_labels),
            "valid_epoch_count": int(stored.value.data.shape[0]),
        }.items()),
    )
    resources["artifact_store"][semantic.artifact_id] = ArtifactPayload(semantic, epochs)
    result["artifact"] = semantic.to_dict()
    return result


def _select(record, arguments, config, resources):
    payload = _payload(arguments, resources)
    requirement = _requirement(arguments)
    epochs = payload.value
    selection = requirement.parameters["selection"]
    if not selection.get("authorized", False):
        raise ValueError("Epoch selection was not authorized by the task")
    excluded = set(map(int, selection.get("exclude_indices", ())))
    kept = [index for index in range(epochs.data.shape[0]) if index not in excluded]
    if not kept:
        raise ValueError("No Epochs remain after selection")
    output = replace(
        epochs, data=epochs.data[kept].copy(),
        event_labels=tuple(epochs.event_labels[index] for index in kept),
        event_onsets_seconds=tuple(epochs.event_onsets_seconds[index] for index in kept),
    )
    result = _store("sp_select_epochs", payload, requirement, resources, output)
    stored = resources["artifact_store"][result["artifact"]["artifact_id"]]
    semantic = replace(stored.semantic, properties=tuple({
        **dict(stored.semantic.properties),
        "epoch_labels_by_index": list(output.event_labels),
        "valid_epoch_count": int(output.data.shape[0]),
    }.items()))
    resources["artifact_store"][semantic.artifact_id] = ArtifactPayload(semantic, output)
    result["artifact"] = semantic.to_dict()
    return result


def _line_noise(record, arguments, config, resources):
    payload = _payload(arguments, resources)
    requirement = _requirement(arguments)
    source = payload.value
    frequency = float(requirement.parameters.get("frequency_hz", 50.0))
    evidence = record_quality(
        source, "semantic_research_synthetic", line_frequency=frequency,
        start=0.0, end=source.duration_seconds,
    )
    values = [item["line_noise_ratio"]["value"] for item in evidence["channel_metrics"].values()]
    if any(value is None for value in values):
        raise ValueError("Requested line-noise evidence is not observable")
    result = _store("sp_line_noise", payload, requirement, resources, {
        "mean_line_noise_ratio": float(np.mean(values)), "frequency_hz": frequency,
    })
    result["value"] = float(np.mean(values))
    return result


def _bandpower(record, arguments, config, resources):
    payload = _payload(arguments, resources)
    requirement = _requirement(arguments)
    source = payload.value
    low = float(requirement.parameters.get("low_hz", 1.0))
    high = float(requirement.parameters.get("high_hz", 40.0))
    values = []
    for channel in source.data:
        frequencies, density = welch(channel, fs=source.sfreq, nperseg=min(len(channel), int(source.sfreq * 2)))
        mask = (frequencies >= low) & (frequencies <= high)
        values.append(float(np.trapz(density[mask], frequencies[mask])))
    result = _store("sp_bandpower", payload, requirement, resources, np.asarray(values))
    result["values"] = values
    return result


def _epoch_feature(name, record, arguments, config, resources):
    payload = _payload(arguments, resources)
    requirement = _requirement(arguments)
    epochs = payload.value
    if name == "sp_epoch_variance":
        values = {
            label: float(np.var(epochs.data[np.asarray(epochs.event_labels) == label]))
            for label in sorted(set(epochs.event_labels))
        }
    else:
        values = {
            label: float(np.mean(np.abs(epochs.data[np.asarray(epochs.event_labels) == label])))
            for label in sorted(set(epochs.event_labels))
        }
    result = _store(name, payload, requirement, resources, values)
    result["values"] = values
    result["source_epoch_artifact_id"] = payload.semantic.artifact_id
    return result


def _schema():
    return {
        "type": "object",
        "properties": {
            "input_artifact_id": {"type": "string"},
            "goal_kind": {"type": "string"},
            "parameters": {"type": "object"},
        },
        "required": ["input_artifact_id", "goal_kind", "parameters"],
        "additionalProperties": False,
    }


def build_semantic_registry():
    handlers = {
        "sp_lowpass": _lowpass, "sp_resample_with_events": _resample,
        "sp_create_epochs": _epochs, "sp_select_epochs": _select,
        "sp_line_noise": _line_noise, "sp_bandpower": _bandpower,
        "sp_condition_feature": lambda *args: _epoch_feature("sp_condition_feature", *args),
        "sp_epoch_variance": lambda *args: _epoch_feature("sp_epoch_variance", *args),
    }
    registry = ToolRegistry()
    for contract in build_contracts():
        registry.register(ToolSpec(
            name=contract.name,
            description="Research-only semantic operation: " + "; ".join(contract.effect.scientific_semantics),
            parameters=_schema(), return_type="object",
            compatible_profiles=("semantic_research_synthetic",),
            handler=handlers[contract.name],
            consumes_artifact=contract.effect.consumes,
            produces_artifact=contract.effect.produces,
            state_effect="stores_session_artifact",
            preconditions={"scientific_semantics": list(contract.effect.scientific_semantics)},
        ))
    return registry


class SemanticRuntime:
    """Thin adapter over the production Executor and ExecutionContext."""

    def __init__(self, root_record: EEGRecord, initial_payloads):
        self.profile = build_semantic_profile()
        record = replace(root_record, metadata={**dict(root_record.metadata), "profile_id": self.profile.profile_id})
        executor = Executor(build_semantic_registry(), config={"research_only": True})
        self.context = ExecutionContext(record, self.profile, executor)
        for payload in initial_payloads:
            self.context.artifacts[payload.semantic.artifact_id] = payload

    def execute_plan(self, plan):
        outputs = []
        for step in plan.steps:
            request = ToolRequest(step.operation, {
                "input_artifact_id": step.input_artifact_id,
                "goal_kind": step.arguments["goal_kind"],
                "parameters": dict(step.arguments["parameters"]),
            })
            # Executor copies the resource mapping; the expected ID remains a validation hint
            self.context.executor.resources["expected_output_artifact_id"] = step.output_artifact_id
            result = self.context.execute(request)
            outputs.append(result)
            if not result.success:
                self.context.trace.finish("stopped_on_error")
                break
        else:
            self.context.trace.finish("completed")
        self.context.executor.resources.pop("expected_output_artifact_id", None)
        return outputs

    def artifact(self, artifact_id):
        return self.context.artifacts[artifact_id]
