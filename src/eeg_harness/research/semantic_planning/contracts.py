"""Reusable operation contracts shared by all three planning methods."""

from dataclasses import dataclass
from typing import Callable

from .models import ScientificRequirement, SemanticArtifact, SemanticEffect, stable_id


@dataclass(frozen=True)
class OperationContract:
    name: str
    goal_kinds: tuple[str, ...]
    effect: SemanticEffect
    apply: Callable[[SemanticArtifact, ScientificRequirement], tuple[SemanticArtifact | None, tuple[str, ...], str | None]]


def _derived(source, operation, requirement, **changes):
    data = dict(source.__dict__)
    data.update(changes)
    data["artifact_id"] = stable_id(operation, source.artifact_id, dict(requirement.parameters))
    data["parent_ids"] = (source.artifact_id,)
    return SemanticArtifact(**data)


def lowpass40(source, requirement):
    if source.kind != "record":
        return None, (), "INPUT_KIND_MISMATCH"
    target = float(requirement.parameters.get("require_lowpass_hz", 40.0))
    if target <= 0 or source.sfreq is None or source.sfreq / 2 <= target:
        return None, (), "INVALID_REQUIREMENT"
    current_high = None if source.passband_hz is None else source.passband_hz[1]
    if current_high is not None and current_high <= target + 1e-9:
        return source, (f"existing passband upper bound {current_high:g} Hz",), None
    output = _derived(
        source, "sp_lowpass", requirement, stage="lowpass",
        passband_hz=(None if source.passband_hz is None else source.passband_hz[0], target),
        filter_history=source.filter_history + (f"lowpass:{target:g}Hz",),
        observability=tuple({**dict(source.observability), "raw_line_noise": "false"}.items()),
    )
    return output, (f"Nyquist {source.sfreq / 2:g} Hz exceeds low-pass {target:g} Hz",), None


def resample_record(source, requirement):
    if source.kind != "record":
        return None, (), "INPUT_KIND_MISMATCH"
    target = float(requirement.parameters.get("target_sfreq", source.sfreq or 0))
    if target <= 0 or source.sfreq is None:
        return None, (), "INVALID_REQUIREMENT"
    if abs(target - source.sfreq) < 1e-12:
        return source, ("record already has requested sampling frequency",), None
    if not source.event_labels:
        return None, (), "EVENTS_UNAVAILABLE"
    output = _derived(
        source, "sp_resample_with_events", requirement, stage="resampled", sfreq=target,
        event_alignment_source="events jointly resampled from original sample coordinates",
        time_reference="seconds_from_record_start_on_resampled_grid",
    )
    return output, ("events exist", "events are jointly resampled with continuous data"), None


def create_epochs(source, requirement):
    if source.kind != "record":
        return None, (), "INPUT_KIND_MISMATCH"
    labels = tuple(requirement.parameters.get("labels", ()))
    if not source.event_labels:
        return None, (), "EVENTS_UNAVAILABLE"
    if not labels or any(label not in source.event_labels for label in labels):
        return None, (), "EVENT_LABEL_UNAVAILABLE"
    target = requirement.parameters.get("target_sfreq")
    if target is not None and abs(float(target) - float(source.sfreq)) > 1e-9:
        return None, (), "REQUIRED_SFREQ_MISSING"
    required_lowpass = requirement.parameters.get("require_lowpass_hz")
    if required_lowpass is not None:
        marker = f"lowpass:{float(required_lowpass):g}Hz"
        if marker not in source.filter_history:
            return None, (), "REQUIRED_PROCESSING_MISSING"
    tmin = float(requirement.parameters.get("tmin", -0.1))
    tmax = float(requirement.parameters.get("tmax", 0.4))
    if tmin >= tmax:
        return None, (), "INVALID_REQUIREMENT"
    counts = {label: source.counts().get(label, 0) for label in labels}
    labels_by_index = [
        label for label in source.get("event_labels_by_index", ()) if label in labels
    ]
    output = _derived(
        source, "sp_create_epochs", requirement, kind="epochs", stage="epoched",
        condition_counts=tuple(sorted(counts.items())),
        properties=tuple({
            "tmin": tmin, "tmax": tmax, "selected": False,
            "epoch_labels_by_index": labels_by_index,
        }.items()),
    )
    return output, ("event labels exist", "epoch window has tmin < tmax"), None


def select_epochs(source, requirement):
    if source.kind != "epochs":
        return None, (), "INPUT_KIND_MISMATCH"
    selection = requirement.parameters.get("selection")
    if not selection:
        return source, ("no selection requested",), None
    if not selection.get("authorized", False):
        return None, (), "SELECTION_NOT_AUTHORIZED"
    excluded = tuple(int(index) for index in selection.get("exclude_indices", ()))
    labels_by_index = tuple(source.get("epoch_labels_by_index", ()))
    if any(index < 0 or index >= len(labels_by_index) for index in excluded):
        return None, (), "INVALID_REQUIREMENT"
    counts = source.counts()
    for index in excluded:
        label = labels_by_index[index]
        counts[label] = counts.get(label, 0) - 1
    output = _derived(
        source, "sp_select_epochs", requirement, stage="selected",
        condition_counts=tuple(sorted(counts.items())),
        selection_history=source.selection_history + (
            f"user_authorized_exclude_indices:{','.join(map(str, excluded))}",
        ),
        properties=tuple({**dict(source.properties), "selected": True}.items()),
    )
    return output, ("selection explicitly authorized", "indices refer to input artifact"), None


