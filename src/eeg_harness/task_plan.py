"""Shared, bounded task DAG bookkeeping for Plan-and-Execute comparisons.

A plan is a model proposal, never a source of EEG facts or authorization. This
module does not execute tools, infer scientific scopes or evaluate acceptance
rules. All arms use the same identities, dependencies and revision semantics.
Exact numerical evidence continues to live in the existing TaskStore.
"""

from dataclasses import dataclass, field
import json


STATUSES = frozenset({"READY", "RUNNING", "WAITING_INPUT", "TOOL_SUCCEEDED",
    "DELIVERY_SATISFIED", "TASK_COMPLETED", "PARTIAL", "FAILED", "STALE"})
READ_LEVELS = frozenset({"summary", "result", "process"})


def _copy(value):
    """A finite JSON boundary also avoids aliasing caller-owned dictionaries."""
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _object(value, allowed, required, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    extra, missing = set(value) - set(allowed), set(required) - set(value)
    if extra or missing:
        raise ValueError(f"{label}: unknown fields {sorted(extra)}, missing fields {sorted(missing)}")


def _text(value, label, maximum=400):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{label} must be a nonempty string of at most {maximum} characters")
    return value


def _strings(value, label):
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    values = [_text(x, label, 100) for x in value]
    if len(set(values)) != len(values):
        raise ValueError(f"{label} contains duplicate identifiers")
    return values


def _path(value):
    if not isinstance(value, list) or not value or any(
            not (isinstance(x, str) and x or type(x) is int and x >= 0) for x in value):
        raise ValueError("A field path must be a nonempty list of string keys or nonnegative integer indices")
    return _copy(value)


@dataclass
class InputRef:
    task_id: str
    key: str
    fields: list = field(default_factory=list)
    level: str = "result"
    revision: int | None = None

    @classmethod
    def from_dict(cls, value):
        _object(value, {"task_id", "key", "fields", "level", "revision"}, {"task_id", "key"}, "InputRef")
        level = value.get("level", "result")
        if level not in READ_LEVELS:
            raise ValueError("InputRef.level must be summary, result or process")
        paths = value.get("fields", [])
        if not isinstance(paths, list) or len(paths) > 4:
            raise ValueError("InputRef.fields must contain at most four field paths")
        revision = value.get("revision")
        if revision is not None and (type(revision) is not int or revision < 1):
            raise ValueError("InputRef.revision must identify a positive existing version or be omitted")
        return cls(_text(value["task_id"], "InputRef.task_id", 100),
                   _text(value["key"], "InputRef.key", 100), [_path(p) for p in paths], level, revision)

    def to_dict(self):
        result = {"task_id": self.task_id, "key": self.key, "fields": self.fields, "level": self.level}
        if self.revision is not None:
            result["revision"] = self.revision
        return _copy(result)


def _rule(value):
    _object(value, {"path", "op", "value", "source"}, {"path", "op", "value"}, "acceptance_rule")
    if value["op"] not in {"eq", "gte", "lte"}:
        raise ValueError("Acceptance rule op must be eq, gte or lte")
    if type(value["value"]) not in {str, int, float, bool}:
        raise ValueError("Acceptance rule value must be a finite JSON scalar")
    result = {"path": _path(value["path"]), "op": value["op"], "value": value["value"]}
    if "source" in value:
        result["source"] = _text(value["source"], "acceptance_rule.source", 2000)
    return _copy(result)


def _interpretation(value):
    if value == {}:return {}
    _object(value, {'source_span','source_ref','time_reference','measurement_channels','range_span','range_ref','channel_reference'},
            {'time_reference'}, 'interpretation')
    if ('source_span' in value)==('source_ref' in value):raise ValueError('Use exactly one source_ref (preferred) or legacy source_span')
    for key in ('source_span','source_ref','range_ref'):
        if key in value:_text(value[key],key,4000)
    if 'range_span' in value and 'range_ref' in value:raise ValueError('Use one window locator')
    if value['time_reference'] not in {'record_absolute','event_relative'}:
        raise ValueError('Unknown time reference')
    if 'measurement_channels' in value:_strings(value['measurement_channels'],'measurement_channels')
    if 'range_span' in value:_text(value['range_span'],'range_span',4000)
    if 'channel_reference' in value:
        ref=value['channel_reference']
        if not isinstance(ref,dict) or set(ref) not in ({'source_span','target_span'},{'source_ref','target_ref'}):
            raise ValueError('Field reference needs source_ref/target_ref or legacy source_span/target_span')
        for span in value['channel_reference'].values():_text(span,'reference span',4000)
    return _copy(value)


@dataclass
class DeliveryItem:
    key: str
    capability: str
    record: str
    scope: dict
    input_refs: list[InputRef] = field(default_factory=list)
    required: bool = True
    acceptance_rule: list[dict] = field(default_factory=list)
    interpretation: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value):
        _object(value, {"key", "capability", "record", "scope", "input_refs", "required", "acceptance_rule", "interpretation"},
                {"key", "capability", "record", "scope"}, "DeliveryItem")
        if not isinstance(value["scope"], dict) or type(value.get("required", True)) is not bool:
            raise ValueError("DeliveryItem scope must be an object and required must be boolean")
        refs, rules = value.get("input_refs", []), value.get("acceptance_rule", [])
        if not isinstance(refs, list) or not isinstance(rules, list):
            raise ValueError("input_refs and acceptance_rule must be lists")
        parsed_refs = [InputRef.from_dict(r) for r in refs]
        fingerprints = [json.dumps(r.to_dict(), sort_keys=True) for r in parsed_refs]
        if len(set(fingerprints)) != len(fingerprints):
            raise ValueError("Duplicate input reference")
        return cls(_text(value["key"], "DeliveryItem.key", 100),
                   _text(value["capability"], "DeliveryItem.capability", 100),
                   _text(value["record"], "DeliveryItem.record", 100), _copy(value["scope"]),
                   parsed_refs, value.get("required", True), [_rule(r) for r in rules],
                   _interpretation(value.get('interpretation', {})))

    def to_dict(self):
        return _copy({"key": self.key, "capability": self.capability, "record": self.record,
            "scope": self.scope, "input_refs": [r.to_dict() for r in self.input_refs],
            "required": self.required, "acceptance_rule": self.acceptance_rule,
            **({'interpretation':self.interpretation} if self.interpretation else {})})


