"""Versioned, offline-first task-memory selection over the shared EEG session.

This is a lightweight HiAgent/LongMemEval-inspired adapter, not either paper's
implementation. F/S/G/E differ only in working-context organization and rank.
"""

from dataclasses import dataclass, replace
import json
import re

import numpy as np
from scipy.signal import welch

from ..events import EEGEvent, EventSet
from .integrated_method.v3 import EVENT_CAPABILITIES, RESULT_UNITS
from .task_memory import CONFIG, MultiTurnEEGSession, live_turn, synthetic_records


def protocol_records(script):
    """Relabel the synthetic fixture from protocol metadata, not query code."""
    output = synthetic_records()
    for alias, labels in script["event_labels"].items():
        original = output[alias]
        names = tuple(dict.fromkeys(event.label for event in original.events.events))
        if len(labels) != len(names) or len(set(labels)) != len(labels):
            raise ValueError("Protocol event labels must map bijectively")
        mapping = dict(zip(names, labels))
        output[alias] = replace(original,
            data=original.data.copy(),
            metadata={**original.metadata, "protocol_event_labels": list(labels)},
            events=EventSet(tuple(
                EEGEvent(mapping[event.label], event.onset_seconds,
                         duration_seconds=event.duration_seconds,
                         source_index=event.source_index,
                         metadata=event.metadata)
                for event in original.events.events), original.events.source),
        )
    return output


def _tokens(value):
    """Language-agnostic word/number and CJK bigram overlap, no task phrases."""
    text = str(value).casefold()
    output = re.findall(r"[a-z]+(?:[-_][a-z0-9]+)*|\d+(?:\.\d+)?", text)
    for span in re.findall(r"[\u3400-\u9fff]+", text):
        output.extend(span[index:index + 2] for index in range(len(span) - 1))
    return frozenset(output)


def _visible_mention(text, value):
    token = str(value).casefold()
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])",
                          text.casefold()))


def _scalar_paths(value, prefix=()):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _scalar_paths(child, prefix + (str(key),))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _scalar_paths(child, prefix + (str(index),))
    elif isinstance(value, (str, int, float, bool)) and not isinstance(value, bool):
        yield prefix


def _summary(entry):
    """Generic completed-task abstract; raw values remain in common read_task."""
    return {**entry.card(compact=True),
            "request": entry.user_text,
            "source": entry.evidence["source"],
            "source_stage": entry.evidence["source_stage"],
            "unit_or_kind": entry.evidence["unit_or_kind"],
            "analysis_configuration": entry.evidence["analysis_configuration"],
            "result_fields": ["/".join(path) for path in _scalar_paths(entry.result)][:24],
            "read_task_id": entry.task_id}


def _full_card(entry):
    return {**entry.card(), "source": entry.evidence["source"],
            "source_stage": entry.evidence["source_stage"],
            "unit_or_kind": entry.evidence["unit_or_kind"],
            "analysis_configuration": entry.evidence["analysis_configuration"]}


@dataclass(frozen=True)
class Query:
    text: str
    records: tuple[str, ...]
    parameter_values: tuple[str, ...]
    event_labels: tuple[str, ...]
    channels: tuple[str, ...]
    window: tuple[float, float] | None
    version: str | None
    scientific_scope: str | None
    tokens: frozenset[str]


