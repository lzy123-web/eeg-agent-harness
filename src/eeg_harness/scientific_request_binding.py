"""Bind scientific values to complete request clauses, never cropped quotes.

This is bounded admission of literal record/object/range facts. It is neither
an intent parser nor a proof that every natural-language goal was covered.
The model chooses the action; the existing Executor still does the science.
"""
from dataclasses import dataclass, replace, asdict
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


def source_catalog(store):
    """Stable request-local locators over existing frames, no mutable database."""
    return [{'source_ref':f'u{turn}:{hashlib.sha256(text.encode()).hexdigest()[:16]}:{f.start}:{f.end}',
             'turn':turn,'request_sha256':hashlib.sha256(text.encode()).hexdigest(),
             'span':f.text,'records':list(f.records),'start':f.start,'end':f.end}
            for turn,text in enumerate(store.user_requests,1) for f in _request_frames(store,text)]


def resolve_source_ref(store,ref):
    rows=[r for r in source_catalog(store) if r['source_ref']==ref]
    if len(rows)!=1:raise ValueError('Unknown or ambiguous source_ref; use the visible source catalog')
    row=rows[0]
    frame=next(f for f in _request_frames(store,store.user_requests[row['turn']-1])
               if (f.start,f.end)==(row['start'],row['end']))
    return row['turn'],frame


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


def owned_intervals(store, frame, family, anchors):
    """Literal range ownership, independently of action type or whole-frame role.

    Within one metadata role, preceding groups locate literal ranges. Mixed
    roles require an interpretation; word order never chooses their time base.
    Unanchored supplements are handled separately through validated history.
    """
    channels = {c for r in store.records.values() for c in r.channel_names}
    labels = {e.label for r in store.records.values() if r.events for e in r.events.events}
    # Mixed scientific roles require an explicit interpretation, never the
    # nearest name. Literal order can locate ranges within one role only.
    if any(store._contains(frame.text,c) for c in channels) and any(store._contains(frame.text,l) for l in labels):
        return set()
    occurrences = []
    for value in channels | labels:
        for match in re.finditer(r'(?<![A-Za-z0-9_-])'+re.escape(value)+r'(?![A-Za-z0-9_-])', frame.text):
            roles = ({'continuous'} if value in channels else set()) | ({'event'} if value in labels else set())
            occurrences.append((match.end(),value,roles))
    result = set()
    previous_end = 0
    owner_roles, group = set(), set()
    for interval in RANGE.finditer(frame.text):
        preceding = [o for o in occurrences if previous_end < o[0] <= interval.start()]
        previous_end = interval.end()
        if preceding:
            owner_roles = max(preceding,key=lambda o:o[0])[2]
            foreign_end = max((o[0] for o in preceding if o[2] != {family}),default=-1)
            group = {o[1] for o in preceding if o[0] > foreign_end and o[2] == {family}}
        # A subsequent range without a new object keeps only the most recent
        # group, never all objects earlier in the sentence.
        if owner_roles == {family} and anchors and anchors.issubset(group):
            result.add(tuple(float(v) for v in interval.groups()))
    return result


def object_evidence_frames(store, frames, family, anchors, record, whole):
    """The same complete object/adjacent-range parents for execution and asks."""
    channels={c for r in store.records.values() for c in r.channel_names}
    labels={e.label for r in store.records.values() if r.events for e in r.events.events}
    evidence=list(frames)
    for left,right in zip(frames,frames[1:]):
        left_objects={v for v in (labels if family=='event' else channels) if store._contains(left.text,v)}
        left_foreign=family!='event' and any(store._contains(left.text,v) for v in labels)
        right_has_object=any(store._contains(right.text,v) for v in channels|labels)
        if (anchors and left_objects==anchors and not left_foreign and not RANGE.search(left.text)
                and not right_has_object and RANGE.search(right.text)
                and right.object_parent==left.object_parent
                and not re.search(r'[^\s;；。\n,，]',whole[left.end:right.start])
                and record in set(left.records)&set(right.records)):
            evidence.append(SourceFrame(whole[left.start:right.end],left.start,right.end,
                tuple(sorted(set(left.records)&set(right.records))),'adjacent_object_and_interval'))
    return evidence


