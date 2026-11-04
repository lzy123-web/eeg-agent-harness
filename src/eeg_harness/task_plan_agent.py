"""Shared Plan-and-Execute controls over the original EEGAgent and Executor.

The plan is a model proposal, never a source of scientific authorization. A/B/C
share identity, provenance, versions, full read rights and local replanning.
Only acceptance automation and dependency evidence presentation are varied.
"""
import hashlib
import json
import re
from copy import deepcopy

from .agent import EEGAgent
from .executor import _validate_schema
from .tooling import ToolRequest
from .working_memory import WorkingMemoryStore, NUMERIC_TOOLS, clone, encoded
from .working_memory_agent import WorkingMemoryController, control, STRING
from .working_memory_managed import ManagedMemoryController, managed_controls
from .working_memory_scientific import ScientificMemoryController
from .working_memory_scientific_tasks import ScientificTaskStore, canonical_scope, RequirementValidationError
from .working_memory_lifecycle import METADATA
from .result_semantics import read_scalar, result_field_semantics
from .task_plan import PlanGraph, TaskSpec, DeliveryItem
from .scientific_contracts import (ContractError, validate_contract, computation_scope,
                                   contract_diagnostics, selected_contract)
from .scientific_binding import resolve_scientific_binding, validate_scientific_sources


ARMS = ("A", "B", "C", "C-no-delivery", "C-no-selection", "A-equivalent")
OWNER_PROPERTIES={
    'task_id':{**STRING,'description':'Explicit owner. Required for every scientific action in a multi-call batch.'},
    'output_key':{**STRING,'description':'Exact delivery key; use with task_id. No scope copying needed.'},
    'revision':{'type':'integer','minimum':1,'description':'Optional expected task revision; stale values reject.'}}
SYSTEM = """你是多任务EEG分析Agent。先依据用户原请求提出最小科学任务DAG(plan_tasks)，不是固定工具脚本。
同一目的可有多个不同窗口或记录的结果key。task_id由你提出后保持稳定；改标题不创建新身份。补参/条件修订用revise_plan，原结果与旧版本保留。
input_refs是数据依赖唯一声明，程序派生关系，无需重复dependencies；control_dependencies表示另需整个上游任务完成的控制前提。引用明确key、字段、版本和summary/result/process层级。计划不是科学授权；数值参数仍必须来自真实用户或合法历史。
新增科学测量用plan_tasks(deliveries)：每行给task_id/key和实际科学选择，同一task_id的多个交付合成同一节点。修改现有测量必须选原task_id/output_key/revision，用revise_plan直接写scope/interpretation等变化，未改事实由程序保留；无需重写整任务或changes/updates容器。scope/interpretation按字段合并，引用/条件列表整体替换；改scope须给合法来源或范围引用，程序不代选。
比较在plan_tasks的交付行选capability=compare_results，明确left/right各自task_id/key/revision和单个field；结果为right-minus-left及right/left。程序从所选操作数补齐记录/空计算scope，不让比较重述EEG条件。省略revision表示当前版本，固定历史必须明确revision。
新建节点、结果inherit_result谱系、原任务身份修订是不同操作：inherit_result只继承真实科学条件，不会修订DAG任务。用户改变已选测量时保留其task_id；独立新分析仍新建，不按名称相似推断。
回顾已有结果直接read_dependency/read_result/restore_task或使用已可见证据，不新建重复计算义务；追加测量只登记真正新增交付并引用实际工件。比较仍须明确两侧标量fields，不猜字段/方向。
科学动作使用task_id与output_key明确归属，可省略已明确scope；revision可防过期。同批动作依次执行，各自绑定owner，不依赖前面select的可变current。单步旧入口可省owner，但多输出必须明确。无需反复抄工件/结果ID。
需要上游工件时使用input_refs提供的真实句柄；compare_results对真实结果做描述性差值比值，不心算。跨记录/版本不能混用；事件窗是相对时间，连续窗是记录绝对时间。未授权的处理不能执行。
所有方案都能read_dependency/read_result或restore_task，精确数值读取与过程恢复不同。摘要足够则不强迫多读；要核对过程再继续时恢复原行动观察，不能把索引当数值。
check_deliveries可读所有方案相同的交付诊断。明确质量/计数条件须依据实际结果判断；辅助尝试失败不等于科学交付失败。缺参可wait_node并推进独立节点，最后真实澄清或partial。
complete_node(task_id,output_key,revision,result_id)只接受对应真实交付，可先接受生产者再执行同任务消费者；不完成或归档整个任务。身份来自当前真实结果，不猜测。省略output_key才表示完成整个任务，须所有必需交付齐全。接受不等于诊断条件成立。
不要删除用户要求或降低科学条件以完成任务。任务完成不证明原自然请求无遗漏。finish_task必须给原用户所需实际数值、单位、来源/范围、新旧版本及未完成事项；不作诊断或无依据的因果解释。
混合对象或字段省略时，在交付项interpretation使用scientific_source_frames的source_ref、time_reference、measurement_channels；channel_reference用source_ref/target_ref仅引用通道名称。补参或改窗用revise_plan保留旧source_ref并指向当前range_ref，或改用当前完整来源。引用只是定位，不证明语义；事件测量通道不改变时基，不猜缺窗，不在动作侧另改解释。
若需要用户补参，finish_task.clarifications列出task_id/key/fields，程序核验实际缺失并把明确问题送达。仅wait_node或写无关问题不算询问。报告频带/指标放goal，scope只放广告中的计算条件。
"""


class PlannedTaskStore(ScientificTaskStore):
    """Common fixes, not a candidate-only safety advantage; old modes untouched."""

    def completion_check(self, goal):
        result = super().completion_check(goal)
        # Pending proposals are observations, not additional scientific debts.
        ready = bool(result["requirements"]) and all(
            r["status"] == "satisfied" for r in result["requirements"])
        result.update(valid=ready, ready=ready,
                      code=None if ready else "TASK_REQUIREMENTS_PENDING")
        return result

    def execute_action(self, name, arguments, record=None, **kwargs):
        if name not in METADATA:
            return super().execute_action(name, arguments, record=record, **kwargs)
        # Read-only metadata has no computational window to inherit. Identity
        # remains explicit; a guessed alias is never silently substituted.
        alias = record or self.active_record
        if alias not in self.records or self.active is None:
            return self._error("RECORD_NOT_FOUND", "Select a known record in a current task")
        self.active.record = self.active_record = alias
        self.active.scope = clone(arguments)
        self._action_sources = {}
        try:
            return WorkingMemoryStore.execute_numeric(self, name, arguments)
        finally:
            self._action_sources = None