def line_noise_feature(source, requirement):
    frequency = float(requirement.parameters.get("frequency_hz", 50.0))
    high = None if source.passband_hz is None else source.passband_hz[1]
    if source.kind != "record" or source.stage != "raw" or source.observable("raw_line_noise") != "true":
        return None, (), "RAW_SOURCE_UNAVAILABLE"
    if source.sfreq is None or source.sfreq / 2 <= frequency + 1 or (high is not None and high < frequency + 1):
        return None, (), "FREQUENCY_NOT_OBSERVABLE"
    output = _derived(
        source, "sp_line_noise", requirement, kind="feature", stage="feature",
        properties=(("feature_kind", "line_noise"), ("frequency_hz", frequency)),
    )
    return output, ("source stage is raw", "requested frequency is observable"), None


def bandpower_feature(source, requirement):
    if source.kind != "record":
        return None, (), "INPUT_KIND_MISMATCH"
    low = float(requirement.parameters.get("low_hz", 1.0))
    high = float(requirement.parameters.get("high_hz", 40.0))
    required_lowpass = requirement.parameters.get("require_lowpass_hz")
    pass_high = None if source.passband_hz is None else source.passband_hz[1]
    if low < 0 or low >= high or source.sfreq is None or high >= source.sfreq / 2:
        return None, (), "FREQUENCY_NOT_OBSERVABLE"
    if required_lowpass is not None and (source.stage != "lowpass" or pass_high is None or pass_high > float(required_lowpass) + 1e-9):
        return None, (), "REQUIRED_PROCESSING_MISSING"
    if pass_high is not None and pass_high < high:
        return None, (), "FREQUENCY_NOT_OBSERVABLE"
    output = _derived(
        source, "sp_bandpower", requirement, kind="feature", stage="feature",
        properties=(("feature_kind", "bandpower"), ("low_hz", low), ("high_hz", high)),
    )
    return output, ("requested band is inside Nyquist and declared passband",), None


def epoch_feature(source, requirement):
    if source.kind != "epochs":
        return None, (), "INPUT_KIND_MISMATCH"
    labels = tuple(requirement.parameters.get("labels", ()))
    minimum = int(requirement.parameters.get("min_trials_per_label", 1))
    selection = requirement.parameters.get("selection")
    if selection and not selection.get("authorized", False):
        return None, (), "SELECTION_NOT_AUTHORIZED"
    if selection and not source.get("selected", False):
        return None, (), "SELECTION_REQUIRED"
    counts = source.counts()
    if any(counts.get(label, 0) < minimum for label in labels):
        return None, (), "INSUFFICIENT_TRIALS"
    output = _derived(
        source, f"sp_{requirement.kind}", requirement, kind="feature", stage="feature",
        properties=(("feature_kind", requirement.kind), ("source_epoch_artifact_id", source.artifact_id)),
    )
    return output, ("requested labels have sufficient trials", "feature binds exact Epoch artifact"), None


def build_contracts(include_extension=True):
    shared = ("root_id", "reference", "channels")
    contracts = [
        OperationContract("sp_lowpass", ("bandpower", "condition_feature", "epoch_variance"), SemanticEffect("sp_lowpass", "record", "record", shared + ("events",), ("passband", "filter_history"), ("raw_line_noise",), ("processed branch cannot represent raw line-noise evidence",)), lowpass40),
        OperationContract("sp_resample_with_events", ("epochs", "condition_feature", "epoch_variance"), SemanticEffect("sp_resample_with_events", "record", "record", shared + ("event labels",), ("sfreq", "event sample coordinates"), (), ("event times are quantized to target sampling grid",)), resample_record),
        OperationContract("sp_create_epochs", ("epochs", "condition_feature", "epoch_variance"), SemanticEffect("sp_create_epochs", "record", "epochs", shared + ("sfreq",), ("time coordinate", "condition counts"), (), ("Epoch lineage binds event labels and window",)), create_epochs),
        OperationContract("sp_select_epochs", ("condition_feature", "epoch_variance"), SemanticEffect("sp_select_epochs", "epochs", "epochs", shared + ("sfreq",), ("condition counts", "selection history"), (), ("selection requires explicit user authorization",)), select_epochs),
        OperationContract("sp_line_noise", ("line_noise",), SemanticEffect("sp_line_noise", "record", "feature", shared, (), (), ("raw line noise requires an observable raw source",)), line_noise_feature),
        OperationContract("sp_bandpower", ("bandpower",), SemanticEffect("sp_bandpower", "record", "feature", shared, (), (), ("requested frequency must remain observable",)), bandpower_feature),
        OperationContract("sp_condition_feature", ("condition_feature",), SemanticEffect("sp_condition_feature", "epochs", "feature", shared + ("selection history",), (), (), ("minimum condition counts bind the exact input Epoch artifact",)), epoch_feature),
    ]
    if include_extension:
        contracts.append(OperationContract("sp_epoch_variance", ("epoch_variance",), SemanticEffect("sp_epoch_variance", "epochs", "feature", shared + ("selection history",), (), (), ("variance feature binds the exact input Epoch artifact",)), epoch_feature))
    return tuple(contracts)
