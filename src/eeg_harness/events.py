"""Generic event and epoch data structures with explicit EEG time semantics."""

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Mapping, Optional
from uuid import uuid4

import numpy as np

from .provenance import source_reference


class EventError(ValueError):
    pass


class EpochError(ValueError):
    pass


class ArtifactConsistencyError(ValueError):
    """An artifact no longer matches the version declared by its consumer."""

    pass


@dataclass(frozen=True)
class EEGEvent:
    label: str
    onset_seconds: float
    duration_seconds: float = 0.0
    source_index: Optional[int] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "label": self.label,
            "onset_seconds": self.onset_seconds,
            "duration_seconds": self.duration_seconds,
            "source_index": self.source_index,
        }


@dataclass(frozen=True)
class EventSet:
    events: tuple[EEGEvent, ...]
    source: str
    time_reference: str = "seconds_from_record_start"

    @property
    def labels(self):
        return tuple(sorted({event.label for event in self.events}))

    def select(self, labels):
        requested = {labels} if isinstance(labels, str) else set(labels)
        if not requested:
            raise EventError("At least one event label must be selected")
        return tuple(event for event in self.events if event.label in requested)

    def summary(self):
        counts = {label: 0 for label in self.labels}
        for event in self.events:
            counts[event.label] += 1
        return {
            "event_count": len(self.events),
            "labels": counts,
            "time_reference": self.time_reference,
            "first_onset_seconds": self.events[0].onset_seconds if self.events else None,
            "last_onset_seconds": self.events[-1].onset_seconds if self.events else None,
            "source": source_reference(self.source),
        }


