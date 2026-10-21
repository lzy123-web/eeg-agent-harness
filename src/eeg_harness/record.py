"""Explicit, task-neutral EEG data objects and validated slicing."""

from dataclasses import dataclass, field
import math
from typing import Any, Mapping

import numpy as np


@dataclass(frozen=True)
class EEGRecord:
    """A processed EEG recording passed explicitly between analysis tools.

    ``data`` is channel-major with shape ``[channels, samples]``.  Dataset and
    clinical label semantics deliberately do not belong in this core object.
    """

    data: np.ndarray
    sfreq: float
    channel_names: tuple[str, ...]
    reference: str
    montage: str
    source: str
    processing_metadata: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    events: Any = None

    def __post_init__(self):
        data = np.asarray(self.data)
        channel_names = tuple(self.channel_names)
        if data.ndim != 2:
            raise ValueError(f"EEG data must have shape [channels, samples], got {data.shape}")
        if not math.isfinite(float(self.sfreq)) or float(self.sfreq) <= 0:
            raise ValueError("EEG sampling frequency must be a positive finite number")
        if len(channel_names) != data.shape[0]:
            raise ValueError(
                f"Channel name count {len(channel_names)} does not match data rows {data.shape[0]}"
            )
        if not channel_names or any(not name for name in channel_names):
            raise ValueError("EEG channel names must be non-empty")
        if len(set(channel_names)) != len(channel_names):
            raise ValueError("EEG channel names must be unique")
        if data.shape[1] == 0:
            raise ValueError("EEG data must contain at least one sample")

        object.__setattr__(self, "data", data)
        object.__setattr__(self, "sfreq", float(self.sfreq))
        object.__setattr__(self, "channel_names", channel_names)
        object.__setattr__(self, "source", str(self.source))
        object.__setattr__(self, "processing_metadata", tuple(self.processing_metadata))

    @property
    def duration_seconds(self):
        return self.data.shape[1] / self.sfreq

    def slice(self, start, end, channels=None):
        """Return a copied ``[channels, samples]`` window after strict checks."""

        try:
            start_seconds = float(start)
            end_seconds = float(end)
        except (TypeError, ValueError) as exc:
            raise ValueError("Start and end times must be finite numbers") from exc
        if not math.isfinite(start_seconds) or not math.isfinite(end_seconds):
            raise ValueError("Start and end times must be finite numbers")
        if start_seconds < 0:
            raise ValueError("Start time must be non-negative")
        if start_seconds == end_seconds:
            raise ValueError("EEG time window must not be empty")
        if start_seconds > end_seconds:
            raise ValueError("Start time must be earlier than end time")
        if end_seconds > self.duration_seconds:
            raise ValueError(
                f"EEG time window ends at {end_seconds:g}s, beyond record duration "
                f"{self.duration_seconds:g}s"
            )

        if channels is None:
            selected_names = self.channel_names
        elif isinstance(channels, str):
            selected_names = (channels,)
        else:
            selected_names = tuple(channels)
        if not selected_names:
            raise ValueError("At least one EEG channel must be selected")
        channel_index = {name: index for index, name in enumerate(self.channel_names)}
        missing = [name for name in selected_names if name not in channel_index]
        if missing:
            raise ValueError(f"Unknown EEG channel(s): {', '.join(missing)}")

        start_index = int(round(start_seconds * self.sfreq))
        end_index = int(round(end_seconds * self.sfreq))
        if start_index >= end_index:
            raise ValueError("EEG time window contains no samples at the record sampling rate")
        indices = [channel_index[name] for name in selected_names]
        return self.data[indices, start_index:end_index].copy()


EEGContext = EEGRecord

