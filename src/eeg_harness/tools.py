"""Standard tool wrappers around the migrated and event-related EEG algorithms."""

import numpy as np
from scipy.signal import welch

from .events import create_epoch_set
from .legacy.features import compute_amplitude, compute_psd
from .legacy.seizure import seizureNormalModel_OneSecond
from .provenance import source_reference
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
        return resources["artifact_store"][artifact_id]
    except KeyError as exc:
        raise LookupError(f"Epoch artifact not found: {artifact_id}") from exc


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
        "method": "whole-Epoch Welch PSD followed by arithmetic mean across Epochs",
        "interpretation": "absolute event-window bandpower; not baseline-normalized ERD/ERS",
        "frequency_resolution_hz": float(epochs.sfreq / min(epoch_samples, int(round(epochs.sfreq)))),
        "conditions": output,
    }


def build_default_registry():
    registry = ToolRegistry()
    common_profiles = ("*",)
    registry.register(
        ToolSpec(
            name="record_info",
            description="Return sampling rate, duration, channels, reference and processing metadata.",
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
            description="Compute Welch band power for configured EEG frequency bands.",
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
            description="Run the migrated one-second single-channel seizure/non-seizure model.",
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
            description="List event labels, counts and onset-time range without returning EEG arrays.",
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
            description="Create an in-session Epoch artifact for selected event labels and a relative window.",
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
        "properties": {"artifact_id": {"type": "string"}},
        "required": ["artifact_id"],
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
            description="Compute reproducible mean Welch band power per event condition and channel.",
            parameters=artifact_schema,
            return_type="object",
            compatible_profiles=event_profiles,
            handler=_event_bandpower,
            consumes_artifact="epochs",
            preconditions={"min_artifact_duration_seconds": 1.0},
        )
    )
    return registry