@dataclass(frozen=True)
class RejectedEpoch:
    label: str
    onset_seconds: float
    reason: str

    def to_dict(self):
        return {
            "label": self.label,
            "onset_seconds": self.onset_seconds,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class EpochSet:
    data: np.ndarray
    sfreq: float
    channel_names: tuple[str, ...]
    tmin: float
    tmax: float
    event_labels: tuple[str, ...]
    event_onsets_seconds: tuple[float, ...]
    baseline: Optional[tuple[Optional[float], Optional[float]]]
    rejected: tuple[RejectedEpoch, ...]
    source: str
    reference: str = "unspecified"
    artifact_id: str = field(default_factory=lambda: f"epochs-{uuid4()}")
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        data = np.asarray(self.data)
        if data.ndim != 3:
            raise ValueError(f"Epoch data must have shape [epochs, channels, times], got {data.shape}")
        object.__setattr__(self, "data", data)

    def content_fingerprint(self):
        """Bind scientific metadata and array content without exposing samples."""
        metadata = {
            "dtype": str(self.data.dtype),
            "shape": list(self.data.shape),
            "sfreq": self.sfreq,
            "channel_names": list(self.channel_names),
            "tmin": self.tmin,
            "tmax": self.tmax,
            "event_labels": list(self.event_labels),
            "event_onsets_seconds": list(self.event_onsets_seconds),
            "baseline": self.baseline,
            "reference": self.reference,
            "rejected": [item.to_dict() for item in self.rejected],
            "parameters": dict(self.parameters),
        }
        digest = hashlib.sha256()
        digest.update(json.dumps(
            metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8"))
        digest.update(np.ascontiguousarray(self.data).tobytes())
        return f"sha256:{digest.hexdigest()}"

    def summary(self):
        return {
            "artifact_id": self.artifact_id,
            "artifact_fingerprint": self.content_fingerprint(),
            "valid_epoch_count": int(self.data.shape[0]),
            "rejected_epoch_count": len(self.rejected),
            "shape": list(self.data.shape),
            "channel_names": list(self.channel_names),
            "sfreq": self.sfreq,
            "tmin": self.tmin,
            "tmax": self.tmax,
            "baseline": list(self.baseline) if self.baseline is not None else None,
            "reference": self.reference,
            "event_labels": list(self.event_labels),
            "event_onsets_seconds": list(self.event_onsets_seconds),
            "rejected": [item.to_dict() for item in self.rejected],
            "source": source_reference(self.source),
            "parameters": dict(self.parameters),
        }


def events_from_mne_raw(raw, source):
    events = []
    first_time = float(raw.first_time)
    for index, annotation in enumerate(raw.annotations):
        onset = float(annotation["onset"]) - first_time
        events.append(
            EEGEvent(
                label=str(annotation["description"]),
                onset_seconds=onset,
                duration_seconds=float(annotation["duration"]),
                source_index=index,
                metadata={"raw_annotation_onset": float(annotation["onset"])},
            )
        )
    events.sort(key=lambda item: (item.onset_seconds, item.source_index or 0))
    return EventSet(tuple(events), source=str(source))


def create_epoch_set(record, labels, tmin, tmax, baseline=None):
    if record.events is None or not record.events.events:
        raise EventError("EEG record has no events or annotations")
    tmin = float(tmin)
    tmax = float(tmax)
    if not np.isfinite(tmin) or not np.isfinite(tmax) or tmin >= tmax:
        raise EpochError("Epoch window requires finite tmin < tmax")
    selected = record.events.select(labels)
    if not selected:
        raise EventError("No events match the requested labels")

    resolved_baseline = None
    if baseline is not None:
        if len(baseline) != 2:
            raise EpochError("Baseline must contain exactly two values")
        baseline_start = tmin if baseline[0] is None else float(baseline[0])
        baseline_end = tmax if baseline[1] is None else float(baseline[1])
        if not np.isfinite(baseline_start) or not np.isfinite(baseline_end):
            raise EpochError("Baseline bounds must be finite")
        if baseline_start < tmin or baseline_end > tmax or baseline_start >= baseline_end:
            raise EpochError("Baseline must be a non-empty interval inside the Epoch window")
        resolved_baseline = (baseline[0], baseline[1])

    epoch_samples = int(round((tmax - tmin) * record.sfreq))
    if epoch_samples <= 0:
        raise EpochError("Epoch window contains no samples at the record sampling rate")
    accepted_data = []
    accepted_labels = []
    accepted_onsets = []
    rejected = []
    total_samples = record.data.shape[1]
    for event in selected:
        start_index = int(round((event.onset_seconds + tmin) * record.sfreq))
        end_index = start_index + epoch_samples
        if start_index < 0 or end_index > total_samples:
            rejected.append(RejectedEpoch(event.label, event.onset_seconds, "OUT_OF_RECORD_BOUNDS"))
            continue
        epoch = record.data[:, start_index:end_index].astype(np.float32, copy=True)
        if epoch.shape[1] != epoch_samples:
            rejected.append(RejectedEpoch(event.label, event.onset_seconds, "INCOMPLETE_EPOCH"))
            continue
        if baseline is not None:
            baseline_start = tmin if baseline[0] is None else float(baseline[0])
            baseline_end = tmax if baseline[1] is None else float(baseline[1])
            start_offset = int(round((baseline_start - tmin) * record.sfreq))
            end_offset = int(round((baseline_end - tmin) * record.sfreq))
            if start_offset >= end_offset:
                raise EpochError("Baseline contains no samples at the record sampling rate")
            epoch -= epoch[:, start_offset:end_offset].mean(axis=1, keepdims=True)
        accepted_data.append(epoch)
        accepted_labels.append(event.label)
        accepted_onsets.append(event.onset_seconds)

    if not accepted_data:
        raise EpochError("No valid Epochs remain after boundary checks")
    data = np.stack(accepted_data).astype(np.float32, copy=False)
    return EpochSet(
        data=data,
        sfreq=record.sfreq,
        channel_names=record.channel_names,
        tmin=tmin,
        tmax=tmax,
        event_labels=tuple(accepted_labels),
        event_onsets_seconds=tuple(accepted_onsets),
        baseline=resolved_baseline,
        rejected=tuple(rejected),
        source=record.source,
        reference=record.reference,
        parameters={
            "selected_labels": [labels] if isinstance(labels, str) else list(labels),
            "window_semantics": "[event_onset+tmin, event_onset+tmax)",
            "sampling_alignment": "round(seconds * sfreq)",
            "event_source": source_reference(record.events.source),
        },
    )

