"""One read-only EEG consumer shared by both extensibility conditions."""

import numpy as np

from ...events import ArtifactConsistencyError
from ...tooling import ToolSpec
from ...tools import build_default_registry


ARTIFACT_SCHEMA = {
    "type": "object",
    "properties": {
        "artifact_id": {"type": "string"},
        "expected_artifact_fingerprint": {"type": "string"},
    },
    "required": ["artifact_id"],
    "additionalProperties": False,
}


def _epoch_variance(record, arguments, config, resources):
    artifact_id = arguments["artifact_id"]
    try:
        epochs = resources["artifact_store"][artifact_id]
    except KeyError as exc:
        raise LookupError(f"Epoch artifact not found: {artifact_id}") from exc
    fingerprint = epochs.content_fingerprint()
    expected = arguments.get("expected_artifact_fingerprint")
    if expected is not None and expected != fingerprint:
        raise ArtifactConsistencyError(
            "Epoch artifact content does not match the expected fingerprint"
        )
    conditions = {}
    for label in sorted(set(epochs.event_labels)):
        indices = [index for index, value in enumerate(epochs.event_labels) if value == label]
        data = epochs.data[indices]
        conditions[label] = {
            "epoch_count": len(indices),
            "channels": {
                channel: float(np.var(data[:, channel_index, :], dtype=np.float64, ddof=0))
                for channel_index, channel in enumerate(epochs.channel_names)
            },
        }
    return {
        "artifact_id": epochs.artifact_id,
        "artifact_fingerprint": fingerprint,
        "method": "population_variance_ddof_0_across_epochs_and_time",
        "unit": "signal_unit_squared",
        "conditions": conditions,
    }


def build_extensibility_registry():
    registry = build_default_registry()
    registry.register(ToolSpec(
        name="epoch_variance",
        description=(
            "Compute population variance (ddof=0) per event condition and EEG channel "
            "from one existing Epoch artifact; this is a descriptive read-only statistic."
        ),
        parameters=ARTIFACT_SCHEMA,
        return_type="object",
        compatible_profiles=("*",),
        handler=_epoch_variance,
        consumes_artifact="epochs",
    ))
    return registry
