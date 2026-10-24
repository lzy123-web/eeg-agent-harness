"""Standard tool wrappers around the migrated and event-related EEG algorithms."""

import numpy as np
from dataclasses import replace
from uuid import uuid4
from scipy.signal import welch

from .events import ArtifactConsistencyError, create_epoch_set
from .legacy.features import compute_amplitude, compute_psd
from .legacy.seizure import seizureNormalModel_OneSecond
from .provenance import source_reference
from .quality import epoch_quality, record_quality
from .tooling import ToolRegistry, ToolSpec


WINDOW_SCHEMA = {
    "type": "object",
    "properties": {
        "channels": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "start": {"type": "number", "minimum": 0},
        "end": {"type": "number", "exclusiveMinimum": 0},
    },
    "required": ["channels", "start", "end"],
    "additionalProperties": False,
}


def _record_info(record, arguments, config, resources):
    return {
        "sfreq": record.sfreq,
        "duration_seconds": record.duration_seconds,
        "sample_count": int(record.data.shape[1]),
        "channel_count": int(record.data.shape[0]),
        "channel_names": list(record.channel_names),
        "reference": record.reference,
        "montage": record.montage,
        "source": source_reference(record.source),
        "processing": list(record.processing_metadata),
    }


def _amplitude(record, arguments, config, resources):
    return compute_amplitude(
        record, arguments["channels"], arguments["start"], arguments["end"], config
    )


def _psd(record, arguments, config, resources):
    return compute_psd(
        record, arguments["channels"], arguments["start"], arguments["end"], config
    )


def _seizure(record, arguments, config, resources):
    return seizureNormalModel_OneSecond(
        record,
        arguments["channels"],
        arguments["start"],
        arguments["end"],
        config,
        model_path=resources["seizure_model"],
    )


def _list_events(record, arguments, config, resources):
    if record.events is None:
        return {
            "event_count": 0,
            "labels": {},
            "time_reference": "seconds_from_record_start",
            "first_onset_seconds": None,
            "last_onset_seconds": None,
            "source": source_reference(record.source),
        }
    return record.events.summary()


def _create_epochs(record, arguments, config, resources):
    epochs = create_epoch_set(
        record,
        arguments["labels"],
        arguments["tmin"],
        arguments["tmax"],
        baseline=arguments.get("baseline"),
    )
    resources["artifact_store"][epochs.artifact_id] = epochs
    return epochs.summary()


def _get_epoch_artifact(arguments, resources):
    artifact_id = arguments["artifact_id"]
    try:
        artifact = resources["artifact_store"][artifact_id]
    except KeyError as exc:
        raise LookupError(f"Epoch artifact not found: {artifact_id}") from exc
    expected = arguments.get("expected_artifact_fingerprint")
    if expected is not None and artifact.content_fingerprint() != expected:
        raise ArtifactConsistencyError(
            "Epoch artifact content does not match the expected fingerprint"
        )
    return artifact


def _epoch_summary(record, arguments, config, resources):
    return _get_epoch_artifact(arguments, resources).summary()


def _event_bandpower(record, arguments, config, resources):
    epochs = _get_epoch_artifact(arguments, resources)
    epoch_samples = epochs.data.shape[-1]
    if epoch_samples < int(round(epochs.sfreq)):
        raise ValueError(
            "Epoch duration is too short for 1 Hz Welch resolution; "
            "event_bandpower requires at least one second"
        )
    freq_bands = config["freq_bands"]
    output = {}
    for label in sorted(set(epochs.event_labels)):
        indices = [index for index, value in enumerate(epochs.event_labels) if value == label]
        condition = epochs.data[indices]
        channel_output = {}
        for channel_index, channel_name in enumerate(epochs.channel_names):
            per_epoch = []
            for epoch in condition[:, channel_index, :]:
                frequencies, density = welch(
                    epoch,
                    fs=epochs.sfreq,
                    nperseg=min(len(epoch), max(1, int(round(epochs.sfreq)))),
                )
                per_epoch.append([
                    float(np.trapz(
                        density[np.logical_and(frequencies >= low, frequencies <= high)],
                        frequencies[np.logical_and(frequencies >= low, frequencies <= high)],
                    ))
                    for low, high in freq_bands.values()
                ])
            mean_power = np.asarray(per_epoch, dtype=float).mean(axis=0)
            channel_output[channel_name] = {
                band_name: float(value)
                for band_name, value in zip(freq_bands, mean_power)
            }
        output[label] = {
            "epoch_count": len(indices),
            "channels": channel_output,
        }
    return {
        "artifact_id": epochs.artifact_id,
        "artifact_fingerprint": epochs.content_fingerprint(),
        "method": "whole-Epoch Welch PSD followed by arithmetic mean across Epochs",
        "interpretation": "absolute event-window bandpower; not baseline-normalized ERD/ERS",
        "frequency_resolution_hz": float(epochs.sfreq / min(epoch_samples, int(round(epochs.sfreq)))),
        "conditions": output,
    }