@dataclass
class TaskSpec:
    task_id: str
    goal: str
    dependencies: list[str]
    required_outputs: list[DeliveryItem]
    optional_operations: list[str] = field(default_factory=list)
    status: str = "READY"
    revision: int = 1
    outputs: dict = field(default_factory=dict)
    output_status: dict = field(default_factory=dict)
    attempts: list = field(default_factory=list)
    unresolved: list = field(default_factory=list)
    revision_history: list = field(default_factory=list)
    control_dependencies: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value, *, runtime=False):
        planned = {"task_id", "goal", "dependencies", "control_dependencies", "required_outputs", "optional_operations"}
        state = {"status", "revision", "outputs", "output_status", "attempts", "unresolved", "revision_history"}
        _object(value, planned | state if runtime else planned,
                {"task_id", "goal", "required_outputs"}, "TaskSpec")
        rows = value["required_outputs"]
        if not isinstance(rows, list) or not 1 <= len(rows) <= 12:
            raise ValueError("A task needs one to twelve independently identifiable delivery items")
        deliveries = [DeliveryItem.from_dict(r) for r in rows]
        if len({r.key for r in deliveries}) != len(deliveries) or not any(r.required for r in deliveries):
            raise ValueError("Task delivery keys must be unique and at least one delivery must be required")
        obj = cls(_text(value["task_id"], "TaskSpec.task_id", 100),
                  _text(value["goal"], "TaskSpec.goal", 2000),
                  _strings(value.get("dependencies", []), "TaskSpec.dependencies"), deliveries,
                  _strings(value.get("optional_operations", []), "TaskSpec.optional_operations"))
        obj.control_dependencies = _strings(value.get('control_dependencies', []), 'TaskSpec.control_dependencies')
        if runtime:
            obj.status = value.get("status", "READY")
            obj.revision = value.get("revision", 1)
            if obj.status not in STATUSES or type(obj.revision) is not int or obj.revision < 1:
                raise ValueError("Invalid task runtime status or revision")
            for key in ("outputs", "output_status"):
                if not isinstance(value.get(key, {}), dict):
                    raise ValueError(f"{key} must be an object")
                setattr(obj, key, _copy(value.get(key, {})))
            for key in ("attempts", "unresolved", "revision_history"):
                if not isinstance(value.get(key, []), list):
                    raise ValueError(f"{key} must be a list")
                setattr(obj, key, _copy(value.get(key, [])))
            declared = {r.key for r in deliveries}
            if set(obj.outputs) - declared or set(obj.output_status) - declared:
                raise ValueError("Runtime outputs must identify declared delivery keys")
            if any(s not in STATUSES for s in obj.output_status.values()):
                raise ValueError("Invalid output status")
        return obj

    def to_dict(self, *, runtime=True):
        result = {"task_id": self.task_id, "goal": self.goal,
            "dependencies": self.dependencies, "required_outputs": [r.to_dict() for r in self.required_outputs],
            "optional_operations": self.optional_operations}
        if self.control_dependencies:
            result['control_dependencies'] = self.control_dependencies
        if runtime:
            result.update(status=self.status, revision=self.revision, outputs=self.outputs,
                output_status=self.output_status, attempts=self.attempts, unresolved=self.unresolved,
                revision_history=self.revision_history)
        return _copy(result)

    def delivery(self, key):
        return next((d for d in self.required_outputs if d.key == key), None)

    def input_refs(self):
        return [ref for delivery in self.required_outputs for ref in delivery.input_refs]

    def control_prerequisites(self):
        # Legacy duplicated data declarations keep their original semantics.
        # Explicit control_dependencies are never erased by a data reference.
        data = {r.task_id for r in self.input_refs()}
        return set(self.control_dependencies) | (set(self.dependencies) - data)


