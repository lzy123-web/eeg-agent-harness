"""Read-only scientific object resolution over explicit existing evidence.

No authoritative state lives here. A pending reference is a legal plan, not
an executable input; a resolved object is not a completed delivery. Callers
retain the graph's readiness, Executor admission and actual-result checks.
"""
from dataclasses import dataclass, field

from .working_memory import clone, encoded
from .working_memory_scientific_tasks import canonical_scope


@dataclass
class ScientificBinding:
    scope: dict
    witnesses: list = field(default_factory=list)
    pending: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    entry: object = None
    artifact_id: str | None = None

    @property
    def ok(self):return not self.conflicts

    def summary(self):
        return {'scope':clone(self.scope),'witnesses':clone(self.witnesses),
                'pending':clone(self.pending),'conflicts':clone(self.conflicts),
                'artifact_id':self.artifact_id,
                'status':'conflict' if self.conflicts else 'pending' if self.pending else 'resolved'}


def resolve_scientific_binding(store,name,record,declared,*,references=(),previous=None,
                               execution=None,artifact_id=None):
    """Resolve only supplied references, own history/receipt or an exact handle.

    references contain a graph-resolved delivery and its actual entry (if any).
    Missing outputs contribute planned scope, explicitly marked pending. A new
    transaction's graph view must already have invalidated changed producers.
    """
    out=ScientificBinding(clone(declared))
    if record not in store.contexts:
        out.conflicts.append('Unknown record');return out
    spec=store.contexts[record].executor.registry.get(name)
    if spec is None:
        out.conflicts.append('No numerical scientific contract for this capability');return out
    candidates=[]
    def add(entry,role,reference=None,planned=None):
        if entry is None:
            out.pending.append({'role':role,'reference':clone(reference)})
            if planned and planned.get('record')!=record:
                out.conflicts.append('Referenced planned object belongs to another record')
            if planned and store._family(planned['capability'])==store._family(name):
                candidates.append((canonical_scope(planned.get('scope',{})),None,None))
            out.witnesses.append({'role':role,'reference':clone(reference),'result_id':None,'fact':False})
            return
        valid=entry.record==record and store._binding_valid(entry)
        out.witnesses.append({'role':role,'reference':clone(reference),'result_id':entry.task_id,
                             'created_user_turn':entry.evidence.get('created_user_turn'),
                             'record':entry.record,'scope':clone(entry.parameters),'fact':valid,
                             'binding':clone(entry.evidence['binding'])})
        if not valid:
            out.conflicts.append('Referenced actual result has a wrong record or stale scientific binding');return
        if store._family(entry.capability)!=store._family(name):
            return # A declared non-geometric dependency is not a scope witness.
        binding=entry.evidence['binding']
        identity=(binding['record_fingerprint'],binding.get('artifact_id'),binding.get('artifact_fingerprint'))
        candidates.append((canonical_scope(entry.parameters),entry,identity))
    for row in references:
        add(row['entry'],'input_ref',row['reference'],row['delivery'])
    # Explicit dependencies determine the object. Own previous results are a
    # distinct fallback, never an extra competing producer or a graph search.
    if not candidates and not out.pending and previous is not None:
        if previous.record==record and store._binding_valid(previous):add(previous,'own_previous_result')
    if execution is not None:add(execution,'owned_execution_receipt')
    if artifact_id is not None:
        artifact=store.contexts[record].artifacts.get(artifact_id)
        owners=[e for e in store.entries if e.record==record and
                e.evidence['binding'].get('artifact_id')==artifact_id and store._binding_valid(e)]
        if artifact is None or not owners:
            out.conflicts.append('Explicit artifact is absent or has no valid provenance')
        else:
            # All candidates share this exact ID. Deduplication below requires
            # equivalent object facts; no "first similar historical result".
            for e in owners:add(e,'explicit_artifact')
    inherited={}
    for scoped,entry,identity in candidates:
        for key,value in scoped.items():
            if key in inherited and inherited[key]!=value:
                out.conflicts.append('Explicit sources identify conflicting scientific scopes')
            inherited[key]=value
    facts={b for s,e,b in candidates if e is not None}
    if len(facts)>1:out.conflicts.append('Explicit sources identify different actual artifacts or processing versions')
    if out.conflicts:return out
    actual=sorted((e for s,e,b in candidates if e is not None),key=lambda e:e.sequence)
    out.entry=actual[0] if actual else None
    out.scope={**clone(inherited),**clone(declared)}
    if spec.consumes_artifact:
        ids={e.evidence['binding'].get('artifact_id') for e in actual}
        ids.discard(None)
        out.artifact_id=next(iter(ids)) if len(ids)==1 else None
        if any(k in inherited and canonical_scope({k:v})[k]!=inherited[k] for k,v in declared.items()):
            out.conflicts.append('Declared scope conflicts with the explicitly selected artifact; use a lawful different producer')
        if artifact_id is not None and out.artifact_id!=artifact_id:
            out.conflicts.append('Explicit artifact differs from the declared producer')
    missing=set(store._required_fields(name))-set(out.scope)
    if missing:out.pending.append({'role':'user_parameters','fields':sorted(missing)})
    return out