def _record_quality(record, arguments, config, resources):
    return record_quality(
        record,
        record.metadata.get("profile_id", "unknown"),
        channels=arguments.get("channels"),
        start=arguments.get("start"),
        end=arguments.get("end"),
        line_frequency=arguments.get("line_frequency", 50.0),
    )


def _epoch_quality(record, arguments, config, resources):
    return epoch_quality(
        _get_epoch_artifact(arguments, resources),
        record.metadata.get("profile_id", "unknown"),
    )


def _select_quality_epochs(record, arguments, config, resources):
    epochs = _get_epoch_artifact(arguments, resources)
    evidence = epoch_quality(
        epochs, record.metadata.get("profile_id", "unknown")
    )
    expected_evidence = arguments.get("expected_quality_evidence_id")
    if expected_evidence is not None and evidence["evidence_id"] != expected_evidence:
        raise ArtifactConsistencyError(
            "Current Epoch quality evidence does not match expected_quality_evidence_id"
        )
    excluded = set(evidence["flagged_epoch_indices"])
    kept = [index for index in range(epochs.data.shape[0]) if index not in excluded]
    if not kept:
        raise ValueError("No Epochs remain after the declared quality rules")
    selected = replace(
        epochs,
        data=epochs.data[kept].copy(),
        event_labels=tuple(epochs.event_labels[index] for index in kept),
        event_onsets_seconds=tuple(epochs.event_onsets_seconds[index] for index in kept),
        artifact_id=f"{epochs.artifact_id}-quality-selected",
        parameters={
            **dict(epochs.parameters),
            "quality_selection_evidence_id": evidence["evidence_id"],
            "excluded_epoch_indices": sorted(excluded),
        },
    )
    resources["artifact_store"][selected.artifact_id] = selected
    output = selected.summary()
    output["selection"] = {
        "input_epoch_count": int(epochs.data.shape[0]),
        "excluded_epoch_count": len(excluded),
        "output_epoch_count": len(kept),
        "evidence_id": evidence["evidence_id"],
    }
    return output


def _rereference_epochs(record, arguments, config, resources):
    epochs = _get_epoch_artifact(arguments, resources)
    reference_channels = tuple(arguments["reference_channels"])
    if not reference_channels:
        raise ValueError("At least one explicit reference channel is required")
    if len(reference_channels) != len(set(reference_channels)):
        raise ValueError("Reference channels must be unique")
    channel_index = {name: index for index, name in enumerate(epochs.channel_names)}
    missing = [name for name in reference_channels if name not in channel_index]
    if missing:
        raise ValueError("Reference channels are absent from Epoch artifact: " + ", ".join(missing))
    indices = [channel_index[name] for name in reference_channels]
    reference_signal = epochs.data[:, indices, :].mean(axis=1, keepdims=True)
    transformed_data = (epochs.data - reference_signal).astype(epochs.data.dtype, copy=False)
    source_fingerprint = epochs.content_fingerprint()
    reference = "explicit average of " + ", ".join(reference_channels)
    transformed = replace(
        epochs,
        data=transformed_data.copy(),
        reference=reference,
        artifact_id=f"epochs-{uuid4()}",
        parameters={
            **dict(epochs.parameters),
            "rereference": {
                "method": "subtract_explicit_reference_channel_mean",
                "reference_channels": list(reference_channels),
                "source_artifact_fingerprint": source_fingerprint,
            },
        },
    )
    resources["artifact_store"][transformed.artifact_id] = transformed
    output = transformed.summary()
    output["transformation"] = {
        "operation": "epoch_rereference",
        "reference_channels": list(reference_channels),
        "source_artifact_id": epochs.artifact_id,
        "source_artifact_fingerprint": source_fingerprint,
        "output_reference": reference,
    }
    return output


