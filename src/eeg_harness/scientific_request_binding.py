"""Bind scientific values to complete request clauses, never cropped quotes.

This is bounded admission of literal record/object/range facts. It is neither
an intent parser nor a proof that every natural-language goal was covered.
The model chooses the action; the existing Executor still does the science.
"""
from dataclasses import dataclass, replace
import hashlib
import re

from .working_memory import clone
from .working_memory_actions import ActionWorkingMemoryStore
from .working_memory_lifecycle import EVENT_TOOLS, METADATA, RANGE


@dataclass(frozen=True)
class SourceFrame:
    text: str
    start: int
    end: int
    records: tuple[str, ...]
    record_basis: str
    object_family: str | None = None
    object_names: tuple[str, ...] = ()
    object_parent: tuple[int, int] | None = None


@dataclass(frozen=True)
class SourceResolution:
    text: str = ""
    frames: tuple[SourceFrame, ...] = ()
    allowed_records: tuple[str, ...] = ()
    time_reference: str = "record_absolute"
    request_fingerprint: str = ""
    code: str | None = None
    message: str = ""

    @property
    def ok(self):
        return self.code is None


def _record_occurrences(store, text):
    matches = []
    for record in store.records:
        pattern = r"(?:记录|record)\s*" + re.escape(record) + r"(?![A-Za-z0-9_-])"
        matches.extend((m.start(), m.end(), record) for m in re.finditer(pattern, text, re.I))
    return sorted(matches)


def _record_names(store, text):
    return {record for _, _, record in _record_occurrences(store, text)}


def _objects(store):
    return sorted({name for context in store.contexts.values()
                   for name in (*context.record.channel_names,
                                *([e.label for e in context.record.events.events]
                                  if context.record.events else []))}, key=lambda v: (-len(v), v))


def _request_frames(store, whole):
    """Keep literal parent spans and forward record ownership in this request.

    Ordinary punctuation/list handling is inherited. A later explicit record
    after an object or complete interval starts a new unit even without
    punctuation; a leading record list with a shared interval remains shared.
    """
    objects = _objects(store)
    pieces = store._scientific_clauses(whole, objects)
    raw, search_from = [], 0
    for piece in pieces:
        start = whole.find(piece, search_from)
        search_from = start + len(piece)
        cuts = [0]
        for pos, _, _ in _record_occurrences(store, piece):
            prefix = piece[cuts[-1]:pos]
            if pos > cuts[-1] and (RANGE.search(prefix) or any(store._contains(prefix, x) for x in objects)):
                cuts.append(pos)
        cuts.append(len(piece))
        raw.extend((start + left, start + right) for left, right in zip(cuts, cuts[1:])
                   if piece[left:right].strip())
    whole_records = _record_names(store, whole)
    bound = tuple(sorted(whole_records)) if len(whole_records) == 1 else ()
    basis = "unique_record_in_request" if bound else "unresolved"
    owner_family, owner_names, owner_parent = None, (), None
    all_labels = {e.label for context in store.contexts.values() if context.record.events
                  for e in context.record.events.events}
    all_channels = {c for context in store.contexts.values() for c in context.record.channel_names}
    frames = []
    for start, end in raw:
        text = whole[start:end]
        explicit = tuple(sorted(_record_names(store, text)))
        if explicit:
            if explicit != bound:
                owner_family, owner_names, owner_parent = None, (), None
            bound, basis = explicit, "explicit_record"
        labels = tuple(sorted(x for x in all_labels if store._contains(text, x)))
        channels = tuple(sorted(x for x in all_channels if store._contains(text, x)))
        if labels or channels:
            # A reported channel within a named event object belongs to that
            # event object. Mixed-domain intervals still fail literal grounding.
            owner_family, owner_names = ("event", labels) if labels else ("continuous", channels)
            owner_parent = (start, end)
        frames.append(SourceFrame(text, start, end, bound, basis, owner_family, owner_names, owner_parent))
        if explicit:
            basis = "preceding_record_in_request"
    return frames


def _fallback_records(store, record, inherited, scope, name):
    if inherited is not None:
        return (inherited.record,), "inherited_result"
    context = store.contexts[record]
    artifact_id = scope.get("artifact_id")
    if (artifact_id in context.artifacts and any(e.record == record
            and e.evidence["binding"]["artifact_id"] == artifact_id
            and store._binding_valid(e) for e in store.entries)):
        return (record,), "actual_artifact"
    historical, ambiguous = _historical_scientific_object(store, name, scope)
    if historical is not None:
        return (historical["record"],), "unique_historical_scientific_object"
    if ambiguous:
        return (), "ambiguous_historical_scientific_objects"
    for whole in reversed(store.user_requests[:-1]):
        records = tuple(sorted(_record_names(store, whole)))
        if records:
            return records, "prior_user_record" if len(records) == 1 else "ambiguous_prior_records"
    if len(store.records) == 1:
        return (record,), "only_loaded_record"
    # Reading known metadata does not authorize any scientific transformation.
    if name in METADATA:
        return (record,), "selected_metadata_record"
    return (), "unresolved"


