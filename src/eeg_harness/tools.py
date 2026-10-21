"""Standard tool wrappers around the migrated EEG algorithms."""

from .legacy.features import compute_amplitude, compute_psd
from .legacy.seizure import seizureNormalModel_OneSecond
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
        "source": record.source,
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


def build_default_registry():
    registry = ToolRegistry()
    common_profiles = ("tuev_bipolar_22", "edf_native")
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
    return registry