def build_default_registry():
    registry = ToolRegistry()
    common_profiles = ("*",)
    registry.register(
        ToolSpec(
            name="record_info",
            description="Inspect this EEG record: sampling rate, duration, channels, reference and processing metadata. Use this for record-information requests.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            return_type="object",
            compatible_profiles=common_profiles,
            handler=_record_info,
        )
    )
    registry.register(
        ToolSpec(
            name="amplitude",
            description="Compute mean absolute amplitude, RMS, maximum and minimum for a time window.",
            parameters=WINDOW_SCHEMA,
            return_type="object",
            compatible_profiles=common_profiles,
            handler=_amplitude,
            requires_window=True,
            max_window_seconds=60.0,
        )
    )
    registry.register(
        ToolSpec(
            name="psd",
            description="Compute Welch absolute band power for explicitly named EEG channels and a valid [start,end) window in seconds.",
            parameters=WINDOW_SCHEMA,
            return_type="object",
            compatible_profiles=common_profiles,
            handler=_psd,
            requires_window=True,
            max_window_seconds=60.0,
        )
    )
    registry.register(
        ToolSpec(
            name="seizure_detection",
            description="Run the research-only migrated seizure/non-seizure model. Valid only for the verified tuev_bipolar_22 Profile at 256 Hz with a model resource; it is not a clinical diagnosis.",
            parameters=WINDOW_SCHEMA,
            return_type="array",
            compatible_profiles=("tuev_bipolar_22",),
            handler=_seizure,
            requires_window=True,
            max_window_seconds=10.0,
            required_sfreq=256.0,
            required_resources=("seizure_model",),
        )
    )
    event_profiles = ("*",)
    registry.register(
        ToolSpec(
            name="list_events",
            description="Inspect actual event labels, counts and onset-time range without returning EEG arrays. Use it when event availability or labels are not yet established.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            return_type="object",
            compatible_profiles=event_profiles,
            handler=_list_events,
            observes_state=("events",),
        )
    )
    registry.register(
        ToolSpec(
            name="create_epochs",
            description="Create an in-session Epoch artifact for confirmed event labels and a relative window. Returns an artifact_id; labels must exist in the current record.",
            parameters={
                "type": "object",
                "properties": {
                    "labels": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                    "tmin": {"type": "number"},
                    "tmax": {"type": "number"},
                    "baseline": {"type": "array"},
                },
                "required": ["labels", "tmin", "tmax"],
                "additionalProperties": False,
            },
            return_type="object",
            compatible_profiles=event_profiles,
            handler=_create_epochs,
            produces_artifact="epochs",
            requires_events=True,
            state_effect="stores_session_artifact",
        )
    )
    artifact_schema = {
        "type": "object",
        "properties": {
            "artifact_id": {"type": "string"},
            "expected_artifact_fingerprint": {"type": "string"},
        },
        "required": ["artifact_id"],
        "additionalProperties": False,
    }
    selection_schema = {
        "type": "object",
        "properties": {
            **artifact_schema["properties"],
            "expected_quality_evidence_id": {"type": "string"},
        },
        "required": ["artifact_id"],
        "additionalProperties": False,
    }
    rereference_schema = {
        "type": "object",
        "properties": {
            **artifact_schema["properties"],
            "reference_channels": {
                "type": "array", "items": {"type": "string"}, "minItems": 1,
            },
        },
        "required": ["artifact_id", "reference_channels"],
        "additionalProperties": False,
    }
    registry.register(
        ToolSpec(
            name="epoch_summary",
            description="Return metadata and rejection summary for an in-session Epoch artifact.",
            parameters=artifact_schema,
            return_type="object",
            compatible_profiles=event_profiles,
            handler=_epoch_summary,
            consumes_artifact="epochs",
        )
    )
    registry.register(
        ToolSpec(
            name="event_bandpower",
            description="Compute mean Welch absolute band power per event condition and channel from an existing Epoch artifact. Requires its exact artifact_id; this is not ERD/ERS.",
            parameters=artifact_schema,
            return_type="object",
            compatible_profiles=event_profiles,
            handler=_event_bandpower,
            consumes_artifact="epochs",
            preconditions={"min_artifact_duration_seconds": 1.0},
        )
    )
    registry.register(
        ToolSpec(
            name="rereference_epochs",
            description=(
                "Create a new Epoch artifact by subtracting the mean of explicitly named "
                "existing reference channels from every EEG channel. This changes the "
                "scientific reference state and requires explicit user authorization."
            ),
            parameters=rereference_schema,
            return_type="object",
            compatible_profiles=("edf_native",),
            handler=_rereference_epochs,
            consumes_artifact="epochs",
            produces_artifact="epochs",
            state_effect="stores_session_artifact",
        )
    )
    registry.register(
        ToolSpec(
            name="record_quality",
            description="Measure record/window flatline, high-amplitude and valid line-noise evidence without a composite score.",
            parameters={
                "type": "object",
                "properties": {
                    "channels": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "line_frequency": {"type": "number"},
                },
                "additionalProperties": False,
            },
            return_type="object",
            compatible_profiles=("*",),
            handler=_record_quality,
            observes_state=("record_quality",),
        )
    )
    registry.register(
        ToolSpec(
            name="epoch_quality",
            description="Measure Epoch coverage and empirical flatline/high-amplitude flags without returning waveforms.",
            parameters=artifact_schema,
            return_type="object",
            compatible_profiles=("*",),
            handler=_epoch_quality,
            consumes_artifact="epochs",
            observes_state=("epoch_quality",),
        )
    )
    registry.register(
        ToolSpec(
            name="select_quality_epochs",
            description="Create a derived Epoch artifact excluding only epochs flagged by declared empirical quality rules.",
            parameters=selection_schema,
            return_type="object",
            compatible_profiles=("*",),
            handler=_select_quality_epochs,
            consumes_artifact="epochs",
            produces_artifact="epochs",
            state_effect="stores_session_artifact",
        )
    )
    return registry