def parse_visible_query(session, text):
    """Use only current request and real record/task metadata; no gold IDs."""
    records = tuple(alias for alias in session.records if _visible_mention(text, alias))
    channels = tuple(dict.fromkeys(name for record in session.records.values()
                                       for name in record.channel_names
                                       if _visible_mention(text, name)))
    event_labels = tuple(dict.fromkeys(event.label for record in session.records.values()
                                         for event in record.events.events
                                         if _visible_mention(text, event.label)))
    values = tuple(dict.fromkeys(str(value) for entry in session.entries
                                for value in entry.parameters.values()
                                for value in (value if isinstance(value, list) else [value])
                                if isinstance(value, str) and _visible_mention(text, value)))
    times = re.search(r"(\d+(?:\.\d+)?)\s*(?:到|至|[-~])\s*"
                      r"(\d+(?:\.\d+)?)\s*(?:秒|s\b)", text.casefold())
    window = (float(times[1]), float(times[2])) if times else None
    # Generic temporal update language is identical in G and E.
    old = bool(re.search(r"修改前|最初|原来|旧(?:版|结果)?|\bbefore\b|\boriginal\b", text.casefold()))
    new = bool(re.search(r"修改后|最新|新(?:版|结果)?|\bafter\b|\brevised\b", text.casefold()))
    version = "old" if old and not new else "new" if new and not old else None
    # These are scientific *scope* terms, never synthetic event label names.
    event_scope = bool(event_labels or re.search(r"事件|试次|\bepoch\b|\bevent\b", text.casefold()))
    continuous_scope = bool(re.search(r"连续|\bcontinuous\b", text.casefold()))
    scope = "event" if event_scope and not continuous_scope else (
        "continuous" if continuous_scope and not event_scope else None)
    return Query(text, records, values, event_labels, channels, window,
                 version, scope, _tokens(text))


def _generic_score(entry, query, entries):
    """Strong generic field/text/time/version retrieval shared by G and E."""
    summary = _summary(entry)
    corpus = _tokens(json.dumps(summary, ensure_ascii=False))
    lexical = len(query.tokens & corpus) / max(1, len(query.tokens))
    score = 4.0 * lexical
    if query.records:
        score += 3.0 if entry.record in query.records else -2.0
    field_values = {str(value) for value in entry.parameters.values()
                    for value in (value if isinstance(value, list) else [value])
                    if isinstance(value, str)}
    score += 1.5 * len(set(query.parameter_values) & field_values)
    if query.window:
        values = set(float(value) for value in entry.parameters.values()
                     if isinstance(value, (int, float)) and not isinstance(value, bool))
        score += 2.0 if set(query.window) <= values else -0.5
    if query.version:
        has_child = any(other.revision_of == entry.task_id for other in entries)
        version_match = has_child if query.version == "old" else entry.revision_of is not None
        score += 3.0 if version_match else -1.5
    # Sequence is a tie break, not a substitute for version resolution.
    return score + entry.sequence * 0.0001


def _scientific_bonus(entry, query):
    """EEG-only scope consistency from actual task parameters/record labels."""
    event = entry.capability in EVENT_CAPABILITIES
    score = 0.0
    if query.scientific_scope:
        score += 2.0 if (query.scientific_scope == "event") == event else -2.0
    if query.event_labels:
        labels = set(entry.parameters.get("labels", ()))
        score += 2.0 if labels & set(query.event_labels) else -1.0
    if query.channels and not event:
        channels = set(entry.parameters.get("channels", ()))
        score += 1.0 if channels & set(query.channels) else -0.5
    return score