def window_availability(store, name, scope, record, fields):
    """Read-only absence audit; never invent endpoints or import evaluator gold."""
    from .working_memory_lifecycle import NUMBER
    family=store._family(name);key='labels' if family=='event' else 'channels'
    pair=('tmin','tmax') if family=='event' else ('start','end')
    anchors=set(scope.get(key,[]));parents=[];intervals=set();uncertain=False
    if not anchors or not set(fields).issubset(pair):return {'status':'review_required','sources':[]}
    for turn,whole in enumerate(store.user_requests,1):
        frames=_request_frames(store,whole)
        relevant=[f for f in frames if record in f.records and
            (f.object_family==family and anchors.issubset(f.object_names) or
             bool(owned_intervals(store,f,family,anchors)))]
        for f in object_evidence_frames(store,relevant,family,anchors,record,whole):
            owned=owned_intervals(store,f,family,anchors)
            literal={(float(a),float(b)) for a,b in RANGE.findall(f.text)}
            parents.append({'turn':turn,**asdict(f)})
            if f.records!=(record,):uncertain=True
            if literal:
                # An attached range without literal names is resolved by its
                # complete merged parent above; never classify it as absent.
                if owned:intervals.update(owned)
                elif f.object_parent is None or f.object_parent==(f.start,f.end):uncertain=True
            else:
                values={float(v) for v in re.findall(rf'(?<![A-Za-z0-9.])({NUMBER})(?![\d.])',f.text)}
                known={float(scope[k]) for k in pair if k in scope}
                if values-known:uncertain=True # unassigned scalar: review, not a guessed field
        # Multiple attached ranges, including a later range after an already
        # complete interval, are a conflict even when only the first can bind.
        attached={(float(a),float(b)) for f in relevant for a,b in RANGE.findall(f.text)}
        if len(attached)>1:uncertain=True
    if not parents or uncertain or len(intervals)>1:status='review_required'
    elif intervals:
        values=next(iter(intervals))
        status='known_user_window' if all(k not in scope or scope[k]==v for k,v in zip(pair,values)) else 'review_required'
    else:status='missing_literal_window'
    return {'status':status,'fields':list(fields),'sources':parents,'windows':[list(v) for v in sorted(intervals)]}


def resolve_channel_reference(store, scope, record, resolution, reference, *, interpreted=False, turn=None):
    """Copy only a unique literal channel set, never record/time/artifact.

    Full original parents are mandatory. A model proposes the field relation;
    the program checks source values, uniqueness, destination metadata and its
    independently specified interval. This is not a proof of linguistic intent.
    """
    if not isinstance(reference, dict) or set(reference) != {'source_span', 'target_span'}:
        raise ValueError('Channel reference requires complete source_span and target_span')
    turn=turn or store.turn
    frames = _request_frames(store, store.user_requests[turn-1])
    source = [f for f in frames if f.text == reference['source_span']]
    target = [f for f in resolution.frames if f.text == reference['target_span']]
    if len(source) != 1 or len(target) != 1:
        raise ValueError('Reference parents must identify unique complete original clauses')
    source, target = source[0], target[0]
    candidates = {f.object_names for f in frames if f.end <= target.start and
                  f.object_family == 'continuous' and f.object_parent == (f.start,f.end)}
    if (source.end > target.start or source.object_family != 'continuous' or
        candidates != {source.object_names} or target.records != (record,) or
        target.object_family not in (None,'continuous') or not source.records):
        raise ValueError('Ambiguous reference or conflicting destination object; clarify selection')
    selected = tuple(sorted(scope.get('channels', [])))
    if (selected != source.object_names or not set(selected).issubset(store.records[record].channel_names) or
        any(not set(selected).issubset(store.records[r].channel_names) for r in source.records)):
        raise ValueError('Referenced channels must exist in destination and match literal source')
    # A proposal may locate evidence, never create target-selection authority.
    # Without literal target confirmation the relation remains a clarification.
    explicit_target={c for c in store.records[record].channel_names if store._contains(target.text,c)}
    if explicit_target and explicit_target != set(selected):
        raise ValueError('Referenced selection conflicts with the explicit target channels')
    if not interpreted and not all(store._contains(target.text,c) for c in selected):
        raise ValueError('Unconfirmed destination selection: ask the user to name its channels')
    # The interpreted route checks the selected current/historical window in
    # interpreted_sources, separately from this channel-only relation. Legacy
    # action references have no such interpretation and retain their check.
    if not interpreted:
        intervals = {(float(a),float(b)) for a,b in RANGE.findall(target.text)}
        if set(scope) - {'channels','start','end'} or not all(k in scope for k in ('start','end')) or intervals != {(float(scope['start']),float(scope['end']))}:
            raise ValueError('Destination needs one independently stated complete absolute interval')
    base = {'kind':'user','turn':turn,'span':target.text,
            'reference_kind':'channel_names_only','source_parent':source.text,
            'source_records':list(source.records),'destination_record':record,
            'semantic_interpretation':'model_proposed_field_reference_not_intent_proof'}
    return {k:{**base,'field':k} for k in (('channels',) if interpreted else ('channels','start','end'))}


