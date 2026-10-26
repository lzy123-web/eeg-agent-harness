"""Field-level contracts for the existing EEG tool return schemas.

These definitions come from tools.py, events.py and quality.py, not from a
tool-wide unit, an LLM claim, a case name or a future question. This deliberately
supports a limited set of well-defined fields. Unknown paths fail closed.
"""
import math


class UnsupportedResultField(ValueError):
    pass


def read_scalar(result, path):
    if (not isinstance(path, list) or not path or
            any(type(key) not in {str, int} or isinstance(key, int) and key < 0 for key in path)):
        raise UnsupportedResultField("Use a nonempty canonical scalar field path")
    value = result
    try:
        for key in path:
            value = value[key]
    except (KeyError, IndexError, TypeError) as exc:
        raise UnsupportedResultField("Field is absent from the actual result") from exc
    if value is not None and type(value) not in {str, float, int, bool}:
        raise UnsupportedResultField("Only a scalar can be stated")
    return value


def result_field_semantics(capability, path, result, *, parameters=None, analysis_configuration=None):
    """Return explicit semantics after checking the actual value's type.

    The returned unit_or_kind is a field quantity unit (V/V²/Hz/s), count,
    fraction, or metadata. It is never inherited from the whole tool result.
    Dynamic labels/channels/bands come from the actual output and its contract.
    """
    value = read_scalar(result, path)
    params, config = parameters or {}, analysis_configuration or {}
    p = tuple(path)
    spec = None

    def numeric(kind, unit, value_type="number"):
        return {"kind": kind, "unit_or_kind": unit, "value_type": value_type,
                "contract": "eeg_tool_scalar_v1"}

    if capability == "amplitude" and len(p) == 2:
        if p[0] in params.get("channels", ()) and p[1] in {"mean_abs", "rms", "max_val", "min_val"}:
            spec = numeric("amplitude", "V")
    elif capability == "psd" and len(p) == 2:
        if p[0] in params.get("channels", ()) and p[1] in config.get("freq_bands", {}):
            spec = numeric("absolute_band_power", "V²")
    elif capability == "event_bandpower":
        if p == ("frequency_resolution_hz",):
            spec = numeric("frequency_resolution", "Hz")
        elif len(p) >= 3 and p[0] == "conditions" and p[1] in params.get("labels", ()):
            if len(p) == 3 and p[2] == "epoch_count":
                spec = numeric("epoch_count", "count", "nonnegative_integer")
            elif len(p) == 5 and p[2] == "channels" and p[4] in config.get("freq_bands", {}):
                spec = numeric("mean_absolute_epoch_band_power", "V²")
        elif p in {("artifact_id",), ("artifact_fingerprint",), ("method",), ("interpretation",)}:
            spec = numeric("metadata", "metadata", "string")
    elif capability in {"record_info", "create_epochs", "epoch_summary"}:
        quantities = {"sfreq": ("sampling_frequency", "Hz", "number"),
                      "duration_seconds": ("duration", "s", "number"),
                      "sample_count": ("sample_count", "count", "nonnegative_integer"),
                      "channel_count": ("channel_count", "count", "nonnegative_integer"),
                      "valid_epoch_count": ("epoch_count", "count", "nonnegative_integer"),
                      "rejected_epoch_count": ("epoch_count", "count", "nonnegative_integer"),
                      "tmin": ("event_relative_time", "s", "number"),
                      "tmax": ("event_relative_time", "s", "number")}
        if len(p) == 1 and p[0] in quantities:
            spec = numeric(*quantities[p[0]])
        elif p in {("artifact_id",), ("artifact_fingerprint",), ("reference",), ("montage",)}:
            spec = numeric("metadata", "metadata", "string")
        elif len(p) == 2 and p[0] in {"channel_names", "event_labels"} and type(p[1]) is int:
            spec = numeric("metadata", "metadata", "string")
        elif len(p) == 2 and p[0] == "event_onsets_seconds" and type(p[1]) is int:
            spec = numeric("record_absolute_time", "s")
    elif capability == "epoch_quality":
        if len(p) == 2 and p[0] == "epoch_counts" and p[1] in {
                "requested_or_boundary_checked", "created", "boundary_rejected", "quality_flagged", "quality_usable"}:
            spec = numeric("epoch_count", "count", "nonnegative_integer")
        elif len(p) == 2 and p[0] in {"condition_counts_before_quality", "condition_counts_quality_usable"} and p[1] in params.get("labels", ()):
            spec = numeric("epoch_count", "count", "nonnegative_integer")
        elif p == ("usable_fraction_of_created",):
            spec = numeric("usable_fraction", "fraction", "fraction")
        elif p in {("evidence_id",), ("evidence_type",), ("profile_id",), ("source_stage",),
                   ("artifact_id",), ("artifact_fingerprint",), ("threshold_status",), ("validity",)}:
            spec = numeric("metadata", "metadata", "string")

    if spec is None:
        raise UnsupportedResultField("No registered field-level semantic contract; do not infer a unit")
    expected_type = spec["value_type"]
    if expected_type == "string":
        valid = isinstance(value, str)
    elif expected_type == "nonnegative_integer":
        valid = type(value) is int and value >= 0
    else:
        try:
            number = float(value)
            valid = type(value) in {str, int, float} and math.isfinite(number)
            if expected_type == "fraction":
                valid = valid and 0 <= number <= 1
        except (TypeError, ValueError):
            valid = False
    if not valid:
        raise UnsupportedResultField("Actual result violates its field-level value type")
    return spec
