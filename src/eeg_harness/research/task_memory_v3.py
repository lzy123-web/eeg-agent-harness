"""HiAgent-inspired task episodes over the existing EEG session and Executor.

This adapts task chunking and on-demand action/observation restoration, not
HiAgent's LLM subgoal generator or learned/proactive summarizer.
"""

import json

from .task_memory import MultiTurnEEGSession, live_turn
from .task_memory_v2 import (_full_card, _scalar_paths, score_read_semantics,
                             select_context_v2, build_protocol_session,
                             parse_visible_query)
from .integrated_method.v3 import EVENT_CAPABILITIES


class EpisodeMemorySession(MultiTurnEEGSession):
    """A failed analysis stays active; a completed one becomes immutable."""

    def __init__(self, session_id, records=None):
        super().__init__(session_id, records)
        self.active_task = None
        self.focused_task_id = None
        self.task_summaries = {}
        self.lifecycle = []
        self.evidence_reads = 0

    def analyze(self, alias, capability, parameters, text, *, revision_of=None):
        pending = self.active_task
        continuation = bool(pending and pending["state"] == "blocked"
                            and (pending["record"], pending["capability"],
                                 pending["revision_of"]) ==
                            (alias, capability, revision_of))
        if not continuation:
            if pending:
                self.lifecycle.append({"event": "abandoned", "record": pending["record"]})
            pending = {"state": "active", "record": alias, "capability": capability,
                       "parameters": dict(parameters), "revision_of": revision_of,
                       "request": text, "attempts": []}
            self.active_task = pending
            self.lifecycle.append({"event": "started", "record": alias,
                                   "capability": capability})
        else:
            pending.update(state="active", parameters=dict(parameters), request=text)
            self.lifecycle.append({"event": "resumed", "record": alias,
                                   "capability": capability})
        result = super().analyze(alias, capability, parameters, text,
                                 revision_of=revision_of)
        trace = (list(self.entries[-1].tool_trace) if result["status"] == "completed"
                 else result.get("tool_trace", []))
        pending["attempts"].append({"request": text, "parameters": dict(parameters),
                                    "status": result["status"],
                                    "code": result.get("code"), "tool_trace": trace})
        if result["status"] == "completed":
            self.task_summaries[result["task_id"]] = _summary(self.entries[-1])
            self.lifecycle.append({"event": "archived", "task_id": result["task_id"],
                                   "attempt_count": len(pending["attempts"])})
            self.active_task = None
            self.focused_task_id = None
        else:
            pending["state"] = "blocked"
            self.lifecycle.append({"event": "blocked", "status": result["status"],
                                   "code": result.get("code")})
        return result

    def switch(self, alias, text):
        result = super().switch(alias, text)
        if result["status"] == "switched":
            if self.active_task:
                self.lifecycle.append({"event": "suspended_on_switch",
                                       "record": self.active_task["record"]})
            self.active_task = None
            self.focused_task_id = None
        return result

    def read_task(self, task_id, text, *, record_message=True):
        entry = next((item for item in self.entries if item.task_id == task_id), None)
        if entry is not None and record_message:
            mismatch = scientific_read_mismatch(self, entry, text)
            if mismatch:
                self.messages.append({"role": "user", "content": text})
                self.lifecycle.append({"event": "read_rejected", "task_id": task_id,
                                       "reason": mismatch})
                return {"status": "clarification_required",
                        "code": "SCIENTIFIC_SCOPE_MISMATCH", "reason": mismatch}
        result = super().read_task(task_id, text, record_message=record_message)
        if result["status"] == "read":
            result = {**result, "source_stage": entry.evidence["source_stage"],
                      "analysis_configuration": entry.evidence["analysis_configuration"],
                      "tool_trace": list(entry.tool_trace)}
            if record_message:
                self.focused_task_id = task_id
                self.evidence_reads += 1
                self.lifecycle.append({"event": "restored", "task_id": task_id,
                                       "record": entry.record})
        return result


def scientific_read_mismatch(session, entry, text):
    """Shared, conservative EEG evidence guard; no gold or policy-specific data."""
    query = parse_visible_query(session, text)
    params = entry.parameters
    if query.records and entry.record not in query.records:
        return "record"
    if query.scientific_scope:
        event = entry.capability in EVENT_CAPABILITIES
        if (query.scientific_scope == "event") != event:
            return "analysis_scope"
    if query.channels:
        channels = set(params.get("channels", ()))
        if entry.capability == "event_bandpower":
            for condition in entry.result.get("conditions", {}).values():
                channels.update(condition.get("channels", {}))
        if not set(query.channels).issubset(channels):
            return "channels"
    if query.event_labels and not set(query.event_labels).issubset(params.get("labels", ())):
        return "event_labels"
    if query.window:
        window = ((params.get("start"), params.get("end"))
                  if "start" in params else (params.get("tmin"), params.get("tmax")))
        if tuple(query.window) != window:
            return "window"
    has_newer_version = any(other.revision_of == entry.task_id
                            for other in session.entries)
    if query.version == "new" and has_newer_version:
        return "version"
    if query.version == "old" and entry.revision_of and not has_newer_version:
        return "version"
    return None


def _summary(entry):
    """Compact routing facts only; never generate a numerical finding."""
    return {"task_id": entry.task_id, "sequence": entry.sequence,
            "record": entry.record, "capability": entry.capability,
            "parameters": entry.parameters, "revision_of": entry.revision_of,
            "source": entry.evidence["source"],
            "source_stage": entry.evidence["source_stage"],
            "unit_or_kind": entry.evidence["unit_or_kind"],
            "analysis_configuration": entry.evidence["analysis_configuration"],
            "evidence_token": entry.evidence["evidence_token"],
            "result_fields": ["/".join(path) for path in _scalar_paths(entry.result)][:24],
            "read_task_id": entry.task_id}


