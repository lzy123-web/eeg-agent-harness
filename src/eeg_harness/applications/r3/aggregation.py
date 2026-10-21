"""Explicit participant-level aggregation without file-name inference."""

from collections import defaultdict
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class RecordFeature:
    record_key: str
    participant_id: str
    values: dict[str, float]
    group: str | None = None


def aggregate_participants(records):
    """Average records within participant before any optional group description."""

    if not records:
        raise ValueError("At least one explicitly mapped record is required")
    by_participant = defaultdict(list)
    participant_groups = {}
    seen_record_keys = set()
    feature_names = None
    for item in records:
        if not item.record_key or not item.participant_id:
            raise ValueError("record_key and participant_id must be explicit")
        if item.record_key in seen_record_keys:
            raise ValueError(f"Duplicate record_key: {item.record_key}")
        seen_record_keys.add(item.record_key)
        names = tuple(sorted(item.values))
        feature_names = names if feature_names is None else feature_names
        if names != feature_names:
            raise ValueError("All records must contain the same feature names")
        values = np.asarray([item.values[name] for name in feature_names], dtype=float)
        if not np.isfinite(values).all():
            raise ValueError("Feature values must be finite")
        if item.participant_id in participant_groups and participant_groups[item.participant_id] != item.group:
            raise ValueError("A participant cannot have conflicting explicit groups")
        participant_groups[item.participant_id] = item.group
        by_participant[item.participant_id].append(values)
    participants = {}
    for participant_id, values in by_participant.items():
        mean = np.stack(values).mean(axis=0)
        participants[participant_id] = {
            "record_count": len(values),
            "group": participant_groups[participant_id],
            "features": dict(zip(feature_names, map(float, mean))),
        }
    return participants


def public_group_description(participants):
    """Return group-level means only; never expose participant IDs or their features."""

    if not participants or any(item["group"] is None for item in participants.values()):
        raise ValueError("Explicit participant-to-group mapping is required for group description")
    groups = defaultdict(list)
    for item in participants.values():
        names = sorted(item["features"])
        groups[item["group"]].append(np.asarray([item["features"][name] for name in names]))
    output = {}
    for group, values in groups.items():
        mean = np.stack(values).mean(axis=0)
        output[group] = {
            "participant_count": len(values),
            "participant_weighting": "equal after within-participant record mean",
            "feature_means": dict(zip(names, map(float, mean))),
        }
    return {"groups": output, "contains_participant_level_features": False}