def interpreted_sources(store,name,scope,record,resolution,interpretation,inherited=None):
    """Check facts of a proposed meaning, without pretending to parse intent.

    The complete original parent and literal pair remain inspectable. Tool
    time basis, record ownership, actual metadata and field isolation are
    deterministic. Whether the proposed relation faithfully explains the
    user's words is separately evaluated, not certified by string matching.
    """
    from .task_plan import _interpretation
    value=_interpretation(interpretation)
    source_turn=store.turn
    if 'source_ref' in value:
        source_turn,located=resolve_source_ref(store,value['source_ref'])
        frames=[f for f in resolution.frames if (f.start,f.end,f.text)==(located.start,located.end,located.text)] if source_turn==store.turn else [located]
        if source_turn<store.turn and not located.records and inherited and store._binding_valid(inherited) and inherited.record==record:
            frames=[replace(located,records=(record,),record_basis='valid_inherited_result')]
        value['source_span']=located.text
    else:frames=[f for f in resolution.frames if f.text==value['source_span']]
    if len(frames)!=1 or frames[0].records!=(record,):
        raise ValueError('Interpretation must identify one complete record-bound source parent')
    frame=frames[0]
    if value['time_reference']!=resolution.time_reference:
        raise ValueError('Tool time reference conflicts with the task interpretation')
    context=store.contexts[record]
    channels=set(context.record.channel_names)
    labels={e.label for e in context.record.events.events} if context.record.events else set()
    measurement=set(value.get('measurement_channels',[]))
    if not measurement.issubset(channels):
        raise ValueError('Measurement dimensions are absent from target metadata')
    object_key='labels' if resolution.time_reference=='event_relative' else 'channels'
    available=labels if object_key=='labels' else channels
    selected=set(scope.get(object_key,[]))
    if not selected or not selected.issubset(available):
        raise ValueError('Interpreted object is absent from target metadata')
    sources={}
    pair=('tmin','tmax') if object_key=='labels' else ('start','end')
    window_frame,window_turn=frame,source_turn
    retained_window=False
    if 'range_ref' in value:
        window_turn,window_frame=resolve_source_ref(store,value['range_ref'])
        if window_turn==store.turn:
            matched=[f for f in resolution.frames if (f.start,f.end,f.text)==(window_frame.start,window_frame.end,window_frame.text)]
            if len(matched)!=1:raise ValueError('Window reference is not a resolved source for this action')
            window_frame=matched[0]
        if window_frame.records!=(record,):raise ValueError('Window reference belongs to another record')
        # A changed object field does not invalidate unchanged time fields of
        # the explicitly selected actual result. Require its original receipt,
        # not merely equal numbers in some historical user sentence.
        retained_window=bool(window_turn<store.turn and inherited
            and store._binding_valid(inherited) and inherited.record==record
            and store._family(inherited.capability)==store._family(name)
            and all(scope.get(k)==inherited.parameters.get(k) for k in pair)
            and any(all(o.get('scientific_sources',{}).get(k,{}).get('turn')==window_turn
                        and o.get('scientific_sources',{}).get(k,{}).get('span')==window_frame.text
                        for k in pair) for o in inherited.tool_trace))
        if retained_window:
            current_windows={v for f in resolution.frames for v in
                (owned_intervals(store,f,store._family(name),selected) or
                 ({(float(a),float(b)) for a,b in RANGE.findall(f.text)} if f.object_parent is None else set()))}
            if current_windows and current_windows!={tuple(float(scope[k]) for k in pair)}:
                raise ValueError('Current user window conflicts with the selected result window')
        if source_turn==store.turn and window_frame!=frame and not retained_window:
            raise ValueError('Current source parents cannot be spliced into a window')
    if source_turn<store.turn:
        historical,ambiguous=_historical_scientific_object(store,name,scope)
        exact=bool(inherited and store._binding_valid(inherited) and inherited.record==record
            and set(inherited.parameters.get(object_key,[]))==selected)
        if not exact and (ambiguous or not historical or historical['record']!=record
                         or historical['span']!=frame.text or historical['turn']!=source_turn):
            raise ValueError('Historical locator is not the applicable scientific object')
        if window_turn<store.turn:
            if not exact or any(scope.get(k)!=inherited.parameters.get(k) for k in pair):
                raise ValueError('Historical window requires the same valid result; revised values need a current range_ref')
            current_windows={v for f in resolution.frames for v in
                (owned_intervals(store,f,store._family(name),selected) or
                 ({(float(a),float(b)) for a,b in RANGE.findall(f.text)} if f.object_parent is None else set()))}
            if current_windows and current_windows!={tuple(float(scope[k]) for k in pair)}:
                raise ValueError('Current user window conflicts with the old window; use its current range_ref')
        elif window_frame not in resolution.frames or any(
                store._contains(window_frame.text,x) for x in available-selected):
            raise ValueError('Current supplement conflicts with the historical object')
    elif window_turn!=store.turn and not retained_window:raise ValueError('Cannot borrow an old window for a current object')
    reference=value.get('channel_reference')
    if reference:
        if 'source_ref' in reference:
            st,sf=resolve_source_ref(store,reference['source_ref'])
            tt,tf=resolve_source_ref(store,reference['target_ref'])
            if st!=tt or tt!=source_turn:raise ValueError('Field relation must identify source and target in the same request')
            reference={'source_span':sf.text,'target_span':tf.text}
        if object_key!='channels' or reference['target_span']!=frame.text:
            raise ValueError('Field reference applies only to target channel names')
        sources.update(resolve_channel_reference(store,scope,record,
            replace(resolution,frames=(frame,)),reference,interpreted=True,turn=source_turn))
    elif any(not store._contains(frame.text,x) for x in selected):
        raise ValueError('Object values must be literal or use interpretation.channel_reference with complete source/target clauses')
    if any(not store._contains(frame.text,c) for c in measurement) and not (reference and measurement.issubset(selected)):
        raise ValueError('Measurement dimensions need literal source names or the same verified channel field reference')
    if not all(k in scope for k in pair):
        # An interpretable object may still lack scientific parameters. Keep
        # only its verified identity, so the existing missing-field path can
        # suspend and later resume it without inventing a range.
        return {object_key:{'kind':'user','turn':source_turn,'span':frame.text,
            'interpretation':clone(value),'semantic_status':'model_interpretation_not_intent_proof',
            'verified_facts':['source_parent','record','metadata','tool_time_reference']}}
    span=value.get('range_span',window_frame.text)
    if span not in window_frame.text or window_frame.text.count(span)!=1:
        raise ValueError('Window locator must uniquely occur inside the complete source parent')
    if not all(k in scope for k in pair) or {(float(a),float(b)) for a,b in RANGE.findall(span)} != {tuple(float(scope[k]) for k in pair)}:
        raise ValueError('Interpretation cannot invent or combine missing window endpoints')
    # Do not silently change a previously admitted meaning for the same source
    # interval. A task revision needs independently compatible evidence.
    for fact in store.admitted_scopes:
        for source in fact['sources'].values():
            prior=source.get('interpretation',{})
            if (source.get('turn')==store.turn and fact['record']==record and prior.get('source_span')==frame.text
                    and prior.get('range_span',prior.get('source_span'))==span
                    and prior.get('time_reference') not in (None,value['time_reference'])):
                raise ValueError('Conflicting time references for the same interpreted source window')
    base={'kind':'user','turn':source_turn,'span':frame.text,'interpretation':clone(value),
          'semantic_status':'model_interpretation_not_intent_proof',
          'verified_facts':['source_parent','record','metadata','literal_window','tool_time_reference']}
    sources.update({k:{**clone(base),'field':k,**({'field_reference':clone(reference)} if k=='channels' and reference else {})}
                    for k in (object_key,*pair)})
    for k in pair:
        sources[k].update(turn=window_turn,span=window_frame.text)
    return sources