class PlanGraph:
    """Transactional identity/dependency store shared by every comparison arm.

    Runtime result bindings must be written by the real execution adapter. The
    graph trusts those bindings but never a model-supplied status or result.
    Scheduling is deterministic; local scientific actions remain model choices.
    """

    def __init__(self, *, max_nodes=32, max_revisions=4):
        if type(max_nodes) is not int or max_nodes < 1 or type(max_revisions) is not int or max_revisions < 1:
            raise ValueError("Positive graph and revision limits are required")
        self.nodes = {}
        self.history = []
        self.max_nodes, self.max_revisions = max_nodes, max_revisions

    @staticmethod
    def _version(node, revision=None):
        if revision is None or revision == node.revision:
            return node.to_dict()
        return next((_copy(row["snapshot"]) for row in node.revision_history
                     if row["revision"] == revision), None)

    @staticmethod
    def _validate(nodes):
        for ident, node in nodes.items():
            controls = node.control_prerequisites()
            if ident in node.dependencies or ident in controls or any(dep not in nodes for dep in controls):
                raise ValueError(f"Task {ident} has a self or unknown dependency")
            for ref in node.input_refs():
                if ref.task_id not in nodes:
                    raise ValueError(f"Unknown upstream task {ref.task_id}")
                version = PlanGraph._version(nodes[ref.task_id], ref.revision)
                if version is None:
                    raise ValueError(f"Unknown upstream task revision {ref.task_id}@{ref.revision}")
                if not any(d["key"] == ref.key for d in version["required_outputs"]):
                    raise ValueError(f"Unknown upstream delivery {ref.task_id}/{ref.key}")
            # A task is a scientific goal, not necessarily one atomic tool.
            # Local output references order its deliveries, not the whole task.
            seen, stack = set(), set()
            def visit_output(key):
                if key in stack:raise ValueError('Delivery dependencies contain a cycle')
                if key in seen:return
                stack.add(key)
                for ref in node.delivery(key).input_refs:
                    if ref.task_id == ident and ref.revision in (None,node.revision):
                        visit_output(ref.key)
                stack.remove(key);seen.add(key)
            for delivery in node.required_outputs:visit_output(delivery.key)
        visited, active = set(), set()

        def visit(ident):
            if ident in active:
                raise ValueError("Task dependencies contain a cycle")
            if ident in visited:
                return
            active.add(ident)
            node = nodes[ident]
            # A pinned historical output has no scheduling edge to a newer
            # producer. Its own existence/status/binding are still checked.
            deps = node.control_prerequisites() | {r.task_id for r in node.input_refs()
                if r.task_id != ident and r.revision in (None,nodes[r.task_id].revision)}
            for dep in sorted(deps):
                visit(dep)
            active.remove(ident)
            visited.add(ident)

        for ident in nodes:
            visit(ident)

    def submit(self, nodes, replace=False):
        if not isinstance(nodes, list) or not nodes or type(replace) is not bool:
            raise ValueError("submit needs a nonempty list and a boolean replace")
        # Replacing a live graph would erase identity/history. Explicit local
        # revisions are the supported replan path; replace is initial-only.
        if replace and self.nodes:
            raise ValueError("A live graph cannot be replaced; revise stable task IDs or append tasks")
        parsed = [TaskSpec.from_dict(n.to_dict(runtime=False) if isinstance(n, TaskSpec) else n) for n in nodes]
        ids = [n.task_id for n in parsed]
        if len(set(ids)) != len(ids) or set(ids) & set(self.nodes):
            raise ValueError("Duplicate task IDs; use revise for existing tasks")
        proposed = dict(self.nodes)
        proposed.update({n.task_id: n for n in parsed})
        if len(proposed) > self.max_nodes:
            raise ValueError("Task graph node limit exceeded")
        self._validate(proposed)
        self.nodes = proposed
        self.history.append({"event": "plan_submitted", "task_ids": ids,
                             "specifications": [n.to_dict(runtime=False) for n in parsed],
                             "dependency_relations":{n.task_id:self.dependency_relations(n) for n in parsed}})
        return parsed

    def resolve_ref(self, ref):
        """Resolve current or pinned historical delivery without changing facts.

        A historical reference stays linked to its old result/processing scope;
        it never silently follows a newly revised current node. The caller still
        validates the real TaskStore binding and scientific applicability.
        """
        ref = InputRef.from_dict(ref) if isinstance(ref, dict) else ref
        node = self.nodes.get(ref.task_id)
        version = self._version(node, ref.revision) if node else None
        if version is None or not any(d["key"] == ref.key for d in version["required_outputs"]):
            raise ValueError("Unknown upstream task, output key or revision")
        return {"task_id": ref.task_id, "key": ref.key, "revision": version["revision"],
                "status": version["status"], "goal": version["goal"],
                "output": _copy(version["outputs"].get(ref.key)),
                "output_status": version["output_status"].get(ref.key),
                "delivery": next(_copy(d) for d in version["required_outputs"] if d["key"] == ref.key)}

    def dependency_relations(self, node):
        """Derived auditable relations; never a second mutable edge store."""
        return {'control': sorted(node.control_prerequisites()),
            'data':[{'consumer_key':d.key, 'task_id':r.task_id, 'key':r.key,
                     'revision':r.revision, 'source':'input_refs'}
                    for d in node.required_outputs for r in d.input_refs]}

    def dependency_state(self, task_id):
        node = self.nodes[task_id]
        blocked = []
        for dep in sorted(node.control_prerequisites()):
            if self.nodes[dep].status != 'TASK_COMPLETED':
                blocked.append({'task_id':dep,'reason':'control_dependency_not_completed'})
        for ref in node.input_refs():
            if ref.task_id == task_id:continue # local readiness belongs to the delivery action
            resolved = self.resolve_ref(ref)
            if not (resolved['output'] is not None and resolved['output_status'] in {'DELIVERY_SATISFIED','TASK_COMPLETED'}):
                blocked.append({'task_id':ref.task_id,'key':ref.key,'revision':ref.revision,'reason':'required_input_not_delivered'})
        return {"ready": not blocked, "blocked": blocked}

    def ready_nodes(self):
        return [node for node in self.nodes.values()
                if node.status in {"READY", "RUNNING", "STALE", "TOOL_SUCCEEDED", "DELIVERY_SATISFIED"}
                and self.dependency_state(node.task_id)["ready"]]

    def set_status(self, task_id, status, unresolved=None):
        if status not in STATUSES:
            raise ValueError("Unknown task status")
        if unresolved is not None and not isinstance(unresolved, list):
            raise ValueError("unresolved must be a list")
        node = self.nodes[task_id]
        node.status = status
        if unresolved is not None:
            node.unresolved = _copy(unresolved)
        self.history.append({"event": "task_state", "task_id": task_id,
                             "revision": node.revision, "status": status})

    def mark_output(self, task_id, key, evidence, status="DELIVERY_SATISFIED"):
        """Called only by the adapter after real result/identity validation."""
        node = self.nodes[task_id]
        if node.delivery(key) is None or status not in STATUSES:
            raise ValueError("Output must match a declared key and a known status")
        node.outputs[key], node.output_status[key] = _copy(evidence), status
        self.history.append({"event": "result_bound", "task_id": task_id,
            "revision": node.revision, "key": key, "status": status, "evidence": _copy(evidence)})

    @staticmethod
    def affected_local_outputs(node, keys):
        affected=set(keys)
        while True:
            added={d.key for d in node.required_outputs if any(
                r.task_id==node.task_id and r.revision is None and r.key in affected for r in d.input_refs)}-affected
            if not added:return affected
            affected.update(added)

    def revise(self, task_id, updates, reason):
        """Revise a stable task; preserve old evidence and invalidate consumers.

        Unchanged output keys remain reusable. Only descendants referencing an
        altered key are invalidated; an untyped control-only dependency is
        conservatively invalidated because it declared no finer data relation.
        This bookkeeping cannot authorize any newly proposed EEG parameters.
        """
        _text(reason, "revision reason", 2000)
        _object(updates, {"goal", "dependencies", "control_dependencies", "required_outputs", "optional_operations"}, set(), "revision")
        if not updates:
            raise ValueError("A revision must change at least one planned field")
        old = self.nodes[task_id]
        if old.revision >= self.max_revisions:
            raise ValueError("Task revision limit exceeded")
        spec = old.to_dict(runtime=False)
        spec.update(_copy(updates))
        revised = TaskSpec.from_dict(spec)
        # Adding a data reference must not silently reclassify an existing
        # legacy control prerequisite as redundant data. Only an explicit
        # task-level dependency edit may change that control commitment.
        if not {'dependencies','control_dependencies'} & set(updates):
            lost_controls = old.control_prerequisites() - revised.control_prerequisites()
            revised.control_dependencies = sorted(set(revised.control_dependencies) | lost_controls)
        if revised.to_dict(runtime=False) == old.to_dict(runtime=False):
            raise ValueError("A no-op revision does not create a new version")
        proposed = dict(self.nodes)
        old_items = {d.key: d.to_dict() for d in old.required_outputs}
        new_items = {d.key: d.to_dict() for d in revised.required_outputs}
        changed = {k for k in old_items.keys() | new_items.keys() if old_items.get(k) != new_items.get(k)}
        if old.control_prerequisites() != revised.control_prerequisites():
            changed |= set(new_items)
        changed = self.affected_local_outputs(revised,changed)
        revised.revision = old.revision + 1
        revised.revision_history = _copy(old.revision_history) + [{"revision": old.revision,
            "reason": reason, "snapshot": old.to_dict()}]
        revised.attempts = _copy(old.attempts)
        revised.outputs = {k: _copy(v) for k,v in old.outputs.items() if k not in changed and k in new_items}
        revised.output_status = {k:v for k,v in old.output_status.items() if k in revised.outputs}
        revised.status = "READY" if changed else old.status
        revised.unresolved = [] if changed else _copy(old.unresolved)
        proposed[task_id] = revised
        self._validate(proposed)
        affected = {task_id: changed}
        invalidated = []
        queue = [task_id] if changed else []
        while queue:
            upstream_id = queue.pop(0)
            for ident, node in proposed.items():
                if ident == task_id:
                    continue
                keys = {d.key for d in node.required_outputs if any(
                    r.task_id == upstream_id and r.revision is None and r.key in affected[upstream_id]
                    for r in d.input_refs)}
                if upstream_id in node.control_prerequisites():
                    keys = {d.key for d in node.required_outputs}
                keys = self.affected_local_outputs(node,keys)
                newly = keys - affected.get(ident, set())
                if newly:
                    affected.setdefault(ident, set()).update(newly)
                    queue.append(ident)
        self.nodes = proposed
        for ident, keys in affected.items():
            if ident == task_id:
                continue
            node = self.nodes[ident]
            # Do not delete historical numerical results: old bindings stay in
            # TaskStore and the graph's immutable audit snapshot.
            self.history.append({"event": "dependent_invalidated", "task_id": ident,
                "upstream": task_id, "keys": sorted(keys), "previous": node.to_dict()})
            for key in keys:
                node.outputs.pop(key, None)
                node.output_status[key] = "STALE"
            node.status = "STALE"
            node.unresolved = [{"code": "UPSTREAM_REVISION", "task_id": task_id,
                                "affected_keys": sorted(keys)}]
            invalidated.append(ident)
        result = {"task_id": task_id, "revision": revised.revision,
                  "changed_keys": sorted(changed), "invalidated": invalidated}
        self.history.append({"event": "task_revised", "reason": reason,
                             **_copy(result), "previous": old.to_dict()})
        return result

    def to_dict(self):
        return {"nodes": [n.to_dict() for n in self.nodes.values()],
                "history": _copy(self.history), "max_nodes": self.max_nodes,
                "max_revisions": self.max_revisions}


