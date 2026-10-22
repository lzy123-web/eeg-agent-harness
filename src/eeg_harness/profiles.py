"""Task profiles describe explicit EEG adaptation and tool compatibility."""

from dataclasses import dataclass
from typing import Optional

from .legacy.polar import BIPOLAR_PAIRS


class ProfileValidationError(ValueError):
    """Raised when a record does not satisfy a declared profile contract."""


@dataclass(frozen=True)
class TaskProfile:
    profile_id: str
    description: str
    adapter: str
    reference: str
    montage: str
    required_channels: tuple[str, ...]
    target_sfreq: Optional[float]
    max_window_seconds: Optional[float]
    compatible_tools: tuple[str, ...]
    l_freq: Optional[float] = None
    h_freq: Optional[float] = None
    notch_freq: Optional[float] = None
    average_reference: bool = False
    channel_types: tuple[str, ...] = ("eeg",)

    def supports_tool(self, tool_name):
        return tool_name in self.compatible_tools

    def validate_record(self, record):
        if self.target_sfreq is not None and record.sfreq != self.target_sfreq:
            raise ProfileValidationError(
                f"Profile {self.profile_id} requires {self.target_sfreq:g} Hz, "
                f"got {record.sfreq:g} Hz"
            )
        missing = [name for name in self.required_channels if name not in record.channel_names]
        if missing:
            raise ProfileValidationError(
                f"Profile {self.profile_id} is missing required channels: {', '.join(missing)}"
            )


BIPOLAR_22_CHANNELS = tuple(f"{left}-{right}" for left, right in BIPOLAR_PAIRS)

TUEV_BIPOLAR_22 = TaskProfile(
    profile_id="tuev_bipolar_22",
    description="Verified 22-channel bipolar preprocessing contract for the migrated model",
    adapter="bipolar_22",
    reference="pairwise subtraction (left-right)",
    montage="22-channel longitudinal bipolar montage",
    required_channels=BIPOLAR_22_CHANNELS,
    target_sfreq=256.0,
    max_window_seconds=60.0,
    compatible_tools=(
        "record_info", "amplitude", "psd", "seizure_detection",
        "list_events", "create_epochs", "epoch_summary", "event_bandpower",
        "record_quality", "epoch_quality",
        "select_quality_epochs",
    ),
    l_freq=0.5,
    h_freq=70.0,
    notch_freq=60.0,
)

EDF_NATIVE = TaskProfile(
    profile_id="edf_native",
    description="Native EDF EEG channels without resampling or reference conversion",
    adapter="native",
    reference="as recorded in EDF",
    montage="native EDF channel layout",
    required_channels=(),
    target_sfreq=None,
    max_window_seconds=60.0,
    compatible_tools=(
        "record_info", "amplitude", "psd",
        "list_events", "create_epochs", "epoch_summary", "event_bandpower",
        "record_quality", "epoch_quality",
        "select_quality_epochs",
    ),
)

PROFILES = {profile.profile_id: profile for profile in (TUEV_BIPOLAR_22, EDF_NATIVE)}


def get_profile(profile_id):
    try:
        return PROFILES[profile_id]
    except KeyError as exc:
        raise ValueError(f"Unknown EEG task profile: {profile_id}") from exc