def ground_bound_scope(store, name, scope, record, resolution, inherited, channel_reference=None, interpretation=None):
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
                       f.object_family == family and anchors.issubset(f.object_names) or
                       bool(owned_intervals(store,f,family,anchors))]
    # Legacy grounding gathers candidates and mutates fact caches. Commit only
    # the final coherent sources below, after ownership/reference validation.
    prior_facts = clone(store.active.scientific_facts) if store.active else None
    prior_admitted = clone(store.admitted_scopes)
    sources, missing, unresolved = ActionWorkingMemoryStore._ground_scope(
        store, name, scope, record, "；".join(f.text for f in relevant_frames), inherited)
    store.admitted_scopes = prior_admitted
    if store.active:
        store.active.scientific_facts = prior_facts
    context = store.contexts[record]
    if channel_reference is not None:
        sources.update(resolve_channel_reference(store, scope, record, resolution, channel_reference))
    explained=interpreted_sources(store,name,scope,record,resolution,interpretation,inherited) if interpretation else {}
    channels = set(context.record.channel_names)
    labels = {e.label for e in context.record.events.events} if context.record.events else set()
    pair = ("tmin", "tmax") if family == "event" else ("start", "end")
    # Legacy literal matching is a candidate generator, not final authority.
    # Recheck current range pairs against full-parent ownership even when the
    # legacy path already found their numbers. Historical/exact-result sources
    # and single-endpoint revisions retain their original provenance.
    for key in pair:
        source = sources.get(key, {})
        if (source.get('kind') == 'user' and source.get('turn') == store.turn
                and RANGE.search(source.get('span', ''))):
            sources.pop(key)
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
    evidence_frames = object_evidence_frames(store,relevant_frames,family,anchors,record,whole)
    if anchors and all(key in scope for key in pair):
        interval = tuple(float(scope[key]) for key in pair)
        unanchored = [f for f in relevant_frames if f.object_parent is None
                      and not any(store._contains(f.text, v) for v in channels | labels)]
        implicit_intervals = {(float(a), float(b)) for f in unanchored for a, b in RANGE.findall(f.text)}
        for frame in evidence_frames:
            present_objects = {v for v in (labels if family == "event" else channels)
                               if store._contains(frame.text, v)}
            owned = owned_intervals(store,frame,family,anchors)
            foreign_domain = bool((channels if family == "event" else labels) &
                {v for v in channels | labels if store._contains(frame.text,v)}) and interval not in owned
            object_source = sources.get(object_key, {})
            prior_identity = (object_source.get("kind") == "result" or
                              object_source.get("kind") == "user" and object_source.get("turn", store.turn) < store.turn)
            implicit_identity = (prior_identity and frame in unanchored
                                 and implicit_intervals == {interval})
            if (not anchors.issubset(present_objects) and not implicit_identity) or foreign_domain:
                continue
            intervals = owned or ({(float(a),float(b)) for a,b in RANGE.findall(frame.text)} if implicit_identity else set())
            # Several records and intervals in one clause may be a respective
            # pairing, not a Cartesian product. Literal values cannot prove
            # which record owns which interval; require explicit separation.
            if interval not in intervals or len(frame.records) > 1 and len(intervals) > 1:
                continue
            for key in pair:
                if key not in sources:
                    sources[key] = {"kind": "user", "turn": store.turn, "span": frame.text}
            break
    sources.update(explained)
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