def validate_scientific_sources(store,name,record,binding,interpretation,request_span=None):
    """Shared factual source interpretation, separate from readiness/completion.

    A fixed artifact supplies its own physical range. Current intent locators
    and historical range locators remain separate auditable roles; no proposal
    is rewritten, and explicit current changes cannot be hidden by inheritance.
    """
    from .scientific_request_binding import (resolve_action_source,interpreted_sources,
        resolve_source_ref,owned_intervals,RANGE)
    if not binding.ok:raise ValueError('; '.join(binding.conflicts))
    scope=binding.scope
    supplied={**scope,**({'artifact_id':binding.artifact_id} if binding.artifact_id else {})}
    resolution=resolve_action_source(store,name,supplied,record,request_span,inherited=binding.entry)
    if not resolution.ok:raise ValueError(resolution.message)
    if binding.artifact_id:
        selected=set(scope.get('labels',[]))
        expected=(float(scope['tmin']),float(scope['tmax']))
        for frame in resolution.frames:
            if frame.records!=(record,) or frame.object_family not in (None,'event'):continue
            if frame.object_names and not selected.intersection(frame.object_names):continue
            intervals=owned_intervals(store,frame,'event',selected)
            if not intervals and frame.object_parent is None:
                intervals={(float(a),float(b)) for a,b in RANGE.findall(frame.text)}
            if intervals and intervals!={expected}:
                raise ValueError('Current user window conflicts with the selected artifact')
    if not interpretation:return resolution,{}
    if interpretation.get('time_reference')!=resolution.time_reference:
        raise ValueError('Tool time reference conflicts with the task interpretation')
    pair=('tmin','tmax') if store._family(name)=='event' else ('start','end')
    key='labels' if pair[0]=='tmin' else 'channels'
    required=set(store._required_fields(name))
    for locator in ('source_ref','range_ref'):
        if locator not in interpretation:continue
        _,parent=resolve_source_ref(store,interpretation[locator])
        if parent.records and parent.records!=(record,):raise ValueError('Scientific source belongs to another record')
    measured=set(interpretation.get('measurement_channels',[]))
    if not measured.issubset(store.contexts[record].record.channel_names):
        raise ValueError('Measurement dimensions are absent from target metadata')
    range_locator=interpretation.get('range_ref',interpretation.get('source_ref'))
    if range_locator and all(k in scope for k in pair):
        _,parent=resolve_source_ref(store,range_locator)
        span=interpretation.get('range_span',parent.text)
        if span not in parent.text:raise ValueError('Range span is outside its complete source parent')
        intervals={(float(a),float(b)) for a,b in RANGE.findall(span)}
        if intervals and intervals!={tuple(float(scope[k]) for k in pair)}:
            raise ValueError('Proposed range conflicts with its explicit source locator')
    # Future outputs and absent conditions are represented, never promoted to
    # actual evidence by this check. Locator existence is checked by the caller.
    if binding.pending or not scope.get(key) or not required.issubset(scope):return resolution,{}
    if not binding.artifact_id:
        return resolution,interpreted_sources(store,name,scope,record,resolution,interpretation,binding.entry)
    if 'source_ref' not in interpretation:
        return resolution,interpreted_sources(store,name,scope,record,resolution,interpretation,binding.entry)
    turn,frame=resolve_source_ref(store,interpretation['source_ref'])
    if turn<store.turn:
        return resolution,interpreted_sources(store,name,scope,record,resolution,interpretation,binding.entry)
    matched=[f for f in resolution.frames if (f.start,f.end,f.text)==(frame.start,frame.end,frame.text)]
    if len(matched)!=1 or matched[0].records!=(record,):raise ValueError('Artifact intent source must identify its complete record-bound parent')
    context=store.contexts[record]
    measured=set(interpretation.get('measurement_channels',[]))
    if not measured.issubset(context.record.channel_names):raise ValueError('Measurement dimensions are absent from target metadata')
    named_channels={c for c in context.record.channel_names if store._contains(frame.text,c)}
    if measured and not measured.issubset(named_channels):
        raise ValueError('Measurement dimensions need literal names in their explicit intent source')
    # Field-only channel relations never authorize an event range.
    if interpretation.get('channel_reference'):raise ValueError('Channel field relations cannot replace an event artifact source')
    selected=set(scope[key]);available={e.label for e in context.record.events.events} if key=='labels' else set(context.record.channel_names)
    named={x for x in available if store._contains(frame.text,x)}
    if named and not selected.issubset(named):raise ValueError('Current source identifies a different scientific object')
    expected=tuple(float(scope[k]) for k in pair)
    if 'range_ref' in interpretation:
        _,window=resolve_source_ref(store,interpretation['range_ref'])
        if window.records!=(record,) or {(float(a),float(b)) for a,b in RANGE.findall(window.text)}!={expected}:
            raise ValueError('Range locator conflicts with the actual artifact window or record')
        if not all(store._contains(window.text,x) for x in selected):
            raise ValueError('Historical range parent does not identify the selected artifact object')
    return resolution,{k:{'kind':'artifact','artifact_id':binding.artifact_id,'record':record,
        'interpretation':clone(interpretation),'intent_source_turn':turn,'intent_source_span':frame.text,
        'semantic_status':'model_interpretation_not_intent_proof'} for k in scope}