_STRING = {"type": "string", "minLength": 1}
_PATH = {"type": "array", "minItems": 1, "items": {"type": ["string", "integer"]}}
INPUT_REF_SCHEMA = {"type": "object", "properties": {
    "task_id": _STRING, "key": _STRING,
    "fields": {"type": "array", "maxItems": 4, "items": _PATH},
    "level": {"type": "string", "enum": sorted(READ_LEVELS)},
    "revision": {"type": "integer", "minimum": 1,
                 "description": "Optional pinned existing task revision; omitted follows the current revision."}},
    "required": ["task_id", "key"], "additionalProperties": False}
DELIVERY_SCHEMA = {"type": "object", "properties": {
    "key": _STRING, "capability": _STRING, "record": _STRING,
    "scope": {"type": "object", "description": "Scientific computation conditions; missing values remain missing, never inferred from the plan."},
    "interpretation": {"type":"object", "description":"Auditable semantic interpretation, not EEG facts. Use for mixed objects or field references; preserve the complete source clause. Measurement channels do not choose the time base.",
        "properties":{"source_span":_STRING,"time_reference":{"type":"string","enum":["record_absolute","event_relative"]},
            "measurement_channels":{"type":"array","items":_STRING,"description":"Actual target channels; names must occur in the source clause or be justified by channel_reference."},"range_span":_STRING,
            "channel_reference":{"type":"object","description":"When channel names come from another clause, express that field relation here, using complete original source and target clauses. Target record/window remain independent.","properties":{"source_span":_STRING,"target_span":_STRING},
                "required":["source_span","target_span"],"additionalProperties":False}},
        "required":["source_span","time_reference"],"additionalProperties":False},
    "input_refs": {"type": "array", "items": INPUT_REF_SCHEMA,
        "description":"The sole data dependency declaration: no duplicate task dependencies needed. Same-task current keys must be acyclic. Pinned revisions retain that version's actual evidence."},
    "required": {"type": "boolean"},
    "acceptance_rule": {"type": "array", "items": {"type": "object", "properties": {
        "path": _PATH, "op": {"type": "string", "enum": ["eq", "gte", "lte"]},
        "value": {"type": ["string", "number", "boolean"]}, "source": _STRING},
        "required": ["path", "op", "value"], "additionalProperties": False}}},
    "required": ["key", "capability", "record", "scope"], "additionalProperties": False}
