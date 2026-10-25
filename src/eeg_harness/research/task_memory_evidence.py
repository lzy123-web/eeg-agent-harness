"""Shared, bounded evidence handoff for EEG task-memory answer turns.

This is a public consumption contract over immutable TaskEntry results, not a
new executor, memory ranking policy, or numerical analysis method.
"""

import json
import re
import time

from .task_memory_issue41 import _encoded
from .task_memory_v2 import parse_visible_query
from .task_memory_v3 import EVENT_CAPABILITIES, scientific_read_mismatch


MAX_EVIDENCE_TASKS = 8
MAX_EVIDENCE_BYTES = 24000


def scalar_paths(value, prefix=()):
    """Canonical paths are relative to TaskEntry.result; list indices stay int."""
    if isinstance(value, dict):
        for key, child in value.items():
            yield from scalar_paths(child, prefix + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from scalar_paths(child, prefix + (index,))
    elif value is None or type(value) in {str, int, float, bool}:
        yield list(prefix), value


def visible_cards(payload):
    for card in payload.get("cards", ()):
        if "rolling_summary" in card:
            yield from card["rolling_summary"]
        else:
            yield card
    yield from payload.get("working_tasks", ())
    yield from payload.get("completed_index", ())
    if payload.get("focused_evidence"):
        yield payload["focused_evidence"]


def add_readable_paths(session, selected):
    """The displayed path is exactly the path accepted by read_task_fields."""
    by_id = {entry.task_id: entry for entry in session.entries}
    for card in visible_cards(selected["payload"]):
        entry = by_id.get(card.get("task_id"))
        if entry is None:
            continue
        paths = [path for path, _ in scalar_paths(entry.result)]
        card["readable_fields"] = paths[:64]
        card["readable_fields_truncated"] = len(paths) > 64
        card.pop("field_index", None)
        card.pop("result_fields", None)
    encoded = _encoded(selected["payload"])
    return {**selected, "characters": len(encoded),
            "estimated_tokens": (len(encoded) + 3) // 4}


def _entry_meta(entry):
    return {"task_id": entry.task_id, "record": entry.record,
            "capability": entry.capability, "parameters": entry.parameters,
            "revision_of": entry.revision_of, "source": entry.evidence["source"],
            "source_stage": entry.evidence["source_stage"],
            "analysis_configuration": entry.evidence["analysis_configuration"],
            "unit_or_kind": entry.evidence["unit_or_kind"],
            "evidence_token": entry.evidence["evidence_token"]}


def _same_value(a, b):
    return _encoded(a) == _encoded(b)


def exact_visible(session, selected):
    """Only actual first-message exact values; an index is not evidence."""
    by_id = {entry.task_id: entry for entry in session.entries}
    found = {}
    for card in visible_cards(selected["payload"]):
        task_id = card.get("task_id")
        entry = by_id.get(task_id)
        if entry is None:
            continue
        result = card.get("exact_result", card.get("result_preview"))
        if result is None:
            continue
        if not _same_value(result, entry.result):
            raise ValueError("Visible result differs from immutable TaskEntry")
        found[task_id] = {**_entry_meta(entry), "fields": [
            {"path": path, "value": value, "via": ["first_visible"]}
            for path, value in scalar_paths(result)]}
    focused = selected["payload"].get("focused_field_evidence")
    if focused and focused.get("status") == "read_fields":
        entry = by_id.get(focused.get("task_id"))
        if entry:
            row = found.setdefault(entry.task_id, {**_entry_meta(entry), "fields": []})
            for field in focused.get("fields", ()):
                row["fields"].append({"path": field["path"], "value": field["value"],
                                      "via": ["first_visible"]})
    return list(found.values())


def normalized_read(session, read):
    """Reject malformed successful reads; never promote errors to exact values."""
    if read.get("status") not in {"read", "read_fields"}:
        return None
    entry = next((item for item in session.entries
                  if item.task_id == read.get("task_id")), None)
    if entry is None:
        raise ValueError("Successful read without stored task")
    if any(read.get(key) != value for key, value in _entry_meta(entry).items()
           if key in read):
        raise ValueError("Read provenance differs from immutable TaskEntry")
    if read["status"] == "read":
        if not _same_value(read.get("result"), entry.result):
            raise ValueError("Read result differs from immutable TaskEntry")
        values = list(scalar_paths(read["result"]))
        via = "read_full"
    else:
        values = []
        for field in read.get("fields", ()):
            path = field.get("path")
            if not isinstance(path, list):
                raise ValueError("Malformed field read path")
            actual = entry.result
            for key in path:
                actual = actual[key]
            if not _same_value(actual, field.get("value")):
                raise ValueError("Field read differs from immutable TaskEntry")
            values.append((path, field["value"]))
        via = "read_fields"
    return {**_entry_meta(entry), "fields": [
        {"path": path, "value": value, "via": [via]} for path, value in values]}


def merge_evidence(visible, reads):
    """Union on (task_id, canonical path), preserve versions and acquisition route."""
    started = time.perf_counter()
    merged = {}
    for item in list(visible) + [read for read in reads if read is not None]:
        task_id = item["task_id"]
        if task_id not in merged:
            merged[task_id] = {key: value for key, value in item.items()
                               if key != "fields"}
            merged[task_id]["fields"] = {}
        else:
            for key, value in item.items():
                if key != "fields" and not _same_value(merged[task_id][key], value):
                    raise ValueError("Conflicting evidence provenance")
        for field in item["fields"]:
            key = _encoded(field["path"]).decode("utf-8")
            previous = merged[task_id]["fields"].get(key)
            if previous is None:
                merged[task_id]["fields"][key] = dict(field)
            elif not _same_value(previous["value"], field["value"]):
                raise ValueError("Conflicting exact field values")
            else:
                previous["via"] = list(dict.fromkeys(previous["via"] + field["via"]))
    if len(merged) > MAX_EVIDENCE_TASKS:
        return {"status": "overflow", "code": "EVIDENCE_TASK_LIMIT"}, 0
    output = [dict(item, fields=list(item["fields"].values()))
              for item in merged.values()]
    if len(_encoded(output)) > MAX_EVIDENCE_BYTES:
        return {"status": "overflow", "code": "EVIDENCE_BYTE_LIMIT"}, 0
    return {"status": "ok", "items": output}, (time.perf_counter() - started) * 1000


def _windows(text):
    return tuple(dict.fromkeys((float(a), float(b)) for a, b in re.findall(
        r"(\d+(?:\.\d+)?)\s*(?:到|至|[-–—~])\s*"
        r"(\d+(?:\.\d+)?)\s*(?:秒|s\b)", text.casefold())))


def bind_read_scope(session, entry, request, scope):
    """Bind one object in a multi-object request without gold or verbatim quote.

    A scope claim must be present in the user's request and match the stored
    task. Missing distinctions are rejected instead of guessed.
    """
    if scope is None:
        scope = {}
    if not isinstance(scope, dict):
        return None, "INVALID_SCOPE"
    query = parse_visible_query(session, request)
    records = query.records
    record = scope.get("record")
    if len(records) > 1 and record is None:
        return None, "RECORD_BINDING_REQUIRED"
    if record is not None and record not in records:
        return None, "UNREQUESTED_RECORD"
    if len(records) == 1 and entry.record != records[0]:
        return None, "SCIENTIFIC_SCOPE_MISMATCH"
    if record is not None and record != entry.record:
        return None, "SCIENTIFIC_SCOPE_MISMATCH"
    if not records and len({item.record for item in session.entries}) > 1:
        return None, "AMBIGUOUS_RECORD"

    event = entry.capability in EVENT_CAPABILITIES
    mentions_event = bool(query.event_labels or re.search(r"事件|试次|\bepoch\b|\bevent\b",
                                                    request.casefold()))
    mentions_cont = bool(re.search(r"连续|\bcontinuous\b", request.casefold()))
    kind = scope.get("kind")
    if mentions_event and mentions_cont and kind is None:
        return None, "KIND_BINDING_REQUIRED"
    if kind is not None and (kind not in {"event", "continuous"}
                             or (kind == "event") != event
                             or (kind == "event" and not mentions_event)
                             or (kind == "continuous" and not mentions_cont)):
        return None, "SCIENTIFIC_SCOPE_MISMATCH"
    if not mentions_event and not mentions_cont and len({
            item.capability in EVENT_CAPABILITIES for item in session.entries}) > 1:
        return None, "AMBIGUOUS_TIME_BASE"
    if mentions_event != mentions_cont and (event != mentions_event):
        return None, "SCIENTIFIC_SCOPE_MISMATCH"

    labels = query.event_labels
    label = scope.get("condition")
    if event and len(labels) > 1 and label is None:
        return None, "CONDITION_BINDING_REQUIRED"
    if label is not None and (label not in labels
                              or label not in entry.parameters.get("labels", ())):
        return None, "SCIENTIFIC_SCOPE_MISMATCH"
    if event and len(labels) == 1 and labels[0] not in entry.parameters.get("labels", ()):
        return None, "SCIENTIFIC_SCOPE_MISMATCH"

    available = set(entry.parameters.get("channels", ()))
    for condition in entry.result.get("conditions", {}).values():
        available.update(condition.get("channels", {}))
    channels = query.channels if available else ()
    channel = scope.get("channel")
    if not available and channel is not None:
        return None, "SCIENTIFIC_SCOPE_MISMATCH"
    if len(channels) > 1 and channel is None:
        return None, "CHANNEL_BINDING_REQUIRED"
    if channel is not None and channel not in channels:
        return None, "UNREQUESTED_CHANNEL"
    chosen_channel = channel or (channels[0] if len(channels) == 1 else None)
    if chosen_channel is not None and chosen_channel not in available:
        return None, "SCIENTIFIC_SCOPE_MISMATCH"

    windows = _windows(request)
    selected_window = scope.get("window")
    if len(windows) > 1 and selected_window is None:
        return None, "WINDOW_BINDING_REQUIRED"
    if selected_window is not None:
        if (not isinstance(selected_window, list) or len(selected_window) != 2
                or any(type(x) not in {int, float} for x in selected_window)
                or tuple(map(float, selected_window)) not in windows):
            return None, "UNREQUESTED_WINDOW"
        window = tuple(map(float, selected_window))
    else:
        window = windows[0] if windows else None
    params = entry.parameters
    actual_window = ((params.get("tmin"), params.get("tmax")) if event else
                     (params.get("start"), params.get("end")))
    if window is not None and tuple(map(float, actual_window)) != window:
        return None, "SCIENTIFIC_SCOPE_MISMATCH"

    lower = request.casefold()
    old = bool(re.search(r"修改前|原来|旧(?:版|结果)?|\bbefore\b|\boriginal\b", lower))
    new = bool(re.search(r"修改后|最新|新(?:版|结果)?|\bafter\b|\brevised\b", lower))
    version = scope.get("version")
    has_child = any(item.revision_of == entry.task_id for item in session.entries)
    in_chain = bool(entry.revision_of or has_child)
    if old and new and in_chain and version is None:
        return None, "VERSION_BINDING_REQUIRED"
    if version is not None and (version not in {"old", "new"}
                                or (version == "old" and not old)
                                or (version == "new" and not new)):
        return None, "UNREQUESTED_VERSION"
    version = version or ("old" if old and not new and in_chain else
                          "new" if new and not old and in_chain else None)
    if version == "old" and not has_child or version == "new" and not entry.revision_of:
        return None, "SCIENTIFIC_SCOPE_MISMATCH"
    if version is None and any(item.revision_of == entry.task_id or
                               entry.revision_of == item.task_id for item in session.entries):
        same = [item for item in session.entries if item.record == entry.record and
                item.capability == entry.capability and item.parameters == entry.parameters]
        if len(same) > 1:
            return None, "AMBIGUOUS_VERSION"

    # Reuse the existing public read guard after object-specific validation.
    parts = [entry.record, "事件" if event else "连续"]
    if label or len(labels) == 1:
        parts.append(label or labels[0])
    if chosen_channel:
        parts.append(chosen_channel)
    if window:
        parts.append(f"{window[0]:g} 到 {window[1]:g} 秒")
    if version:
        parts.append("修改前" if version == "old" else "修改后")
    text = " ".join(parts)
    if scientific_read_mismatch(session, entry, text):
        return None, "SCIENTIFIC_SCOPE_MISMATCH"
    return text, None