def select_context_v2(session, text, policy, *, top_k=3):
    """Select task chunks; all arms share complete source entries and read API."""
    if top_k < 1:
        raise ValueError("top_k must be positive")
    entries = session.entries
    archive_count = max(0, len(entries) - top_k)
    summary_triggered = policy == "S" and archive_count > 0
    if policy == "F":
        cards = [_full_card(entry) for entry in entries]
        ranked = [entry.task_id for entry in entries]
    elif policy == "S":
        cards = ([{"rolling_summary": [_summary(entry) for entry in entries[:-top_k]]}]
                 if archive_count else [])
        cards.extend(_full_card(entry) for entry in entries[-top_k:])
        ranked = [entry.task_id for entry in entries]
    elif policy in {"G", "E", "E-no-science"}:
        query = parse_visible_query(session, text)
        ranked_entries = sorted(entries, key=lambda entry: (
            _generic_score(entry, query, entries)
            + (_scientific_bonus(entry, query) if policy == "E" else 0.0)),
            reverse=True)
        ranked = [entry.task_id for entry in ranked_entries]
        cards = [_full_card(entry) for entry in ranked_entries[:top_k]]
    else:
        raise ValueError("Unknown memory policy")
    payload = {"active_record": session.active_record, "record_aliases": sorted(session.records),
               "cards": cards, "archive_count": archive_count,
               "read_interface": "read_task(task_id)"}
    if policy == "F":
        payload["full_messages"] = list(session.messages)
        payload["full_tool_results"] = [list(entry.tool_trace) for entry in entries]
    visible = ranked if policy in {"F", "S"} else ranked[:top_k]
    serialized = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    return {"payload": payload, "ranked_task_ids": ranked,
            "shown_task_ids": visible, "summary_triggered": summary_triggered,
            "archive_count": archive_count, "characters": len(serialized),
            "estimated_tokens": (len(serialized) + 3) // 4}


def live_turn_v2(session, policy, text, client, *, deliver_answer=False):
    """Use the same model action and Executor interface with v2 context selection."""
    return live_turn(session, policy, text, client,
                     deliver_answer=deliver_answer, selector=select_context_v2)


def build_protocol_session(script):
    """Execute script steps once; target keys are not passed to session memory."""
    session = MultiTurnEEGSession(script["id"], protocol_records(script))
    keys = {}
    for step in script["steps"]:
        parent = keys[step["revision_of"]].task_id if "revision_of" in step else None
        result = session.analyze(step["record"], step["capability"],
                                 step["parameters"], step["text"], revision_of=parent)
        if result["status"] != "completed":
            raise RuntimeError(f"Protocol tool execution failed at {step['key']}: {result}")
        keys[step["key"]] = session.entries[-1]
    return session, keys


def _nested(result, path):
    value = result
    for part in path:
        value = value[part]
    return value


def independent_oracle(record, step, field):
    """Compute requested scalar from raw synthetic samples, not ToolResult."""
    capability = step["capability"]
    params = step["parameters"]
    if capability in {"psd", "amplitude"}:
        channel = field[0]
        samples = record.slice(params["start"], params["end"], [channel])[0]
        if capability == "amplitude":
            if field[1] != "rms":
                raise ValueError("Only independently specified RMS is supported")
            return float(np.sqrt(np.mean(np.square(samples.astype(float)))))
        band = field[1]
        frequencies, density = welch(samples, fs=record.sfreq,
                                     nperseg=min(len(samples), int(round(record.sfreq))))
        low, high = CONFIG["freq_bands"][band]
        selected = (frequencies >= low) & (frequencies <= high)
        return float(np.trapz(density[selected], frequencies[selected]))
    if capability in EVENT_CAPABILITIES:
        labels = set(params["labels"])
        onsets = [event.onset_seconds for event in record.events.events
                  if event.label in labels and
                  0 <= event.onset_seconds + params["tmin"] and
                  event.onset_seconds + params["tmax"] <= record.duration_seconds]
        if capability == "epoch_summary":
            if field != ["valid_epoch_count"]:
                raise ValueError("Only independent valid-Epoch count is supported")
            return len(onsets)
        if capability == "event_bandpower":
            if field[:2] != ["conditions", params["labels"][0]]:
                raise ValueError("Oracle field must match event condition")
            channel, band = field[3], field[4]
            low, high = CONFIG["freq_bands"][band]
            powers = []
            for onset in onsets:
                samples = record.slice(onset + params["tmin"],
                                       onset + params["tmax"], [channel])[0]
                frequencies, density = welch(samples, fs=record.sfreq,
                                             nperseg=min(len(samples), int(round(record.sfreq))))
                selected = (frequencies >= low) & (frequencies <= high)
                powers.append(np.trapz(density[selected], frequencies[selected]))
            return float(np.mean(powers))
    raise ValueError("No independent oracle for this protocol capability")


def score_read_semantics(session, script, query, keys, candidate_id, *,
                         observed_read=None):
    """Check scope, version, source, unit and independent scalar beyond task ID."""
    target_step = next(step for step in script["steps"] if step["key"] == query["target"])
    target = keys[query["target"]]
    observed = (observed_read if observed_read is not None else
                session.read_task(candidate_id, query["text"], record_message=False))
    expected_parent = (keys[target_step["revision_of"]].task_id
                       if "revision_of" in target_step else None)
    expected_source = session.records[target_step["record"]].source
    checks = {
        "task_id": observed.get("task_id") == target.task_id,
        "record": observed.get("record") == target_step["record"],
        "capability": observed.get("capability") == target_step["capability"],
        "parameters": observed.get("parameters") == target_step["parameters"],
        "revision": observed.get("revision_of") == expected_parent,
        "source": observed.get("source") == expected_source,
        "unit": observed.get("unit_or_kind") == RESULT_UNITS[target_step["capability"]],
    }
    try:
        actual = float(_nested(observed["result"], query["field"]))
        oracle = independent_oracle(session.records[target_step["record"]],
                                    target_step, query["field"])
        checks["value"] = bool(np.isclose(actual, oracle, rtol=5e-3, atol=5e-13))
    except (KeyError, IndexError, TypeError, ValueError):
        actual, oracle = None, None
        checks["value"] = False
    return {"valid": all(checks.values()), "checks": checks,
            "observed_value": actual, "oracle_value": oracle,
            "target_key": query["target"], "candidate_id": candidate_id}


def classify_action_failure(expected_operation, observed_operation, *,
                            expected_history_written=True,
                            target_visible=True, target_correct=True):
    """Do not misattribute a common analyze/switch error to retrieval."""
    if expected_operation != observed_operation:
        return "common_action_selection_error"
    if expected_operation == "history" and not expected_history_written:
        return "history_absent_after_prior_failure"
    if expected_operation == "history" and not target_visible:
        return "memory_selection_miss"
    if expected_operation == "history" and not target_correct:
        return "model_read_or_evidence_error"
    return "correct"


def score_observed_history_turn(session, script, query, observed):
    """Future live scorer: resolve expected evidence semantically, not by ID order."""
    action = observed.get("action") or {}
    outcome = observed.get("outcome") or {}
    operation = action.get("operation")
    if operation != "history":
        return {"valid": False, "category": "common_action_selection_error"}
    resolved = {}
    used = set()
    for step in script["steps"]:
        parent = resolved.get(step.get("revision_of"))
        match = next((entry for entry in session.entries
                      if entry.task_id not in used
                      and entry.record == step["record"]
                      and entry.capability == step["capability"]
                      and entry.parameters == step["parameters"]
                      and ("revision_of" not in step or
                           parent is not None and entry.revision_of == parent.task_id)
                      and ("revision_of" in step or entry.revision_of is None)), None)
        if match:
            resolved[step["key"]] = match
            used.add(match.task_id)
    target = resolved.get(query["target"])
    if target is None:
        return {"valid": False, "category": "history_absent_after_prior_failure"}
    shown = observed.get("shown_task_ids") or []
    if target.task_id not in shown:
        return {"valid": False, "category": "memory_selection_miss"}
    score = score_read_semantics(session, script, query, resolved,
                                 outcome.get("task_id"), observed_read=outcome)
    return {"valid": score["valid"],
            "category": "correct" if score["valid"] else "model_read_or_evidence_error",
            "semantic_read": score}


def replay_protocol_v2(script, policies=("F", "S", "G", "E", "E-no-science")):
    """One real-tool history, separate context choices and semantic reads."""
    session, keys = build_protocol_session(script)
    rows = []
    for policy in policies:
        queries = []
        for query in script["queries"]:
            selection = select_context_v2(session, query["text"], policy,
                                          top_k=3)
            target_id = keys[query["target"]].task_id
            ranked = selection["ranked_task_ids"]
            shown = selection["shown_task_ids"]
            top_candidate = ranked[0] if ranked else None
            read = (score_read_semantics(session, script, query, keys, top_candidate)
                    if top_candidate else None)
            target_read = (score_read_semantics(session, script, query, keys, target_id)
                           if target_id in shown else None)
            queries.append({
                "query": query["text"], "target_key": query["target"],
                "target_visible": target_id in shown,
                "top1_semantically_correct": bool(read and read["valid"]),
                "top1_read": read,
                "target_read": target_read,
                "shown_count": len(shown), "history_count": len(session.entries),
                "summary_triggered": selection["summary_triggered"],
                "archived_count": selection["archive_count"],
                "context_characters": selection["characters"],
                "context_token_proxy": selection["estimated_tokens"],
            })
        rows.append({"session_id": script["id"], "policy": policy,
                     "task_count": len(session.entries), "queries": queries})
    return rows