TASK_SPEC_SCHEMA = {"type": "object", "properties": {
    "task_id": _STRING, "goal": _STRING,
    "dependencies": {"type": "array", "items": _STRING,
        "description":"Legacy: entries already named in input_refs are redundant data declarations; other entries require whole-task completion. Prefer control_dependencies for explicit control prerequisites."},
    "control_dependencies": {"type":"array","items":_STRING,
        "description":"Independent whole-task completion prerequisites, enforced even when also referencing a delivery. Data dependencies need only input_refs."},
    "required_outputs": {"type": "array", "minItems": 1, "maxItems": 12, "items": DELIVERY_SCHEMA},
    "optional_operations": {"type": "array", "items": _STRING}},
    "required": ["task_id", "goal", "required_outputs"], "additionalProperties": False}
PLAN_NODES_SCHEMA = {"type": "array", "minItems": 1, "maxItems": 32, "items": TASK_SPEC_SCHEMA}


def task_spec_schema(registry):
    """Shared derived scope vocabulary, never a second tool parameter table."""
    from .scientific_contracts import scope_groups
    spec=_copy(TASK_SPEC_SCHEMA)
    spec['properties']['task_id']['maxLength']=100
    spec['properties']['goal']['maxLength']=2000
    spec['properties']['dependencies']['items']['maxLength']=100
    spec['properties']['optional_operations']['items'].update(maxLength=100)
    item=spec['properties']['required_outputs']['items']
    for key in ('key','capability','record'):item['properties'][key]['maxLength']=100
    interpretation=item['properties']['interpretation']
    interpretation['description']='Semantic proposal, not facts. Prefer source_ref from the visible catalog; legacy source_span is exclusive. Historical object plus current range_ref may express a lawful supplement.'
    interpretation['properties'].update(source_ref=_STRING,range_ref=_STRING)
    interpretation['required']=['time_reference']
    interpretation['oneOf']=[{'required':['source_ref'],'properties':{'source_span':{'type':'null'}}},
                             {'required':['source_span'],'properties':{'source_ref':{'type':'null'}}}]
    interpretation['not']={'required':['range_ref','range_span']}
    ref=interpretation['properties']['channel_reference']
    ref['properties'].update(source_ref=_STRING,target_ref=_STRING)
    ref['required']=[]
    ref['oneOf']=[{'properties':{key:_STRING for key in keys},'required':keys,'additionalProperties':False}
                  for keys in (['source_ref','target_ref'],['source_span','target_span'])]
    groups=scope_groups(registry)+[{'names':['compare_results'],'schema':{'type':'object','properties':{},'additionalProperties':False}}]
    item['properties']['capability']['enum']=[n for g in groups for n in g['names']]
    item['allOf']=[{'if':{'properties':{'capability':{'enum':g['names']}}},
                   'then':{'properties':{'scope':g['schema']}}} for g in groups]
    return spec