class TaskPlanController(ScientificMemoryController):
    def __init__(self, store, *, arm="C", **options):
        if arm not in ARMS:
            raise ValueError("Unknown comparison arm")
        super().__init__(store, context_mode="working", **options)
        self.arm = arm
        self.graph = PlanGraph()
        self.current = None
        self.node_goals = {}
        self.evidence_log = []
        self.plan_events = []
        self.turn_nodes = set()
        self.action_transitions = []
        self.clarifications = []
        self.batch_size = 1
        self.pending_archive = None
        self.automatic_acceptance = arm in {"C", "C-no-selection", "A-equivalent"}
        self.dependency_selection = arm in {"C", "C-no-delivery"}

    def begin_turn(self, request):
        super().begin_turn(request)
        self.current = None
        self.turn_nodes = set()
        self.clarifications = []
        self.repair_credits = 0
        self.previous_issues = None
        self.rejection_facts = set()
        self.progress_events = []
        self.redundant_observations = 0
        self.delivery_review = None

    def _progress_state(self):
        return encoded({k:{'revision':n.revision,'declared':[d.to_dict() for d in n.required_outputs],
            'outputs':n.outputs,'output_status':n.output_status,'status':n.status}
            for k,n in self.graph.nodes.items()})

    @staticmethod
    def _observation_atoms(value):
        """Keep object/field/value/semantics associations as indivisible facts.

        This is a conservative review signal, never evidence authorization.
        Evidence carried inside different native envelopes remains readable.
        """
        atoms=set()
        volatile={'request_id','tool_call_id','duration_ms','progress','timestamp_utc','call_id',
                  'status','message','instruction','meaning','via'}
        def walk(v,path=(),owner=None):
            if isinstance(v,dict):
                ident=v.get('result_id') or v.get('task_id') or v.get('artifact_id')
                if isinstance(ident,str):
                    owner={k:clone(v[k]) for k in ('record','revision','key','parameters','scope','artifact_id') if k in v}
                    owner['identity']=ident;path=()
                if isinstance(v.get('path'),list):
                    # Scalar value and its full path/unit/type cannot be
                    # recombined from facts about another channel or version.
                    atom={k:clone(x) for k,x in v.items() if k not in volatile}
                    atoms.add(encoded([owner,atom]));return
                for k,x in v.items():
                    if k not in volatile:walk(x,(*path,k),owner)
            elif isinstance(v,list):
                for i,x in enumerate(v):walk(x,(*path,i),owner)
            else:
                atoms.add(encoded([owner,list(path),v]))
        walk(value)
        return atoms

    def _visible_atoms(self):
        atoms=set()
        for message in self.last_view or []:
            if message.get('role') not in {'user','tool'}:continue
            try:atoms |= self._observation_atoms(json.loads(message.get('content','')))
            except (ValueError,TypeError):pass
        return atoms

    def _observe_control_progress(self,request,result):
        successful=result.get('status') not in {'rejected','blocked'}
        state_changed=self._progress_state()!=self._action_state_before
        read=request.name in {'read_result','read_dependency','restore_task','check_deliveries'}
        atoms=self._observation_atoms(result) if successful and read else set()
        new_information=bool(atoms-self._visible_atoms()) if atoms else False
        diag=result.get('structure_diagnostics',{})
        issues=frozenset(encoded([i['path'],i['rule']]) for i in diag.get('issues',[]))
        # Identity changes cannot claim correction; a global per-turn credit
        # ceiling also prevents cycling through unrelated proposals.
        target=encoded({'tool':request.name,'target':request.arguments.get('task_id'),
            'key':request.arguments.get('output_key'),
            'rows':[(r.get('task_id'),r.get('key'),r.get('capability')) for r in
                request.arguments.get('deliveries',request.arguments.get('add_deliveries',[])) if isinstance(r,dict)]})
        prev=self.previous_issues
        correction=bool(not successful and issues and not diag.get('truncated') and prev and
            prev[0]==target and issues<prev[1] and self.repair_credits<self.no_progress_limit)
        rejection_fact=encoded([request.name,result.get('code'),result.get('field_path'),result.get('message')])
        # A newly exposed execution prerequisite is diagnostic information,
        # not state advancement. It shares the same finite credit ceiling;
        # changing arguments or cycling error classes never resets errors.
        new_rejection=bool(not successful and not diag and self.errors and
            rejection_fact not in self.rejection_facts and self.repair_credits<self.no_progress_limit)
        if not successful:
            self.errors += 0 if correction or new_rejection else 1
            if correction or new_rejection:self.repair_credits+=1
            self.rejection_facts.add(rejection_fact)
            self.previous_issues=(target,issues) if issues and not diag.get('truncated') else None
            kind='bounded_structure_correction' if correction else 'bounded_new_rejection_information' if new_rejection else 'rejected_without_progress'
        elif state_changed or new_information:
            self.errors=0;self.previous_issues=None;self.redundant_observations=0
            kind='state_change' if state_changed else 'new_visible_information'
        else:
            kind='redundant_observation' if read else 'unchanged_action'
            self.redundant_observations+=1
        self.progress_events.append({'tool':request.name,'kind':kind,'errors':self.errors,
            'repair_credits':self.repair_credits,'structure_diagnostics':clone(diag)})

    def _compatibility_controls(self):
        from .task_plan import task_spec_schema, PLAN_NODES_SCHEMA
        schema=task_spec_schema(next(iter(self.store.contexts.values())).executor.registry)
        delivery_properties=schema['properties']['required_outputs']['items']['properties']
        patch_properties={k:clone(delivery_properties[k]) for k in ('scope','interpretation','input_refs','acceptance_rule')}
        patch_properties['interpretation']={'type':'object',
            'properties':clone(delivery_properties['interpretation']['properties']),'additionalProperties':False}
        controls = [c for c in super().control_definitions()
                    if c["function"]["name"] != "focus_task"]
        next(c["function"] for c in controls if c["function"]["name"] == "compare_results")["parameters"]["required"] = []
        controls += [
            control("plan_tasks", "Propose scientific subtask DAG from the user request. No runtime facts or result IDs may be invented.", {
                "nodes": {"type": "array", "minItems": 1, "maxItems": PLAN_NODES_SCHEMA['maxItems'],
                          "items": schema}}, ["nodes"]),
            control("revise_plan", "Modify one existing delivery using output_key, expected revision and changes; scope/interpretation merge explicit fields, lists replace. Choosing source_ref/source_span or range_ref/range_span replaces its old alternative; supplying both is invalid. Unchanged objects/sources/other deliveries are preserved. Or use legacy updates for a whole-task transaction, never both. All paths validate sources/obligations before commit.", {
                "task_id": STRING, "updates": {"type": "object", "properties": {
                    k:clone(v) for k,v in schema['properties'].items() if k!='task_id'},
                    "additionalProperties":False}, "output_key":STRING,
                "revision":{'type':'integer','minimum':1},
                "changes":{'type':'object','properties':patch_properties,'additionalProperties':False},
                "reason": STRING}, ["task_id", "reason"]),
            control("select_task", "Choose a ready independent node; no fabricated dependency satisfaction.", {"task_id": STRING}, ["task_id"]),
            control("complete_node", "Accept one existing delivery with output_key + current revision + actual result_id (or comparison_id value), without closing its task. Omit output_key to complete the whole task after all required results exist. No mandatory extra read when evidence is already visible.", {
                "task_id": STRING, "output_key": STRING, "revision": {"type":"integer","minimum":1},
                "result_id": STRING}, ["task_id"]),
            control("wait_node", "Suspend this node for genuine missing science or inability; other ready nodes remain available.", {"task_id": STRING, "reason": STRING}, ["task_id", "reason"]),
            control("check_deliveries", "Read real output matching and scientific predicate evaluation; equally available to every arm.", {"task_id": STRING}, ["task_id"]),
            control("read_dependency", "Read a selected key/version. contract discovers actual scalar paths/types/units without values or evidence promotion, even before a consumer is planned; undelivered keys expose only their declared plan. summary/result/process read actual evidence. All modes have identical raw evidence and process read rights.", {
                "task_id": STRING, "key": STRING, "revision":{"type":"integer","minimum":1}, "level": {"type":"string","enum":["contract","summary","result","process"]},
                "fields": {"type":"array","maxItems":4,"items":{"type":"array","items":{"type":["string","integer"]}}}}, ["task_id","key","level"]),
        ]
        revision=next(c['function']['parameters'] for c in controls if c['function']['name']=='revise_plan')
        revision['oneOf']=[{'required':['updates'],'not':{'required':['changes']}},
            {'required':['output_key','revision','changes'],'not':{'required':['updates']}}]
        finish=next(c['function'] for c in controls if c['function']['name']=='finish_task')
        finish['parameters']['properties']['clarifications']={'type':'array','maxItems':12,'items':{
            'type':'object','properties':{'task_id':STRING,'key':STRING,
                'fields':{'type':'array','minItems':1,'items':STRING}},
            'required':['task_id','key','fields'],'additionalProperties':False},
            'description':'Ask for actual missing fields of a registered delivery. Validated questions are appended to the delivered answer; internal waiting alone is not a question.'}
        return controls

    def control_definitions(self):
        from .task_plan import model_write_schemas
        controls=self._compatibility_controls()
        create,revise=model_write_schemas(next(iter(self.store.contexts.values())).executor.registry)
        for row in controls:
            f=row['function']
            if f['name']=='plan_tasks':
                f.update(parameters=create,description='Create NEW tasks from flat delivery rows; same task_id groups multiple keys. Explicit compare_results left/right scalar selections produce right-minus-left and right/left; record and empty scope are derived from the selected operands. Do not redeclare an existing identity.')
            elif f['name']=='revise_plan':
                f.update(parameters=revise,description='Revise an EXISTING task at its expected revision. Select output_key to patch one existing delivery; add_deliveries explicitly appends new keys to that task. Both may be one atomic transaction (for example new producer plus changed consumer input_refs). Write only changed scope/interpretation or replacement lists, no changes/updates wrapper. Preserve identity and unchanged evidence. left/right select comparison operands. Alternatively plan_tasks can create a separate producer, then revise_plan changes the existing consumer. Source, version and transaction checks still apply.')
        return controls

    @staticmethod
    def _scalar_reference(value):
        return {k:clone(v) for k,v in value.items() if k!='field'}|{'fields':[clone(value['field'])],'level':'result'}

    def _normalize_write(self,name,args):
        """Mechanical projection into the existing transactional write path."""
        if name=='revise_plan':
            additions=args.get('add_deliveries',[])
            changes={k:clone(v) for k,v in args.items() if k not in {'task_id','output_key','revision','reason','add_deliveries'}}
            if 'left' in changes or 'right' in changes:
                old=self.graph.nodes.get(args['task_id'])
                d=old.delivery(args['output_key']) if old else None
                if not d or d.capability!='compare_results':raise ContractError(('left',),'Operand changes require an existing comparison delivery')
                refs=[r.to_dict() for r in d.input_refs]
                for i,side in enumerate(('left','right')):
                    if side in changes:refs[i]=self._scalar_reference(changes.pop(side))
                changes['input_refs']=refs
            normalized={k:clone(args[k]) for k in ('task_id','output_key','revision','reason') if k in args}|{'changes':changes}
            if not additions:return normalized
            old=self.graph.nodes.get(args['task_id'])
            if old is None:raise ContractError(('task_id',),'Select an existing task for an append transaction')
            if args['revision']!=old.revision:raise ContractError(('revision',),'Select the existing task current revision')
            if 'output_key' in args and old.delivery(args['output_key']) is None:
                raise ContractError(('output_key',),'Unknown existing delivery key; append uses add_deliveries keys')
            keys=[d.key for d in old.required_outputs]+[d['key'] for d in additions]
            if len(keys)!=len(set(keys)):raise ContractError(('add_deliveries',),'New keys must be distinct from existing and other new keys; patch existing keys with output_key')
            rows=(self._revision_updates(old,normalized)['required_outputs'] if changes else
                  [d.to_dict() for d in old.required_outputs])
            try:proposed=self._normalize_write('plan_tasks',{'deliveries':[dict(d,task_id=old.task_id) for d in additions]})
            except ContractError as exc:
                raise ContractError(('add_deliveries',*exc.path[1:]) if exc.path[:1]==['deliveries'] else exc.path,str(exc)) from exc
            rows.extend(proposed['nodes'][0]['required_outputs'])
            return {k:clone(args[k]) for k in ('task_id','revision','reason')}|{'updates':{'required_outputs':rows}}
        rows=args['deliveries'];nodes={}
        def operand_record(ref,seen=(),path=('deliveries',)):
            ident=(ref['task_id'],ref['key'])
            if ident in seen:raise ContractError(path,'Comparison operand cycle')
            matches=[r for r in rows if (r['task_id'],r['key'])==ident]
            if ref['task_id'] in self.graph.nodes and (not matches or 'revision' in ref):
                try:return self.graph.resolve_ref(self._scalar_reference(ref))['delivery']['record']
                except ValueError as exc:raise ContractError(path,str(exc)) from exc
            if len(matches)!=1 or ref.get('revision',1)!=1:raise ContractError(path,'Operand must select one existing or explicitly proposed delivery/version')
            d=matches[0]
            return d['record'] if d['capability']!='compare_results' else operand_record(d['left'],(*seen,ident),path)
        for index,row in enumerate(rows):
            ident=row['task_id'];goal=row.get('goal',ident)
            node=nodes.setdefault(ident,{'task_id':ident,'goal':goal,'required_outputs':[],
                'control_dependencies':[],'optional_operations':[]})
            if 'goal' in row and node['goal'] not in (ident,goal):raise ContractError(('goal',),'One task identity needs one goal')
            if 'goal' in row:node['goal']=goal
            for key in ('control_dependencies','optional_operations'):
                node[key]=list(dict.fromkeys([*node[key],*row.get(key,[])]))
            d={k:clone(v) for k,v in row.items() if k not in {'task_id','goal','control_dependencies','optional_operations','left','right'}}
            if row['capability']=='compare_results':
                d.update(record=operand_record(row['left'],path=('deliveries',index,'left')),scope={},input_refs=[self._scalar_reference(row[k]) for k in ('left','right')])
            node['required_outputs'].append(d)
        return {'nodes':list(nodes.values())}

    def tool_definitions(self):
        tools=super().tool_definitions()
        for tool in tools:
            f=tool['function']
            if f['name'] in NUMERIC_TOOLS | {'compare_results'}:
                f['parameters']['properties'].update(clone(OWNER_PROPERTIES))
                f['parameters']['properties'].pop('request_span',None)
        return tools

    def execute(self,request,*,batch_size=1):
        self.batch_size=batch_size
        self._action_state_before=self._progress_state()
        def state():return {'current':self.current,'active':self.store.active.subgoal_id if self.store.active else None,
            'nodes':{k:{'revision':n.revision,'status':n.status,'outputs':{key:value.get('result_id') for key,value in n.outputs.items()}}
                     for k,n in self.graph.nodes.items()},'results':[e.task_id for e in self.store.entries],
            'active_scope':clone(self.store.active.scope) if self.store.active else None}
        before=state()
        result=super().execute(request,batch_size=batch_size)
        self.action_transitions.append({'call_id':request.request_id,'tool':request.name,'arguments':clone(request.arguments),
            'before':before,'after':state(),'success':result.success,'error':result.error_code})
        self.batch_size=1
        return result

    def _goal(self, node):
        ident = self.node_goals.get((node.task_id, node.revision))
        return self.store.find_subgoal(ident) if ident else None

    def _activate(self, node):
        if self.current != node.task_id and self.pending and all(
                message in self.last_view for message in self.pending):
            # Retire only an already presented native response. Scheduling can
            # occur before the next model decision: dropping an unseen pair
            # here would replace the actual observation with an archive index.
            # observe_exchange replaces this one-pair handoff on the next turn.
            self.pending = []
        if self.store.active and self.store.active is not self._goal(node):
            self.store.settle_active(["Scheduler switched to another independent task"])
        goal = self._goal(node)
        if goal is None:
            numeric = [d for d in node.required_outputs if d.capability in NUMERIC_TOOLS and d.required]
            default = node.required_outputs[0].record
            # Stable graph identity is independent of human title and of this
            # execution episode; an invalidated partial episode must not carry
            # its old artifact pins into the new attempt.
            result = self.store.focus_task(f"plan:{node.task_id}:{node.revision}:episode:{len(self.store.subgoals)+1}", default,
                [{"tool": d.capability,"record":d.record,"scope":self._effective_scope(d)} for d in numeric] or None)
            if result.get("status") != "active":
                return result
            goal = self.store.active
            goal.title = node.goal
            goal.plan_task_id,goal.plan_revision = node.task_id,node.revision
            self.node_goals[node.task_id,node.revision] = goal.subgoal_id
            # A local replan may change one key while retaining another real
            # result. Bind preserved evidence into the same original archive
            # contract; do not force a redundant computation to satisfy it.
            for d in numeric:
                entry = self._entry_for(node.outputs.get(d.key))
                if self._matches(d,entry,node.outputs.get(d.key),node.task_id):
                    goal.reused[f"preserved:{d.key}"] = entry.task_id
                    self.store._bind_requirement(goal,d.capability,d.record,entry.parameters,entry.task_id)
        goal.status = "active"
        self.store.active, self.store.last_owner = goal, goal.subgoal_id
        self.current = node.task_id
        node.status = "RUNNING"
        self.turn_nodes.add(node.task_id)
        return {"status":"selected","task_id":node.task_id,"revision":node.revision}

    def _schedule(self):
        self._invalidate_unusable_bindings()
        if self.current and self.graph.nodes[self.current].status in {"RUNNING","TOOL_SUCCEEDED","DELIVERY_SATISFIED"}:
            return
        self.current = None
        ready = self.graph.ready_nodes()
        ready = [n for n in ready if all(
            self._entry_for(self._ref_output(r)) is not None and self.store._binding_valid(self._entry_for(self._ref_output(r)))
            if (self._ref_output(r) or {}).get("result_id") else self._valid_comparison(self._ref_output(r))
            for r in n.input_refs() if r.task_id!=n.task_id)]
        if ready:
            self._activate(ready[0])

    def _validate_nodes(self, specs, prefix=('nodes',)):
        from .scientific_request_binding import resolve_source_ref
        for ni,node in enumerate(specs):
            for di,d in enumerate(node.required_outputs):
                path=(*prefix,*((ni,) if prefix==('nodes',) else ()), 'required_outputs',di,'interpretation')
                for key in ('source_ref','range_ref'):
                    if key in d.interpretation:
                        try:
                            _,frame=resolve_source_ref(self.store,d.interpretation[key])
                            if frame.records and frame.records!=(d.record,):raise ValueError('Source parent does not uniquely belong to the delivery record')
                        except ValueError as exc:raise ContractError((*path,key),str(exc)) from exc
                for key,ref in d.interpretation.get('channel_reference',{}).items():
                    if key.endswith('_ref'):
                        try:resolve_source_ref(self.store,ref)
                        except ValueError as exc:raise ContractError((*path,'channel_reference',key),str(exc)) from exc
                if d.record not in self.store.records or d.capability not in NUMERIC_TOOLS | {"compare_results"}:
                    raise ValueError("Unknown record or enabled capability")
                if d.capability in NUMERIC_TOOLS:
                    try:
                        self.store._parse_requirements([{"tool":d.capability,"record":d.record,"scope":d.scope}],d.record)
                    except RequirementValidationError as exc:
                        for error in exc.errors:
                            error.update(task_id=node.task_id,output_key=d.key,
                                guidance='Use the listed actual computation scope fields. Measurement dimensions belong in interpretation; report selections belong in the task goal. Do not invent processing or artifact handles.')
                        raise
                elif d.scope or len(d.input_refs)!=2 or any(len(r.fields)!=1 for r in d.input_refs):
                    raise ContractError((*path[:-1],'input_refs'),
                        "A comparison needs two actual input references with exactly one scalar field path each, and empty computation scope")
                for rule in d.acceptance_rule:
                    quote = rule.get("source", "")
                    if not isinstance(quote,str) or not any(quote and quote in r for r in self.requests):
                        raise ValueError("Acceptance conditions need an exact actual user source")
                    # Bounded source check; semantic correctness of the proposed
                    # formal predicate is still independently scored, not proven.
                    if isinstance(rule["value"], (int,float)) and str(rule["value"]) not in quote:
                        raise ValueError("Acceptance value is not in the stated user source")

    def _entry_for(self, output):
        return self.store.find_entry(output.get("result_id")) if output else None

    def _ref_output(self, ref):
        return self.graph.resolve_ref(ref)["output"]

    def _invalidate_unusable_bindings(self):
        for node in self.graph.nodes.values():
            for key,output in list(node.outputs.items()):
                entry = self._entry_for(output)
                valid = self.store._binding_valid(entry) if entry else self._valid_comparison(output)
                if not valid:
                    output.pop('acceptance', None)
                    node.output_status[key] = "STALE"
                    node.status = "STALE"
                    node.unresolved = ["An actual evidence binding is no longer applicable"]

    def _binding(self, delivery, *, graph=None, previous=None, output=None, task_id=None, artifact_id=None):
        graph=graph or self.graph
        references=[]
        for ref in delivery.input_refs:
            resolved=graph.resolve_ref(ref)
            references.append({'reference':ref.to_dict(),'delivery':resolved['delivery'],
                'entry':self._entry_for(resolved['output']) if resolved['output_status']!='STALE' else None})
        executed=self._entry_for(output) if self._execution_scope(delivery,output,task_id) else None
        return resolve_scientific_binding(self.store,delivery.capability,delivery.record,delivery.scope,
            references=references,previous=previous,execution=executed,artifact_id=artifact_id)

    def _effective_scope(self, delivery, *, proposed=False):
        if delivery.capability not in NUMERIC_TOOLS:return clone(delivery.scope)
        return self._binding(delivery).scope

    def _validate_reference_fields(self, delivery, graph, path):
        for ri,ref in enumerate(delivery.input_refs):
            result=graph.resolve_ref(ref)
            entry=self._entry_for(result['output'])
            if not entry or result['output_status']=='STALE':continue
            for fi,field in enumerate(ref.fields):
                try:
                    read_scalar(entry.result,field)
                    meaning=result_field_semantics(entry.capability,field,entry.result,
                        parameters=entry.parameters,analysis_configuration=entry.evidence['analysis_configuration'])
                    if delivery.capability=='compare_results' and meaning['value_type']=='string':
                        raise ValueError('Comparison requires a numeric field')
                except (ValueError,TypeError,KeyError) as exc:
                    raise ContractError((*path,'input_refs',ri,'fields',fi),
                        'Selected scalar field is absent or unsupported in the actual referenced result; use read_dependency on the declared key/version and explicitly repair fields') from exc

    def _validate_sources(self, specs, graph, *, previous=None, prefix=('nodes',)):
        for ni,node in enumerate(specs):
            for di,d in enumerate(node.required_outputs):
                path=(*prefix,*((ni,) if prefix==('nodes',) else ()), 'required_outputs',di)
                self._validate_reference_fields(d,graph,path)
                if d.capability not in NUMERIC_TOOLS or d.capability in METADATA:continue
                old=self._entry_for(previous.outputs.get(d.key)) if previous else None
                binding=self._binding(d,graph=graph,previous=old)
                try:
                    if not binding.ok:raise ValueError('; '.join(binding.conflicts))
                    prior=previous.delivery(d.key) if previous else None
                    retained=(prior and prior.to_dict()==d.to_dict()
                        and node.outputs.get(d.key)==previous.outputs.get(d.key)
                        and self._matches(prior,old,previous.outputs.get(d.key),previous.task_id))
                    if retained:continue # Immutable retained fact, not a new action authorization.
                    if d.interpretation:
                        validate_scientific_sources(self.store,d.capability,d.record,binding,d.interpretation)
                except ValueError as exc:
                    raise ContractError((*prefix,*((ni,) if prefix==('nodes',) else ()),
                        'required_outputs',di,'interpretation'),str(exc)) from exc

    def _execution_scope(self, d, output, task_id):
        """A scoped receipt for one selected, validated artifact action.

        It is a runtime fact on the existing output, never a guessed plan field
        or an archive-wide match for an underspecified delivery.
        """
        receipt=(output or {}).get('execution_scope_binding')
        entry=self._entry_for(output)
        if (not receipt or not entry or not self.store._binding_valid(entry)
                or not task_id or receipt.get('task_id')!=task_id or output.get('originating_task')!=task_id
                or receipt.get('contract_sha256')!=hashlib.sha256(encoded(d.to_dict())).hexdigest()
                or receipt.get('result_id')!=entry.task_id
                or receipt.get('binding')!=entry.evidence['binding']
                or entry.record!=d.record or entry.capability!=d.capability):return {}
        spec=self.store.contexts[d.record].executor.registry.get(d.capability)
        return clone(entry.parameters) if spec.consumes_artifact else {}

    def _matches(self, d, entry, output=None, task_id=None):
        if not entry or not self.store._binding_valid(entry):
            return False
        if (output or {}).get('execution_scope_binding') and (
                output.get('result_id')!=entry.task_id or not self._execution_scope(d,output,task_id)):
            return False
        if entry.record != d.record or entry.capability != d.capability:
            return False
        if d.interpretation and d.interpretation['time_reference'] != entry.evidence['analysis_configuration']['time_reference']:
            return False
        # Declared fields always win; only the exact action's valid receipt can
        # complete omitted artifact-derived fields. Required checks stay intact.
        resolved=self._binding(d,output=output,task_id=task_id)
        if not resolved.ok or resolved.pending:return False
        scope = resolved.scope
        if any(canonical_scope(entry.parameters).get(k) != v for k,v in canonical_scope(scope).items()):
            return False
        required = self.store._required_fields(d.capability)
        if any(k not in scope for k in required):
            return False
        for ref in d.input_refs:
            parent = self.graph.nodes[ref.task_id]
            upstream = self._entry_for(self._ref_output(ref))
            if not upstream or not self.store._binding_valid(upstream):
                return False
            artifact = upstream.evidence["binding"]["artifact_id"]
            if artifact and entry.evidence["binding"]["artifact_id"] != artifact:
                return False
        return True

    def _acceptance_fingerprint(self, delivery, output):
        # A node's title/revision alone is not a change to this delivery. The
        # immutable result identity, binding and complete delivery contract are.
        evidence = {k:v for k,v in output.items() if k not in {'acceptance','revision'}}
        return hashlib.sha256(encoded({'delivery':delivery.to_dict(), 'evidence':evidence})).hexdigest()

    def _acceptance_valid(self, delivery, output, status):
        receipt = (output or {}).get('acceptance', {})
        return (status in {'DELIVERY_SATISFIED','TASK_COMPLETED'} and bool(receipt) and
                receipt.get('fingerprint') == self._acceptance_fingerprint(delivery, output))

    def _mark_delivery(self, node, delivery, evidence):
        old = node.outputs.get(delivery.key)
        receipt = (old or {}).get('acceptance')
        evidence = {k:clone(v) for k,v in evidence.items() if k != 'acceptance'}
        status = 'TOOL_SUCCEEDED' if delivery.acceptance_rule else 'DELIVERY_SATISFIED'
        if (self._acceptance_valid(delivery, old, node.output_status.get(delivery.key)) and
                receipt['fingerprint'] == self._acceptance_fingerprint(delivery, evidence)):
            evidence['acceptance'] = clone(receipt)
            status = 'DELIVERY_SATISFIED'
        self.graph.mark_output(node.task_id, delivery.key, evidence, status=status)

    def _record_acceptance(self, node, row, owner):
        d, output = node.delivery(row['key']), node.outputs[row['key']]
        repeated = self._acceptance_valid(d, output, node.output_status.get(d.key))
        if not repeated:
            output['acceptance'] = {'owner':owner, 'accepted_revision':node.revision,
                'fingerprint':self._acceptance_fingerprint(d, output),
                'scientifically_accepted':row['accepted'], 'predicates':clone(row['predicates'])}
            self.plan_events.append({'event':'delivery_accepted','task_id':node.task_id,'key':d.key,
                'revision':node.revision,'result_id':output.get('result_id',output.get('comparison_id')),
                'acceptance':clone(output['acceptance'])})
        node.output_status[d.key] = 'DELIVERY_SATISFIED'
        return {'status':'delivery_accepted','task_id':node.task_id,'output_key':d.key,
                'revision':node.revision,'result_id':output.get('result_id',output.get('comparison_id')),
                'idempotent':repeated,'acceptance':clone(output['acceptance']),'check':clone(row)}

    def _accept_delivery(self, node, key, revision, result_id):
        d, output = node.delivery(key), node.outputs.get(key)
        if (not d or not output or revision != node.revision or not result_id or
                result_id != output.get('result_id',output.get('comparison_id'))):
            return self.store._error('INVALID_DELIVERY_ACCEPTANCE','Use an existing delivery, current revision and its actual result identity')
        row = next(r for r in self.delivery_check(node)['outputs'] if r['key']==key)
        if (not row['output_valid'] or node.output_status.get(key)=='STALE' or
                any(not self._input_ready(r) for r in d.input_refs)):
            return self.store._error('INVALID_DELIVERY_ACCEPTANCE','The delivery or its scientific dependency binding is not valid')
        if self.automatic_acceptance and not row['accepted']:
            return {**self.store._error('SCIENTIFIC_ACCEPTANCE_FAILED','Real results do not meet the declared conditions'),'check':row}
        # Model judgment of additional predicates remains a method variable;
        # neither this receipt nor its owner changes the objective diagnostic.
        return self._record_acceptance(node,row,'program' if self.automatic_acceptance else 'model')

    def _sync_outputs(self, node, result=None, owned_delivery=None):
        # Match only actual results used by this node, not a future answer key or
        # opportunistic archive scan. Normal history reuse enters execute_action.
        goal = self._goal(node)
        identifiers = list(dict.fromkeys((goal.result_ids + list(goal.reused.values())) if goal else []))
        for d in node.required_outputs:
            if d.capability == "compare_results":
                if result and result.get("status") == "compared":
                    refs = [(self._ref_output(r) or {}).get("result_id") for r in d.input_refs]
                    if (refs == [r["result_id"] for r in result["operands"]] and
                        [r.fields[0] for r in d.input_refs] == [r["field"] for r in result["operands"]]):
                        self._mark_delivery(node,d,{"comparison_id":result["comparison_id"],"result":clone(result),"revision":node.revision})
                continue
            evidence=node.outputs.get(d.key)
            if owned_delivery is d and result and result.get('status') in {'observed','reused'}:
                # Correlate the exact Store receipt, not the last numeric entry
                # or whichever historical artifact happens to match the title.
                actual=[self.store.find_entry(i) for i in identifiers]
                actual=[e for e in actual if e and (e.task_id==result.get('task_id') if result['status']=='reused'
                    else e.task_id==result.get('observation',{}).get('result_id') and e.tool_trace
                    and e.tool_trace[-1]=={k:v for k,v in result.get('observation',{}).items() if k!='result_id'})]
                if len(actual)==1 and self.store.contexts[d.record].executor.registry.get(d.capability).consumes_artifact:
                    entry=actual[0]
                    evidence={'result_id':entry.task_id,'originating_task':node.task_id,'execution_scope_binding':{
                        'task_id':node.task_id,
                        'contract_sha256':hashlib.sha256(encoded(d.to_dict())).hexdigest(),
                        'result_id':entry.task_id,'binding':clone(entry.evidence['binding']),
                        'basis':'validated_selected_artifact_execution'}}
            found = [self.store.find_entry(i) for i in identifiers if self._matches(d,self.store.find_entry(i),evidence,node.task_id)]
            if found:
                entry = found[-1]
                self._mark_delivery(node,d,{
                    **({'execution_scope_binding':clone(evidence['execution_scope_binding'])}
                       if self._execution_scope(d,evidence,node.task_id) else {}),
                    "result_id":entry.task_id,"record":entry.record,"actual_scope":clone(entry.parameters),
                    **({'created_user_turn':entry.evidence['created_user_turn']} if 'created_user_turn' in entry.evidence else {}),
                    "originating_task":node.task_id,"actual_parameters":clone(entry.parameters),"source":entry.evidence["source"],
                    "processing_version":clone(entry.evidence["binding"]),"revision_of":entry.revision_of,
                    "input_artifact":entry.evidence["binding"]["artifact_id"] if d.capability!="create_epochs" else None,
                    "output_artifact":entry.evidence["binding"]["artifact_id"] if d.capability=="create_epochs" else None,
                    "unit_or_kind":entry.evidence["unit_or_kind"],
                    "result_pointer":entry.task_id,"AO_pointer":entry.evidence["subgoal_id"],"revision":node.revision})
        if self.automatic_acceptance:
            for row in self.delivery_check(node)["outputs"]:
                if row["accepted"]:
                    self._record_acceptance(node,row,'program')

    def delivery_check(self, node):
        rows = []
        for d in node.required_outputs:
            output = node.outputs.get(d.key)
            entry = self._entry_for(output)
            valid = self._matches(d,entry,output,node.task_id) if d.capability != "compare_results" else self._valid_comparison(output)
            predicates = []
            for rule in d.acceptance_rule:
                try:
                    value = read_scalar(entry.result,rule["path"])
                    meaning = result_field_semantics(entry.capability,rule["path"],entry.result,
                        parameters=entry.parameters,analysis_configuration=entry.evidence["analysis_configuration"])
                    if meaning["value_type"] != "string" and type(rule["value"]) in {int,float}:
                        value = float(value)
                    passed = {"eq":lambda: value == rule["value"],"gte":lambda:value >= rule["value"],
                              "lte":lambda:value <= rule["value"]}[rule["op"]]()
                    predicates.append({"rule":clone(rule),"value":value,"meaning":meaning,"passed":bool(passed)})
                except (AttributeError,KeyError,ValueError,TypeError):
                    predicates.append({"rule":clone(rule),"passed":False,"reason":"No applicable actual field"})
            rows.append({"key":d.key,"required":d.required,"output_valid":valid,"predicates":predicates,
                         "acceptance":clone((output or {}).get('acceptance')),
                         "output_status":node.output_status.get(d.key),
                         "accepted":valid and all(p["passed"] for p in predicates)})
        required = [r for r in rows if r["required"]]
        return {"task_id":node.task_id,"revision":node.revision,"outputs":rows,
                "all_outputs_present":bool(required) and all(r["output_valid"] for r in required),
                "scientifically_accepted":bool(required) and all(r["accepted"] for r in required),
                "intent_completeness":"model_plan_is_not_independent_user_intent_gold"}

    def _complete(self, node, *, proposed=False):
        if proposed and self.current != node.task_id:
            return self.store._error("SELECT_CURRENT_TASK","Select this ready task before changing its completion state")
        check = self.delivery_check(node)
        if not check["all_outputs_present"]:
            return {**self.store._error("MISSING_DELIVERY","All required scoped output instances must exist"),"check":check}
        if self.automatic_acceptance and not check["scientifically_accepted"]:
            return {**self.store._error("SCIENTIFIC_ACCEPTANCE_FAILED","Real results do not meet the declared scientific conditions"),"check":check}
        if not proposed and not self.automatic_acceptance and any(d.acceptance_rule and
                not self._acceptance_valid(d,node.outputs.get(d.key),node.output_status.get(d.key))
                for d in node.required_outputs if d.required):
            node.status = "TOOL_SUCCEEDED"
            return {"status":"acceptance_review_required","check":check}
        goal = self._goal(node)
        if goal and goal.requirements and not self.store.completion_check(goal)["valid"]:
            return self.store._error("ARCHIVE_CONTRACT_MISMATCH","Plan outputs and task archive disagree; preserve partial results")
        node.status = "TASK_COMPLETED"
        for row in check["outputs"]:
            if row["output_valid"] and (row["accepted"] or proposed and not self.automatic_acceptance):
                self._record_acceptance(node,row,'program' if self.automatic_acceptance else
                    'model' if proposed else 'common_output_check')
        if goal:
            # Numerical archive remains the original store; comparisons point to
            # both immutable operands and are additionally retained by controller.
            if not goal.requirements:
                goal.status,goal.unresolved = "completed",[]
                self.store.active = None
                self.store.events.append({"event":"archived","subgoal_id":goal.subgoal_id,"turn":self.store.turn})
            else:
                self.store.settle_active()
        self.plan_events.append({"event":"task_completed","task_id":node.task_id,"revision":node.revision,
            "acceptance_owner":"program" if self.automatic_acceptance else "model" if proposed else "common_output_check",
            "scientifically_accepted":check["scientifically_accepted"]})
        self.current = None
        return {"status":"completed","task_id":node.task_id,"check":check}

    def _read(self, task_id, key, level, fields=None, revision=None, *, automatic=False):
        node = self.graph.nodes[task_id]
        resolved = self.graph.resolve_ref({"task_id":task_id,"key":key,**({"revision":revision} if revision else {})})
        output = resolved["output"]
        if level == 'contract':
            entry=self._entry_for(output) if output else None
            valid=bool(entry and self.store._binding_valid(entry) and resolved['output_status']!='STALE')
            fields=[]
            if valid:
                def visit(value,path):
                    if isinstance(value,dict):
                        for k,v in value.items():visit(v,path+[k])
                    elif isinstance(value,list):
                        for k,v in enumerate(value):visit(v,path+[k])
                    else:
                        try:meaning=result_field_semantics(entry.capability,path,entry.result,
                            parameters=entry.parameters,analysis_configuration=entry.evidence.get('analysis_configuration',{}))
                        except ValueError:return
                        fields.append({'path':path,**meaning})
                visit(entry.result,[])
            return {'status':'contract','task_id':task_id,'key':key,'revision':resolved['revision'],
                'actual_delivery':bool(output),'valid_binding':valid,'numeric_evidence':False,
                'declared_contract':resolved['delivery'],'fields':fields,
                'availability':'delivered' if valid else 'stale' if output else 'undelivered',
                'available_history':self._history_index(node,key),
                'selection_rule':'revision omitted means current, never falls back to history; select an explicit available historical revision to read its contract or values',
                'field_basis':'actual_verified_result' if valid else 'unavailable_not_inferred_from_plan'}
        if not output:
            return {**self.store._error("DEPENDENCY_UNDELIVERED","No actual output at that key/version; current execution and historical reading are distinct"),
                    'requested_revision':resolved['revision'],'available_history':self._history_index(node,key)}
        if level == "summary":
            return {"status":"read","task_id":task_id,"key":key,"revision":resolved["revision"],"level":level,"goal":resolved["goal"],
                    "task_status":resolved["status"],"locator":self._locator(output),"numeric_evidence":False}
        entry = self._entry_for(output)
        if entry is None:
            if output.get("comparison_id") and level == "result":
                if not self._valid_comparison(output):
                    return self.store._error("STALE_RESULT","Comparison operands are no longer applicable")
                if output["result"] not in self.visible_comparisons:
                    self.visible_comparisons.append(clone(output["result"]))
                return {"status":"read","comparison":clone(output["result"])}
            return self.store._error("INVALID_RESULT","Select an actual numerical result")
        if not self.store._binding_valid(entry) or resolved["output_status"]=="STALE":
            return self.store._error("STALE_RESULT","Current dependency revision has no valid delivery")
        if level == "process":
            result = ScientificMemoryController._dispatch(self,ToolRequest("restore_task",{
                "task_id":entry.task_id,"reason":"Inspect the actual dependency process before continuing"}))
        else:
            result = ManagedMemoryController._dispatch(self,ToolRequest("read_result",{
                "result_id":entry.task_id, **({"fields":fields} if fields else {})}))
        self.evidence_log.append({"event":"read","task_id":task_id,"key":key,"level":level,
            "result_id":entry.task_id,"automatic":automatic,"success":result.get("status") in {"read","restored"}})
        return result

    def _valid_comparison(self, output):
        if not output or not output.get("comparison_id"):
            return False
        for row in output.get("result",{}).get("operands",[]):
            entry = self.store.find_entry(row["result_id"])
            if not entry or not self.store._binding_valid(entry) or entry.evidence["binding"] != row["binding"]:
                return False
        return len(output.get("result",{}).get("operands",[])) == 2

    @staticmethod
    def _locator(output):
        return {k:clone(v) for k,v in output.items() if k != "result"}

    def _history_index(self, node, key=None):
        """Exact snapshot locators only; no automatic historical selection."""
        rows=[]
        for revision in node.revision_history:
            snapshot=revision['snapshot']
            for name,output in snapshot['outputs'].items():
                if key is not None and name!=key:continue
                entry=self._entry_for(output)
                rows.append({'task_id':node.task_id,'key':name,'revision':snapshot['revision'],
                    'result_id':output.get('result_id',output.get('comparison_id')),
                    'record':entry.record if entry else None,'scope':clone(entry.parameters) if entry else {},
                    'valid_binding':self.store._binding_valid(entry) if entry else self._valid_comparison(output)})
        return rows

    def _inputs(self, node):
        rows = []
        refs = [r for d in node.required_outputs for r in d.input_refs]
        for ref in refs:
            parent = self.graph.nodes[ref.task_id]
            output = self._ref_output(ref)
            entry = self._entry_for(output)
            row = {"task_id":ref.task_id,"key":ref.key,"revision":getattr(ref,"revision",None),"expected_level":ref.level,"fields_requested":clone(ref.fields)}
            if not output or entry and not self.store._binding_valid(entry):
                row.update(level="missing",status="undelivered")
            elif self.dependency_selection:
                if ref.level == "process":
                    goal = self.store.find_subgoal(entry.evidence["subgoal_id"]) if entry else None
                    restored = self.store.restore_subgoal(goal.subgoal_id) if goal else {}
                    row.update(level="process",process=clone(restored.get("action_observations",[])),
                               process_source="original_task_archive",restoration_status=restored.get("status","unavailable"))
                elif ref.level == "summary":
                    row.update(level="summary",goal=parent.goal,locator=self._locator(output))
                elif entry and self.store._binding_valid(entry):
                    try:
                        wanted = [{"path":p,"value":read_scalar(entry.result,p)} for p in ref.fields] if ref.fields else None
                        row.update(level="result",evidence=self._evidence(entry,fields=wanted))
                    except (ValueError,KeyError,TypeError):
                        row.update(level="missing_field",locator=self._locator(output),error="Choose actual fields via read_dependency")
                else:
                    row.update(level="result",comparison=clone(output.get("result")))
            elif self.arm == "B":
                row.update(level="summary",goal=parent.goal,locator=self._locator(output))
                # Reasonable generic summary retains small exact facts; never
                # remove all numbers just to force baseline reads.
                if entry:
                    row["evidence"] = self._evidence(entry,limit=64)
            else:
                row.update(level="result",evidence=self._evidence(entry) if entry else clone(output))
            rows.append(row)
        return rows

    def _view(self):
        self._schedule()
        node = self.graph.nodes.get(self.current)
        # Reuse original view's record metadata, exact evidence handoff and
        # current protocol-valid AO. No second numerical context is introduced.
        messages = super()._view()
        payload = json.loads(messages[1]["content"])
        payload.pop("task_summaries",None)
        payload["plan"] = [{'task_id':n.task_id,'goal':n.goal,'status':n.status,'revision':n.revision,
            'declared_outputs':[d.to_dict() for d in n.required_outputs],
            'revision_targets':[{'task_id':n.task_id,'output_key':d.key,'revision':n.revision} for d in n.required_outputs]}
                           for n in self.graph.nodes.values()]
        payload['dependency_relations']={n.task_id:self.graph.dependency_relations(n) for n in self.graph.nodes.values() if n.input_refs() or n.control_prerequisites()}
        registry=next(iter(self.store.contexts.values())).executor.registry
        payload['artifact_input_contracts']=[]
        for n in self.graph.nodes.values():
            for d in n.required_outputs:
                spec=registry.get(d.capability)
                if not spec or not spec.consumes_artifact:continue
                bindings=[]
                for ref in d.input_refs:
                    resolved=self.graph.resolve_ref(ref)
                    producer=registry.get(resolved['delivery']['capability'])
                    if producer and producer.produces_artifact==spec.consumes_artifact:
                        bindings.append({'reference':ref.to_dict(),'has_result':bool(resolved.get('output'))})
                payload['artifact_input_contracts'].append({'task_id':n.task_id,'key':d.key,
                    'requires_artifact_type':spec.consumes_artifact,'declared_producers':bindings,
                    'registered_producer_capabilities':[p.name for p in registry.list_specs() if p.produces_artifact==spec.consumes_artifact],
                    'status':'producer_selected' if bindings else 'producer_not_selected',
                    'note':'Registry facts only; selecting a producer does not establish result existence, source, scope, or acceptance.'})
        # Original request parents expose actual source boundaries, not a gold
        # plan. A field reference cannot crop away record/object ownership.
        from .scientific_request_binding import source_catalog
        known_channels={c for r in self.store.records.values() for c in r.channel_names}
        known_labels={e.label for r in self.store.records.values() if r.events for e in r.events.events}
        payload["scientific_source_frames"] = [
            {**f,
             "literal_metadata":{"channels":sorted(c for c in known_channels if self.store._contains(f['span'],c)),
                                 "event_labels":sorted(l for l in known_labels if self.store._contains(f['span'],l))},
             "role_status":"not_interpreted_by_literal_locator"}
            for f in source_catalog(self.store)]
        payload["phase"] = "local_execution" if node else "plan_or_final_delivery"
        relevant=[n for n in self.graph.nodes.values() if n.task_id in self.turn_nodes]
        ready=bool(relevant) and all(self.delivery_check(n)['all_outputs_present'] for n in relevant)
        review=('declared_outputs_present' if ready else
                'observations_without_increment' if self.redundant_observations>=2 else None)
        if review!=self.delivery_review:
            self.plan_events.append({'event':'delivery_phase','turn':self.store.turn,
                'mode':'delivery_review' if review else 'execution','reason':review})
        self.delivery_review=review
        if review:
            payload['phase']='delivery_review'
            payload['delivery_phase']={'mode':'delivery_review','reason':review,'can_resume_execution':True,
                'instruction':'Review the original request against actual visible evidence. Declared outputs do not prove intent completeness. Explicitly add/revise omitted work or read genuinely needed evidence, otherwise deliver with finish_task; partial/clarification remain available. All scientific checks and resource limits still apply.'}
        payload['control_progress']={'latest':clone(self.progress_events[-1:]),
            'bounded_diagnostic_credits_used':self.repair_credits}
        payload["current_plan_task"] = node.task_id if node else None
        payload["dependency_evidence"] = self._inputs(node) if node else []
        payload["task_summaries"] = [{"task_id":n.task_id,"goal":n.goal,"revision":n.revision,
            "historical_outputs":self._history_index(n),
            "status":n.status,"outputs":{k:self._locator(v) for k,v in n.outputs.items()},
            "readable_keys":[k for k,v in n.outputs.items() if n.output_status.get(k)!='STALE' and
                             (self.store._binding_valid(self._entry_for(v)) if self._entry_for(v) else self._valid_comparison(v))],
            "revision_keys":[d.key for d in n.required_outputs],
            "unresolved":clone(n.unresolved)} for n in self.graph.nodes.values()]
        messages[0]["content"] = SYSTEM + ("\n明确科学条件由程序自动核验。" if self.automatic_acceptance else
            "\n显式科学条件由你据真实结果评估；可用complete_node接受单个真实交付后继续消费者，全部必需交付齐备才能完成整任务。check_deliveries为可选诊断；条件不足可明确partial。")
        messages[1]["content"] = encoded(payload).decode("utf8")
        return messages

    def build_messages(self, **kwargs):
        if getattr(self,'final_only',False) and not self.delivery_checkpoint:
            messages,_=self.build_final_messages(self.finalization_reason)
            if len(json.dumps(messages,ensure_ascii=False).encode('utf8'))>self.max_context_bytes:
                if kwargs.get('record_decision',True):self.stop_reason='context_capacity'
                return []
            if kwargs.get('record_decision',True):
                self._remember_presented(messages)
                self.last_view=clone(messages)
                self.visible_evidence_ids=self._visible_results(messages)
                self.decisions.append({'turn':self.store.turn,'messages':clone(messages),
                    'context_bytes':len(encoded(messages)),'phase':'hard_final_delivery'})
        else:
            messages = super().build_messages(**kwargs)
        if messages and kwargs.get("record_decision",True):
            payload = json.loads(messages[1]["content"])
            self.evidence_log.append({"event":"presented","decision":len(self.decisions),
                "current_task":self.current,"dependencies":clone(payload.get("dependency_evidence",[]))})
            if self.current:
                self.evidence_log.append({"event":"expected","decision":len(self.decisions),
                    "current_task":self.current,"references":[r.to_dict() for r in self.graph.nodes[self.current].input_refs()]})
        return messages

    def build_final_messages(self, reason="resource_reserve"):
        messages,tools = super().build_final_messages(reason)
        messages[0]['content']='你是EEG分析交付助手。当前资源仅允许finish_task，不能继续工具计算或读取。依据本视图实际可用证据回答原请求；无法完整交付时明确partial及未完成事项，资源限制不是科学缺参。保留对象、单位、范围、版本与真实限制，不编造或推断未读数值。'
        payload = json.loads(messages[1]["content"])
        payload['phase']='hard_final_delivery'
        payload['delivery_phase']={'mode':'hard_final_delivery','reason':reason,'can_resume_execution':False,
            'allowed_operations':['finish_task'],'declared_completion_is_request_completion':False}
        payload.pop('task_status',None)  # No unrequested archive facts in final view.
        payload["plan_status"] = [{"task_id":n.task_id,"revision":n.revision,"status":n.status,
                                   "unresolved":clone(n.unresolved)} for n in self.graph.nodes.values()]
        messages[1]["content"] = encoded(payload).decode("utf8")
        return messages,tools

    def clarification_verification(self,delivery,fields):
        """Bounded factual check; unresolvable semantics require external review."""
        from .scientific_request_binding import window_availability
        return window_availability(self.store,delivery.capability,self._effective_scope(delivery),delivery.record,fields)['status']

    def _validate_revision_sources(self,old,spec,graph=None):
        """Read-only source preflight before graph/version/active-state mutation."""
        self._validate_sources([spec],graph or self.graph,previous=old,prefix=('updates',))

    def _revision_updates(self, old, args):
        """Normalize a single explicit patch into the original atomic contract."""
        if args.get('revision',old.revision)!=old.revision:
            raise ContractError(('revision',),'Select the existing task current revision')
        if 'changes' not in args:
            if 'output_key' in args:raise ContractError(('output_key',),'Use changes for a delivery patch, or updates for a whole-task revision')
            return clone(args['updates'])
        d=old.delivery(args['output_key'])
        if d is None:raise ContractError(('output_key',),'Unknown existing delivery key; no target is inferred')
        changes=args['changes']
        if not changes:raise ContractError(('changes',),'Specify an actual change')
        if changes.get('scope') and any(d.scope.get(k)!=v for k,v in changes['scope'].items()):
            if not set(changes.get('interpretation',{})) & {'source_ref','source_span','range_ref','range_span'}:
                raise ContractError(('changes','interpretation'),'Changed scientific scope requires an explicit lawful source or range locator')
        rows=[item.to_dict() for item in old.required_outputs]
        row=next(r for r in rows if r['key']==d.key)
        for key,value in changes.items():
            if key=='interpretation':
                # Each pair expresses one locator in two representations.
                # An explicit replacement chooses the supplied representation;
                # it must not retain an incompatible old alternative.
                for pair in (('source_ref','source_span'),('range_ref','range_span')):
                    supplied=set(pair)&set(value)
                    if len(supplied)==1:
                        for other in set(pair)-supplied:row.get(key,{}).pop(other,None)
            row[key]={**row.get(key,{}),**clone(value)} if key in {'scope','interpretation'} else clone(value)
        return {'required_outputs':rows}

    def _dispatch(self, request):
        name,args=request.name,clone(dict(request.arguments))
        if getattr(self,'final_only',False) and name!='finish_task':
            result=self.store._error('FINAL_DELIVERY_ONLY','Only the reserved final answer is available')
            result['recovery']={'tool':'finish_task','instruction':'Report actual visible results and unresolved work; execution cannot resume at this resource boundary.'}
            return result
        compact=(name=='plan_tasks' and 'deliveries' in args or
                 name=='revise_plan' and not ({'updates','changes'} & set(args)))
        if not compact:
            result=self._dispatch_canonical(request)
            if name in {'plan_tasks','revise_plan'} and result.get('status')=='rejected':
                public=next(c['function']['parameters'] for c in self.control_definitions() if c['function']['name']==name)
                diagnostics=contract_diagnostics(args,public)
                if diagnostics['issues']:
                    result['compatibility_diagnostic']={k:clone(result[k]) for k in ('code','message','field_path') if k in result}
                    first=diagnostics['issues'][0]
                    result.update(message=first['message'],field_path=first['path'],structure_diagnostics=diagnostics)
            return self._planning_feedback(name,args,result) if name in {'plan_tasks','revise_plan'} else result
        spec=next(c['function'] for c in self.control_definitions() if c['function']['name']==name)
        try:
            diagnostics=contract_diagnostics(args,spec['parameters'])
            if diagnostics['issues']:
                first=diagnostics['issues'][0]
                return self._planning_feedback(name,args,{**self.store._error('INVALID_PLAN_STRUCTURE',first['message']),
                    'field_path':first['path'],'structure_diagnostics':diagnostics})
            validate_contract(args,spec['parameters'])
            normalized=self._normalize_write(name,args)
        except (ValueError,TypeError,KeyError) as exc:
            return self._planning_feedback(name,args,{**self.store._error('INVALID_PLAN_STRUCTURE',str(exc)),
                    'field_path':getattr(exc,'path',[])})
        result=self._dispatch_canonical(ToolRequest(name,normalized,request.request_id))
        if 'field_path' in result:
            path=result['field_path'];result['normalized_field_path']=clone(path)
            if name=='revise_plan':
                if path[:2]==['updates','required_outputs']:
                    index=path[2]
                    added=args.get('add_deliveries',[])
                    rows=normalized.get('updates',{}).get('required_outputs',[])
                    start=len(rows)-len(added)
                    path=(['add_deliveries',index-start,*path[3:]] if added and index>=start else path[3:])
                    if (path[:1]==['add_deliveries'] and args['add_deliveries'][path[1]].get('capability')=='compare_results'
                            and path[2:3]==['input_refs'] and len(path)>3):
                        path=path[:2]+[('left','right')[path[3]]]+path[4:]
                        if 'fields' in path:
                            i=path.index('fields');path=path[:i]+['field']+path[i+2:]
                elif path[:1]==['changes']:path=path[1:]
                old=self.graph.nodes.get(args.get('task_id'))
                selected=old.delivery(args.get('output_key')) if old else None
                if selected and selected.capability=='compare_results' and path[:1]==['input_refs'] and len(path)>1:
                    path=[('left','right')[path[1]],*path[2:]]
                    if 'fields' in path:
                        i=path.index('fields');path=path[:i]+['field']+path[i+2:]
            elif path[:1]==['nodes'] and len(path)>3 and path[2]=='required_outputs':
                task=normalized['nodes'][path[1]];key=task['required_outputs'][path[3]]['key']
                index=next(i for i,d in enumerate(args['deliveries']) if (d['task_id'],d['key'])==(task['task_id'],key))
                path=['deliveries',index,*path[4:]]
                if 'input_refs' in path and args['deliveries'][index]['capability']=='compare_results':
                    i=path.index('input_refs')
                    if len(path)>i+1:path=path[:i]+[('left','right')[path[i+1]]]+path[i+2:]
                    if 'fields' in path:
                        i=path.index('fields');path=path[:i]+['field']+path[i+2:]
            result['field_path']=path
        return self._planning_feedback(name,args,result)

    def _planning_feedback(self,name,args,result):
        """Explain the attempted transaction, never infer the desired one.

        Structure and scientific errors use the same operation boundary. A
        task container is not implicit evidence for a newly proposed key.
        """
        if result.get('status')!='rejected':return result
        if getattr(self,'final_only',False) or result.get('code')=='FINAL_DELIVERY_ONLY':
            result['recovery']={'tool':'finish_task','instruction':'Only the reserved final delivery remains; report actual results and unresolved work.'}
            return result
        effects=[]
        rows=args.get('deliveries',[]) if name=='plan_tasks' else args.get('add_deliveries',[])
        if isinstance(rows,list):
            for row in rows:
                if not isinstance(row,dict):continue
                ident=row.get('task_id') if name=='plan_tasks' else args.get('task_id')
                node=self.graph.nodes.get(ident) if isinstance(ident,str) else None
                effects.append({'operation':'new_task_delivery' if name=='plan_tasks' else 'append_new_delivery',
                    'task_id':ident,'key':row.get('key'),'task_already_exists':node is not None,
                    'key_already_exists':bool(node and isinstance(row.get('key'),str) and node.delivery(row['key'])),
                    'implicit_previous_result':False,
                    'explicit_input_refs':clone(row.get('input_refs',[]))})
        if name=='revise_plan' and 'output_key' in args:
            node=self.graph.nodes.get(args.get('task_id')) if isinstance(args.get('task_id'),str) else None
            key=args.get('output_key')
            output=node.outputs.get(key) if node and isinstance(key,str) else None
            entry=self._entry_for(output)
            effects.append({'operation':'patch_existing_delivery','task_id':args.get('task_id'),'key':key,
                'current_revision':node.revision if node else None,
                'implicit_previous_result':bool(entry and self.store._binding_valid(entry))})
        public=next(c['function']['parameters'] for c in self.control_definitions() if c['function']['name']==name)
        surfaces=[]
        collection='deliveries' if name=='plan_tasks' else 'add_deliveries'
        for i,row in enumerate((args.get(collection,[]) if isinstance(args.get(collection,[]),list) else [])[:24]):
            schema=selected_contract(public['properties'][collection]['items'],row)
            surfaces.append({'path':[collection,i],
                'allowed_fields':list(schema.get('properties',{})) if schema else [],
                'source_fields':[k for k in ('interpretation','input_refs','left','right') if schema and k in schema.get('properties',{})],
                'branch':'explicit_discriminator' if schema else 'select_advertised_capability'})
        if name=='revise_plan':
            node=self.graph.nodes.get(args.get('task_id')) if isinstance(args.get('task_id'),str) else None
            d=node.delivery(args['output_key']) if node and isinstance(args.get('output_key'),str) else None
            fields=['left','right'] if d and d.capability=='compare_results' else ['interpretation','input_refs'] if d else []
            surfaces.append({'path':[],'allowed_fields':list(public['properties']),
                'source_fields':[k for k in fields if k in public['properties']], 'branch':'explicit_existing_target' if d else 'target_not_selected'})
        shared=set(surfaces[0]['source_fields']) if surfaces else set()
        for surface in surfaces[1:]:shared &= set(surface['source_fields'])
        result['recovery']={**result.get('recovery',{}),'tool':result.get('recovery',{}).get('tool',name),
            'proposed_effects':effects,'source_fields':[k for k in ('interpretation','input_refs','left','right') if k in shared],
            'public_contracts':surfaces,
            'operation_contract':{
                'new_task':'plan_tasks.deliveries: independent new identities only',
                'patch_existing':'revise_plan: task_id + output_key + revision + reason, then changed fields. Reuses that selected delivery previous binding; old result remains in revision history.',
                'append_new':'revise_plan: task_id + revision + reason + add_deliveries. New keys do not inherit sibling results merely by sharing a task. Choose evidence fields from the explicitly selected public branch; may also patch one output_key atomically.'},
            'instruction':'Select the intended operation and evidence explicitly; no target or scientific condition is inferred. read_dependency discovers actual result contracts, including undelivered/stale status.'}
        return result

    def _dispatch_canonical(self, request):
        name,args = request.name,clone(dict(request.arguments))
        owner={k:args.pop(k) for k in ('task_id','output_key','revision') if k in args} if name in NUMERIC_TOOLS | {'compare_results'} else {}
        if owner:
            try:validate_contract(owner,{'type':'object','properties':OWNER_PROPERTIES,'required':['task_id'],'additionalProperties':False})
            except ContractError as exc:return {**self.store._error('INVALID_ACTION_OWNER',str(exc)),'field_path':exc.path}
        if name=='plan_tasks' and isinstance(args.get('nodes'),list):
            existing=[n.get('task_id') for n in args['nodes'] if isinstance(n,dict) and n.get('task_id') in self.graph.nodes]
            if existing:
                return {**self.store._error('INVALID_PLAN_OPERATION','Existing identities require explicit revise_plan; no proposal was applied'),
                    'recovery':{'tool':'revise_plan','targets':[{'task_id':i,'revision':self.graph.nodes[i].revision,
                        'output_keys':[d.key for d in self.graph.nodes[i].required_outputs]} for i in existing]}}
        spec = next((c["function"] for c in self._compatibility_controls() if c["function"]["name"] == name),None)
        if spec:
            if name in {'plan_tasks','revise_plan','finish_task'}:
                try:validate_contract(args,spec['parameters'])
                except ContractError as exc:
                    return {**self.store._error('INVALID_PLAN_STRUCTURE',str(exc)), 'field_path':exc.path,
                        'recovery':{'tool':name,'instruction':'Correct this field using the advertised contract; no state was changed'}}
            try:_validate_schema(args,spec["parameters"])
            except (ValueError, TypeError) as exc:
                if name not in {"plan_tasks", "revise_plan"}:raise
                return self.store._error("INVALID_PLAN_STRUCTURE", str(exc)[:600])
        if self.final_only and name != "finish_task":
            return self.store._error("FINAL_DELIVERY_ONLY","Only the reserved final answer is available")
        if name == "plan_tasks":
            try:specs = [TaskSpec.from_dict(n) for n in args["nodes"]]
            except (ValueError, TypeError, KeyError) as exc:
                # Only pure proposal parsing errors are exposed, never arbitrary
                # execution exceptions, file paths or service response bodies.
                return self.store._error("INVALID_PLAN_STRUCTURE", str(exc)[:600])
            try:
                prospective=deepcopy(self.graph)
                prospective.submit(specs)
            except ValueError as exc:
                return {**self.store._error('INVALID_PLAN_GRAPH',str(exc)),'field_path':['nodes'],
                        'recovery':{'tool':'revise_plan' if any(n.task_id in self.graph.nodes for n in specs) else 'plan_tasks',
                                    'instruction':'Existing identities require explicit revision; new identities must form a valid graph'}}
            try:
                self._validate_nodes(specs)
                self._validate_sources(specs,prospective)
            except ContractError as exc:
                return {**self.store._error('INVALID_PLAN_STRUCTURE' if exc.path[-1]=='input_refs' else 'INVALID_PLAN_SOURCE',str(exc)),
                        'field_path':exc.path,'recovery':{'tool':'plan_tasks'}}
            except RequirementValidationError as exc:
                return {**self.store._error('INVALID_PLAN_REQUIREMENT','Repair the listed delivery scope using the existing tool contract'),
                        'requirement_errors':clone(exc.errors)}
            try:self.graph.submit(specs)
            except ValueError as exc:
                return {**self.store._error('INVALID_PLAN_GRAPH',str(exc)),'field_path':['nodes'],
                        'recovery':{'tool':'plan_tasks','instruction':'Correct graph identities or dependencies without changing scientific obligations'}}
            self.turn_nodes.update(n.task_id for n in specs)
            return {"status":"planned","task_ids":[n.task_id for n in specs]}
        if name == "revise_plan":
            old = self.graph.nodes.get(args['task_id'])
            if old is None:
                return {**self.store._error('INVALID_PLAN_REVISION','Unknown existing task; no target is inferred'),'field_path':['task_id']}
            try:updates=self._revision_updates(old,args)
            except ContractError as exc:
                return {**self.store._error('INVALID_PLAN_REVISION',str(exc)),'field_path':exc.path}
            allowed = old.to_dict(runtime=False)
            allowed.update(updates)
            try:revised_spec = TaskSpec.from_dict(allowed)
            except (ValueError, TypeError, KeyError) as exc:
                return self.store._error("INVALID_PLAN_STRUCTURE", str(exc)[:600])
            try:
                prospective=deepcopy(self.graph)
                prospective.revise(args['task_id'],updates,args['reason'])
            except (ValueError,TypeError) as exc:
                return self.store._error('INVALID_PLAN_REVISION',str(exc))
            try:
                self._validate_nodes([revised_spec],prefix=('updates',))
                self._validate_revision_sources(old,prospective.nodes[old.task_id],prospective)
            except ContractError as exc:
                return {**self.store._error('INVALID_PLAN_STRUCTURE' if exc.path[-1]=='input_refs' else 'INVALID_PLAN_SOURCE',str(exc)),
                        'field_path':exc.path,'recovery':{'tool':'revise_plan'}}
            except RequirementValidationError as exc:
                return {**self.store._error('INVALID_PLAN_REQUIREMENT','Repair the listed delivery scope using the existing tool contract'),
                        'requirement_errors':clone(exc.errors)}
            for old_item in old.required_outputs:
                new_item = revised_spec.delivery(old_item.key)
                if old_item.required and (new_item is None or not new_item.required or
                    any(rule not in new_item.acceptance_rule for rule in old_item.acceptance_rule)):
                    return self.store._error("CANNOT_DROP_OBLIGATION","A replan cannot silently remove required results or weaken accepted scientific conditions")
            # Graph revision validates no-op, limits and dependencies before
            # committing. A rejected proposal must not suspend the live goal.
            try:result = self.graph.revise(args["task_id"],updates,args["reason"])
            except (ValueError, TypeError) as exc:
                return self.store._error("INVALID_PLAN_REVISION", str(exc)[:600])
            if self.store.active:
                self.store.settle_active(["Plan revision preserves the previous version"])
            for ident in result["invalidated"]:
                dependent = self.graph.nodes[ident]
                self.node_goals.pop((ident,dependent.revision),None)
            self.current = None
            self.turn_nodes.add(args["task_id"])
            self.plan_events.append({"event":"revision",**clone(result),
                'proposal':clone(args),'normalized_updates':clone(updates)})
            return {"status":"revised",**result}
        if name in {"select_task","complete_node","check_deliveries","wait_node"}:
            if name == 'complete_node' and ('output_key' in args or 'revision' in args or 'result_id' in args):
                node = self.graph.nodes.get(args['task_id'])
                if node is None or not all(k in args for k in ('output_key','revision','result_id')):
                    return self.store._error('INVALID_DELIVERY_ACCEPTANCE','Local acceptance requires task_id, output_key, revision and result_id')
                return self._accept_delivery(node,args['output_key'],args['revision'],args['result_id'])
            node = self.graph.nodes[args["task_id"]]
            if name == "check_deliveries":return {"status":"checked",**self.delivery_check(node)}
            if name == "select_task":
                if node.status == 'TASK_COMPLETED':
                    return {'status':'already_completed','task_id':node.task_id,'revision':node.revision,
                            'outputs':{k:self._locator(v) for k,v in node.outputs.items()},
                            'guidance':'Use read_dependency for exact evidence, or revise_plan for changed conditions; no computation is pending.'}
                if node not in self.graph.ready_nodes() and node.task_id != self.current:
                    return self.store._error("DEPENDENCY_NOT_READY","Required inputs have not actually been delivered")
                return self._activate(node)
            if name == "complete_node":return self._complete(node,proposed=True)
            node.status,node.unresolved = "WAITING_INPUT",[args["reason"]]
            if self.current == node.task_id:
                self.store.settle_active(node.unresolved)
                self.current = None
            return {"status":"waiting","task_id":node.task_id}
        if name == "read_dependency":return self._read(**args)
        if name == "finish_task":
            proposed_questions=args.pop('clarifications',[])
            questions=[]
            for question in proposed_questions:
                node=self.graph.nodes.get(question['task_id'])
                d=node.delivery(question['key']) if node else None
                if not d or d.capability not in NUMERIC_TOOLS:
                    return self.store._error('INVALID_CLARIFICATION','Identify an existing scientific delivery')
                registry=self.store.contexts[d.record].executor.registry
                contract=computation_scope(registry,d.capability)
                required=set(self.store._required_fields(d.capability))
                effective=self._effective_scope(d)
                fields=question['fields']
                if (args.get('status')=='completed' or len(set(fields))!=len(fields) or
                        not set(fields).issubset(required-set(effective)) or
                        any(k not in contract['properties'] for k in fields) or
                        node.outputs.get(d.key) or not node.unresolved and node.status!='WAITING_INPUT'):
                    return self.store._error('INVALID_CLARIFICATION','Ask only for actual missing scientific fields of an unresolved delivery')
                text=f"请提供记录{d.record}、任务{node.task_id}、交付{d.key}（{d.capability}，已知条件{json.dumps(effective,ensure_ascii=False)}）所缺的科学参数：{', '.join(fields)}。"
                from .scientific_request_binding import window_availability
                assessment=window_availability(self.store,d.capability,effective,d.record,fields)
                if assessment['status']!='missing_literal_window':
                    text=f"记录{d.record}、任务{node.task_id}的窗口来源{'已提供，计划漏登记，应通过revise_plan修复' if assessment['status']=='known_user_window' else '需要审核，不能认定用户缺参'}。"
                questions.append({**clone(question),'record':d.record,'capability':d.capability,
                    'scope':clone(effective),'revision':node.revision,'turn':self.store.turn,'question':text,
                    'verification':assessment['status'],'source_assessment':assessment})
            if questions:args['answer']+='\n\n'+'\n'.join(q['question'] for q in questions)
            pending = [n for n in self.graph.nodes.values() if n.task_id in self.turn_nodes and n.status != "TASK_COMPLETED"]
            if args.get("status") == "completed" and pending:
                return {**self.store._error("UNFINISHED_PLAN","Deliver required outputs or report honest partial/clarification"),
                        "pending":[n.task_id for n in pending]}
            result=ManagedMemoryController._dispatch(self,ToolRequest(name,args,request.request_id))
            if result.get('status') in {'completed','partial','clarification_required'}:
                self.clarifications=questions
                result['clarifications']=clone(questions)
            return result
        if name in NUMERIC_TOOLS | {"compare_results"}:
            if self.batch_size>1 and 'task_id' not in owner:
                return self.store._error('ACTION_OWNER_REQUIRED','Each scientific action in a batch needs task_id and output_key; selects do not bind later calls')
            if owner:
                node=self.graph.nodes.get(owner.get('task_id'))
                if node is None or owner.get('revision',node.revision)!=node.revision:
                    return self.store._error('INVALID_ACTION_OWNER','Use an existing task and its current revision')
                d=node.delivery(owner.get('output_key'))
                optional=name in node.optional_operations and 'output_key' not in owner
                if name not in METADATA and not optional and (d is None or d.capability!=name):
                    return self.store._error('INVALID_ACTION_OWNER','output_key must name a delivery of this capability')
                bound=self._execution_scope(d,node.outputs.get(d.key),node.task_id) if d else {}
                if d and (args.get('record',d.record)!=d.record or any(
                        args.get(k,v)!=v for k,v in {**bound,**self._effective_scope(d)}.items())):
                    return self.store._error('ACTION_OWNER_SCOPE_CONFLICT','Revise the planned delivery before changing its scientific scope')
                if bound and args.get('artifact_id',node.outputs[d.key]['input_artifact'])!=node.outputs[d.key]['input_artifact']:
                    return self.store._error('ARTIFACT_DEPENDENCY_MISMATCH','Revise the delivery before changing its bound execution artifact')
                if node not in self.graph.ready_nodes() and node.task_id!=self.current and node.status!='TASK_COMPLETED':
                    return self.store._error('DEPENDENCY_NOT_READY','Owner has missing dependencies or is waiting; revise or resume it first')
                if d and any(not self._input_ready(r) for r in d.input_refs):
                    return self.store._error('DELIVERY_INPUT_NOT_READY','This delivery needs actual accepted producer outputs; execute its producers or repair the declared references first')
                activated=self._activate(node)
                if activated.get('status')!='selected':return activated
            if not self.current:
                return self.store._error("PLAN_REQUIRED","Propose scientific tasks from the user request first")
            node = self.graph.nodes[self.current]
            outputs = [d for d in node.required_outputs if d.capability == name and
                       (not owner or d.key==owner.get('output_key'))]
            if not outputs and name not in node.optional_operations and name not in METADATA:
                return self.store._error("ACTION_OUTSIDE_NODE","Use the current node's outputs or declared optional operations; replan for another scientific task")
            if len(outputs)==1:
                try:self._validate_reference_fields(outputs[0],self.graph,('required_outputs',outputs[0].key))
                except ContractError as exc:
                    return {**self.store._error('INVALID_PLAN_SOURCE',str(exc)),'field_path':exc.path,
                            'recovery':{'tool':'revise_plan','task_id':node.task_id,'output_key':outputs[0].key,
                                        'revision':node.revision,'field':'input_refs'}}
            if name in NUMERIC_TOOLS:
                # Fill only unambiguous planned inputs; execute_action still
                # grounds them against the complete real request/history.
                matching = [d for d in outputs if all(args.get(k,v)==v for k,v in self._effective_scope(d).items())
                            and args.get("record",d.record)==d.record and d.key not in node.outputs]
                selected = matching[0] if len(matching)==1 else None
                if outputs and not selected:
                    # A valid existing output may be reused for an explicit repeat.
                    matches = [d for d in outputs if all(args.get(k,v)==v for k,v in self._effective_scope(d).items()) and args.get("record",d.record)==d.record]
                    selected = matches[0] if len(matches)==1 else None
                    if not selected:
                        return self.store._error("AMBIGUOUS_DELIVERY","Select the exact current output scope/record; no guessed ordering")
                if selected:
                    bound=self._execution_scope(selected,node.outputs.get(selected.key),node.task_id)
                    if bound:
                        artifact=node.outputs[selected.key]['input_artifact']
                        if args.get('artifact_id',artifact)!=artifact or any(args.get(k,v)!=v for k,v in bound.items()):
                            return self.store._error('ARTIFACT_DEPENDENCY_MISMATCH','Revise the delivery before changing its bound execution artifact or scope')
                        args.setdefault('artifact_id',artifact)
                    if any(not self._input_ready(r) for r in selected.input_refs):
                        return self.store._error('DELIVERY_INPUT_NOT_READY','This delivery needs actual accepted producer outputs')
                    args.setdefault("record",selected.record)
                    if selected.interpretation:
                        if 'channel_reference' in args:
                            return self.store._error('INTERPRETATION_CONFLICT',
                                'Numeric actions cannot revise planned field relations. Use revise_plan on required_outputs[].interpretation.channel_reference')
                        if 'interpretation' in args and args['interpretation'] != selected.interpretation:
                            return self.store._error('INTERPRETATION_CONFLICT','Revise the task interpretation before changing its meaning')
                        args['interpretation'] = clone(selected.interpretation)
                    spec = self.store.contexts[selected.record].executor.registry.get(name)
                    if not spec.consumes_artifact:
                        for k,v in self._effective_scope(selected).items():args.setdefault(k,clone(v))
                    previous = (node.revision_history[-1]['snapshot']['outputs'].get(selected.key)
                                if node.revision_history else None)
                    binding=self._binding(selected,previous=self._entry_for(previous),
                        output=node.outputs.get(selected.key),task_id=node.task_id,artifact_id=args.get('artifact_id'))
                    if not binding.ok:
                        return self.store._error('ARTIFACT_DEPENDENCY_MISMATCH','; '.join(binding.conflicts))
                    if binding.artifact_id:args.setdefault('artifact_id',binding.artifact_id)
                    if binding.entry:
                        if args.get('inherit_result',binding.entry.task_id)!=binding.entry.task_id:
                            return self.store._error('SOURCE_DEPENDENCY_MISMATCH','Use the explicitly resolved scientific source')
                        args.setdefault('inherit_result',binding.entry.task_id)
            elif len(outputs)==1:
                refs = outputs[0].input_refs
                if any(not self._input_ready(r) for r in refs):
                    return self.store._error('DELIVERY_INPUT_NOT_READY','Comparison operands must actually be delivered')
                for side,ref in zip(("left","right"),refs):
                    ident = (self._ref_output(ref) or {}).get("result_id")
                    args.setdefault(f"{side}_result",ident)
                    args.setdefault(f"{side}_path",ref.fields[0])
                    if args[f"{side}_result"]!=ident or args[f"{side}_path"]!=ref.fields[0]:
                        return self.store._error("COMPARISON_DEPENDENCY_MISMATCH","Use the declared actual operands and fields")
            result = super()._dispatch(ToolRequest(name,args,request.request_id))
            if result.get('code')=='INVALID_SCIENTIFIC_INTERPRETATION':
                result['recovery']={'tool':'revise_plan','task_id':node.task_id,
                    'field':'required_outputs[].interpretation',
                    'message':'Repair the source/field relation in the planned delivery, keeping its required scope. Numeric action arguments cannot override the plan; genuine ambiguity still needs clarification.'}
            node.attempts.append({"name":name,"arguments":clone(args),"status":result.get("status"),"code":result.get("code")})
            self._sync_outputs(node,result,selected if name in NUMERIC_TOOLS else None)
            # An attempted handle is not evidence of successful consumption.
            # Keep failures in the same audit trail without counting them as use.
            succeeded = result.get("status") in {"observed", "reused", "compared"}
            self.evidence_log.append({"event":"used" if succeeded else "use_attempt",
                "success":succeeded,"result_status":result.get("status"),
                "error_code":result.get("code"),"task_id":node.task_id,"tool":name,
                "inherit_result":args.get("inherit_result"),"artifact_id":args.get("artifact_id"),
                "used_by":"adapter_bound_tool_operands","model_supplied_arguments":clone(dict(request.arguments)),
                "comparison_operands":[r["result_id"] for r in result.get("operands",[])],
                "meaning":"Observed actual handle use, not proof of model reasoning causality"})
            check = self.delivery_check(node)
            if check["all_outputs_present"]:
                result["node_completion"] = self._complete(node)
            return result
        return super()._dispatch(request)

    def _input_ready(self, ref):
        resolved=self.graph.resolve_ref(ref)
        if resolved['output_status'] not in {'DELIVERY_SATISFIED','TASK_COMPLETED'}:return False
        d=DeliveryItem.from_dict(resolved['delivery'])
        if resolved['output'].get('execution_scope_binding') and not self._execution_scope(d,resolved['output'],ref.task_id):return False
        if d.acceptance_rule and not self._acceptance_valid(d,resolved['output'],resolved['output_status']):return False
        entry=self._entry_for(resolved['output'])
        return self.store._binding_valid(entry) if entry else self._valid_comparison(resolved['output'])

    def snapshot(self):
        result = super().snapshot()
        result.update(method_version="shared_plan_execute_v1",arm=self.arm,
            plan=[n.to_dict() for n in self.graph.nodes.values()],plan_events=clone(self.plan_events),
            graph_history=clone(self.graph.history),evidence_access=clone(self.evidence_log),
            action_transitions=clone(self.action_transitions),clarifications=clone(self.clarifications))
        result['control_progress']=clone(getattr(self,'progress_events',[]))
        return result


class TaskPlanEEGAgent(EEGAgent):
    """One shared original loop, with planner/local-executor phases in context."""
    def __init__(self, llm_client, records, *, arm="C", session_id="plan", max_rounds=24,
                 max_tool_calls=36, config=None, **options):
        store = PlannedTaskStore(session_id,records,config=config)
        controller = TaskPlanController(store,arm=arm,**options)
        super().__init__(llm_client,next(iter(store.contexts.values())),max_rounds,max_tool_calls,working_memory=controller)

    def continue_run(self, request):
        return self.run(request)