def _historical_scientific_object(store, name, scope):
    """One user-defined scientific object, independently of model bookkeeping.

    Record counts for unrelated raw-data tasks must not obscure a uniquely
    stated event object. Conversely, choosing an action's labels does not
    resolve two historical event objects. Only actual current-user metadata
    names may narrow a previously ambiguous set. No historical time values
    are imported by this function.
    """
    family = store._family(name)
    key = "labels" if family == "event" else "channels"
    selected = tuple(sorted(scope.get(key, [])))
    if not selected:
        return None, False
    current = store.user_requests[-1] if store.user_requests else ""
    explicitly_named = all(store._contains(current, value) for value in selected)
    current_records = {alias for frame in _request_frames(store, current)
                       if frame.record_basis == "explicit_record" and
                       (frame.object_family == family and set(selected).issubset(frame.object_names)
                        or frame.object_family is None and RANGE.search(frame.text))
                       for alias in frame.records}
    for index in range(len(store.user_requests)-2, -1, -1):
        candidates = []
        for frame in _request_frames(store, store.user_requests[index]):
            for alias in frame.records:
                eeg = store.contexts[alias].record
                labels = {e.label for e in eeg.events.events} if eeg.events else set()
                objects = labels if family == "event" else set(eeg.channel_names)
                present = tuple(sorted(x for x in objects if store._contains(frame.text, x)))
                if family == "continuous" and any(store._contains(frame.text, x) for x in labels):
                    continue  # A channel reported within events is not a raw window.
                if present:
                    candidates.append((alias, present, frame))
        if not candidates:
            continue
        relevant = candidates
        if explicitly_named:
            relevant = [item for item in relevant if set(selected).issubset(item[1])]
        if len(current_records) == 1:
            relevant = [item for item in relevant if item[0] in current_records]
        identities = {(alias, objects) for alias, objects, _ in relevant}
        if len(identities) != 1:
            return None, True  # Do not search older history past newer ambiguity.
        alias, objects = next(iter(identities))
        if objects != selected and not explicitly_named:
            return None, True
        frame = relevant[-1][2]
        return {"kind": "user", "turn": index+1, "span": frame.text,
                "basis": "unique_historical_scientific_object", "record": alias,
                "time_reference": "event_relative" if family == "event" else "record_absolute",
                "parent_start": frame.start, "parent_end": frame.end}, False
    return None, False


def resolve_action_source(store, name, scope, record, request_span=None, *, inherited=None):
    """Select record-bound original frames for one ordinary numerical action.

    A span is only an optional locator. Every occurrence is mapped back to its
    full parent; removing a record name, channel or label cannot change that
    parent's scientific ownership. Ambiguous implicit records require a real
    inherited result or clarification, rather than a model-selected default.
    """
    whole = store.user_requests[-1] if store.user_requests else ""
    time_reference = "event_relative" if name in EVENT_TOOLS else "record_absolute"
    fingerprint = hashlib.sha256(whole.encode("utf-8")).hexdigest()

    def error(code, message):
        return SourceResolution(time_reference=time_reference, request_fingerprint=fingerprint,
                                code=code, message=message)

    if request_span is not None and (not isinstance(request_span, str) or not request_span.strip()
                                     or request_span not in whole):
        return error("INVALID_SOURCE_SPAN", "A source locator must be an actual current-user substring")
    frames = _request_frames(store, whole)
    if request_span is not None:
        # Keep every occurrence: a repeated phrase is not authority to choose a
        # different record. Only matching fully bound parent frames may survive.
        occurrences, begin = [], 0
        while True:
            at = whole.find(request_span, begin)
            if at < 0:
                break
            occurrences.append((at, at + len(request_span)))
            begin = at + 1
        frames = [f for f in frames if any(left < f.end and right > f.start
                                          for left, right in occurrences)]
    fallback, fallback_basis = _fallback_records(store, record, inherited, scope, name)
    resolved = []
    for frame in frames:
        records, basis = frame.records, frame.record_basis
        if not records:
            if len(fallback) != 1:
                continue
            records, basis = fallback, fallback_basis
        if record in records:
            resolved.append(replace(frame, records=records, record_basis=basis))
    if not resolved:
        if any(f.records for f in frames) or len(fallback) == 1 and fallback[0] != record:
            return error("RECORD_SCOPE_CONFLICT", "The complete source clause belongs to another record")
        return error("AMBIGUOUS_RECORD_SOURCE", "Clarify the record or inherit an actual unambiguous result")
    return SourceResolution(text="；".join(f.text for f in resolved), frames=tuple(resolved),
                            allowed_records=tuple(sorted({r for f in resolved for r in f.records})),
                            time_reference=time_reference, request_fingerprint=fingerprint)