def _active_card(session):
    if not session.active_task:
        return None
    pending = session.active_task
    return {"state": pending["state"], "record": pending["record"],
            "capability": pending["capability"], "parameters": pending["parameters"],
            "revision_of": pending["revision_of"], "request": pending["request"],
            "attempts": list(pending["attempts"])}


def _scientific_binding(entry):
    """Bind a restored task to actual source and scientific scope."""
    params = entry.parameters
    return {"record": entry.record, "source": entry.evidence["source"],
            "source_stage": entry.evidence["source_stage"],
            "channels": params.get("channels", []), "event_labels": params.get("labels", []),
            "window": ([params["start"], params["end"]]
                       if "start" in params and "end" in params else None),
            "epoch_window": ([params["tmin"], params["tmax"]]
                             if "tmin" in params and "tmax" in params else None),
            "revision_of": entry.revision_of,
            "evidence_token": entry.evidence["evidence_token"]}


def _scientific_groups(entries):
    """Group by observed EEG object, retaining each window and revision ID."""
    groups = {}
    for entry in entries:
        binding = _scientific_binding(entry)
        identity = (binding["record"], binding["source"], binding["source_stage"],
                    entry.capability, tuple(binding["channels"]),
                    tuple(binding["event_labels"]))
        group = groups.setdefault(identity, {
            "record": binding["record"], "source": binding["source"],
            "source_stage": binding["source_stage"], "capability": entry.capability,
            "channels": binding["channels"], "event_labels": binding["event_labels"],
            "versions": []})
        group["versions"].append({"task_id": entry.task_id,
                                  "revision_of": entry.revision_of,
                                  "window": binding["window"],
                                  "epoch_window": binding["epoch_window"]})
    # Singletons are already represented by their task card or compact index;
    # repeat only object families where distinct versions could be conflated.
    return [group for group in groups.values() if len(group["versions"]) > 1]


def select_context_v3(session, text, policy, *, top_k=3):
    """Active detail, completed abstracts, bounded working set and exact restore."""
    if top_k < 1:
        raise ValueError("top_k must be positive")
    if policy in {"F", "S", "G", "E", "E-no-science"}:
        selected = select_context_v2(session, text, policy, top_k=top_k)
        payload = {**selected["payload"], "active_task": _active_card(session)}
        if policy == "F":
            # Full chronological user text and each complete task result once;
            # the v2 card+message+tool-trace triplication is not a fair F cost.
            payload.pop("full_tool_results", None)
            payload["cards"] = [{key: value for key, value in card.items()
                                 if key != "request"} for card in payload["cards"]]
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        return {**selected, "payload": payload, "characters": len(encoded),
                "estimated_tokens": (len(encoded) + 3) // 4}
    if policy not in {"H", "HE"}:
        raise ValueError("Unknown memory policy")
    baseline = select_context_v2(session, text, "G" if policy == "H" else "E",
                                 top_k=top_k)
    by_id = {entry.task_id: entry for entry in session.entries}
    chosen = baseline["shown_task_ids"]
    archived = [entry for entry in session.entries if entry.task_id not in chosen]
    focus = by_id.get(session.focused_task_id)
    payload = {"active_record": session.active_record,
               "record_aliases": sorted(session.records),
               "active_task": _active_card(session),
               "completed_index": [session.task_summaries[entry.task_id]
                                   for entry in archived],
               "working_tasks": [_full_card(by_id[task_id]) for task_id in chosen],
               "focused_evidence": ({**_full_card(focus),
                                     "tool_trace": list(focus.tool_trace)} if focus else None),
               "read_interface": "read_task(task_id)"}
    if policy == "HE":
        # H can read all the same fields; HE organizes scientific objects and
        # version chains without merging distinct records/conditions/windows.
        payload["scientific_object_groups"] = _scientific_groups(session.entries)
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    return {"payload": payload, "shown_task_ids": chosen,
            "ranked_task_ids": baseline["ranked_task_ids"],
            "summary_triggered": bool(archived), "archive_count": len(archived),
            "characters": len(encoded), "estimated_tokens": (len(encoded) + 3) // 4}


def live_turn_v3(session, policy, text, client, *, deliver_answer=False):
    if not isinstance(session, EpisodeMemorySession):
        raise TypeError("Task episodes require EpisodeMemorySession")
    return live_turn(session, policy, text, client, deliver_answer=deliver_answer,
                     selector=select_context_v3)


def replay_protocol_v3(script, policies=("F", "S", "H", "HE")):
    """One actual tool history; offline gold is used only after selection."""
    session, keys = build_protocol_session(script, session_class=EpisodeMemorySession)
    rows = []
    for policy in policies:
        observations = []
        for query in script["queries"]:
            selected = select_context_v3(session, query["text"], policy)
            target_id = keys[query["target"]].task_id
            first_id = selected["ranked_task_ids"][0] if selected["ranked_task_ids"] else None
            first = (score_read_semantics(session, script, query, keys, first_id)
                     if first_id else None)
            target = (score_read_semantics(session, script, query, keys, target_id)
                      if target_id in selected["shown_task_ids"] else None)
            observations.append({"query": query["text"],
                                 "target_visible": target_id in selected["shown_task_ids"],
                                 "top1_correct": bool(first and first["valid"]),
                                 "target_read_correct": bool(target and target["valid"]),
                                 "summary_triggered": selected["summary_triggered"],
                                 "archive_count": selected["archive_count"],
                                 "characters": selected["characters"]})
        rows.append({"session_id": script["id"], "policy": policy,
                     "task_count": len(session.entries), "queries": observations,
                     "lifecycle": list(session.lifecycle)})
    return rows