def ground_bound_scope(store, name, scope, record, resolution, inherited):
    """Reuse literal grounding, adding coherent same-object multi-window facts.

    The old admission checks whole scientific scopes and inherited originals.
    This version supplies only full record-bound parents and records their
    offsets. Multiple intervals in one parent are legal only when they share
    the same metadata object set and time domain; it never cross-products
    independently named objects or borrows an event interval for raw data.
    """
    family = store._family(name)
    object_key = "labels" if family == "event" else "channels"
    anchors = set(scope.get(object_key, []))
    relevant_frames = [f for f in resolution.frames if f.object_family is None or
                       f.object_family == family and anchors.issubset(f.object_names)]
    sources, missing, unresolved = ActionWorkingMemoryStore._ground_scope(
        store, name, scope, record, "；".join(f.text for f in relevant_frames), inherited)
    context = store.contexts[record]
    channels = set(context.record.channel_names)
    labels = {e.label for e in context.record.events.events} if context.record.events else set()
    pair = ("tmin", "tmax") if family == "event" else ("start", "end")
    evidence_frames = list(relevant_frames)
    whole = store.user_requests[-1] if store.user_requests else ""
    historical, ambiguous = _historical_scientific_object(store, name, scope)
    current_object = any(anchors and all(store._contains(f.text, x) for x in anchors)
                         for f in relevant_frames)
    if ambiguous and inherited is None and not current_object:
        # A model-maintained pending task is not user authorization to choose
        # between multiple real historical objects. Preserve exact-result
        # inheritance and current explicit object selection as legal routes.
        sources.pop(object_key, None)
    if object_key not in sources and historical is not None and historical["record"] == record:
        sources[object_key] = historical
    # Ordinary punctuation can put the literal object and its sole interval in
    # adjacent fragments ("pulse events, window 0 to 1"). Preserve their full
    # original parent, without borrowing intervals past another object or an
    # already complete interval. This is bounded local ownership, not free
    # cross-clause numerical matching or a language-specific task keyword list.
    for left, right in zip(relevant_frames, relevant_frames[1:]):
        left_objects = {v for v in (labels if family == "event" else channels)
                        if store._contains(left.text, v)}
        left_foreign = any(store._contains(left.text, v)
                           for v in (channels if family == "event" else labels))
        right_has_object = any(store._contains(right.text, v) for v in channels | labels)
        gap = whole[left.end:right.start]
        if (anchors and left_objects == anchors and not left_foreign and not RANGE.search(left.text)
                and not right_has_object and RANGE.search(right.text)
                and not re.search(r"[^\s;；。\n,，]", gap)
                and record in set(left.records) & set(right.records)):
            evidence_frames.append(SourceFrame(whole[left.start:right.end], left.start, right.end,
                                               tuple(sorted(set(left.records) & set(right.records))),
                                               "adjacent_object_and_interval"))
    if anchors and all(key in scope for key in pair):
        interval = tuple(float(scope[key]) for key in pair)
        unanchored = [f for f in relevant_frames if f.object_parent is None
                      and not any(store._contains(f.text, v) for v in channels | labels)]
        implicit_intervals = {(float(a), float(b)) for f in unanchored for a, b in RANGE.findall(f.text)}
        for frame in evidence_frames:
            present_objects = {v for v in (labels if family == "event" else channels)
                               if store._contains(frame.text, v)}
            foreign_domain = any(store._contains(frame.text, v)
                                 for v in (channels if family == "event" else labels))
            object_source = sources.get(object_key, {})
            prior_identity = (object_source.get("kind") == "result" or
                              object_source.get("kind") == "user" and object_source.get("turn", store.turn) < store.turn)
            implicit_identity = (prior_identity and frame in unanchored
                                 and implicit_intervals == {interval})
            if (present_objects != anchors and not implicit_identity) or foreign_domain:
                continue
            intervals = {(float(a), float(b)) for a, b in RANGE.findall(frame.text)}
            # Several records and intervals in one clause may be a respective
            # pairing, not a Cartesian product. Literal values cannot prove
            # which record owns which interval; require explicit separation.
            if interval not in intervals or len(frame.records) > 1 and len(intervals) > 1:
                continue
            for key in pair:
                if key not in sources:
                    sources[key] = {"kind": "user", "turn": store.turn, "span": frame.text}
            break
    for source in sources.values():
        if source.get("kind") != "user" or source.get("turn") != store.turn:
            continue
        parents = [f for f in evidence_frames if source.get("span", "") in f.text]
        if parents:
            source["binding"] = {
                "record": record, "time_reference": resolution.time_reference,
                "request_fingerprint": resolution.request_fingerprint,
                "parents": [{"span": f.text, "start": f.start, "end": f.end,
                             "allowed_records": list(f.records), "record_basis": f.record_basis}
                            for f in parents]}
    unresolved = [key for key in scope if key not in sources]
    fingerprint = store._binding(context, name)["record_fingerprint"]
    fact = {"record": record, "family": family, "scope": clone(scope),
            "sources": clone(sources), "record_fingerprint": fingerprint}
    # Replace this invocation's partial fact with its complete bound fact. Old
    # facts for other scopes, records and record versions remain untouched.
    identity = lambda row: (row["record"], row["family"], row["scope"], row["record_fingerprint"])
    if store.active:
        store.active.scientific_facts = [f for f in store.active.scientific_facts if identity(f) != identity(fact)] + [fact]
    if not missing and not unresolved:
        store.admitted_scopes = [f for f in store.admitted_scopes if identity(f) != identity(fact)] + [clone(fact)]
    return sources, missing, unresolved
