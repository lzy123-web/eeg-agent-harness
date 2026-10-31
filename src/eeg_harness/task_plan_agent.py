"""Shared Plan-and-Execute controls over the original EEGAgent and Executor.

The plan is a model proposal, never a source of scientific authorization. A/B/C
share identity, provenance, versions, full read rights and local replanning.
Only acceptance automation and dependency evidence presentation are varied.
"""
import json
import re

from .agent import EEGAgent
from .executor import _validate_schema
from .tooling import ToolRequest
from .working_memory import WorkingMemoryStore, NUMERIC_TOOLS, clone, encoded
from .working_memory_agent import WorkingMemoryController, control, STRING
from .working_memory_managed import ManagedMemoryController, managed_controls
from .working_memory_scientific import ScientificMemoryController
from .working_memory_scientific_tasks import ScientificTaskStore, canonical_scope
from .working_memory_lifecycle import METADATA
from .result_semantics import read_scalar, result_field_semantics
from .task_plan import PlanGraph, TaskSpec


ARMS = ("A", "B", "C", "C-no-delivery", "C-no-selection", "A-equivalent")
SYSTEM = """你是多任务EEG分析Agent。先依据用户原请求提出最小科学任务DAG(plan_tasks)，不是固定工具脚本。
同一目的可有多个不同窗口或记录的结果key。task_id由你提出后保持稳定；改标题不创建新身份。补参/条件修订用revise_plan，原结果与旧版本保留。
dependencies表示依赖；input_refs明确依赖哪个key、需要哪些字段以及summary/result/process层级。计划不是科学授权；数值参数仍必须来自真实用户或合法历史。
调度器只选择已具备实际依赖的当前节点。你为当前节点选择局部工具动作；程序自动绑定结果key/工件/版本，不用反复抄已知ID。动作可省略已明确scope参数，程序仍核对用户来源。
需要上游工件时使用input_refs提供的真实句柄；compare_results对真实结果做描述性差值比值，不心算。跨记录/版本不能混用；事件窗是相对时间，连续窗是记录绝对时间。未授权的处理不能执行。
所有方案都能read_dependency/read_result或restore_task，精确数值读取与过程恢复不同。摘要足够则不强迫多读；要核对过程再继续时恢复原行动观察，不能把索引当数值。
check_deliveries可读所有方案相同的交付诊断。明确质量/计数条件须依据实际结果判断；辅助尝试失败不等于科学交付失败。缺参可wait_node并推进独立节点，最后真实澄清或partial。
不要删除用户要求或降低科学条件以完成任务。任务完成不证明原自然请求无遗漏。finish_task必须给原用户所需实际数值、单位、来源/范围、新旧版本及未完成事项；不作诊断或无依据的因果解释。
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
        self.pending_archive = None
        self.automatic_acceptance = arm in {"C", "C-no-selection", "A-equivalent"}
        self.dependency_selection = arm in {"C", "C-no-delivery"}

    def begin_turn(self, request):
        super().begin_turn(request)
        self.current = None
        self.turn_nodes = set()

    def control_definitions(self):
        from .task_plan import TASK_SPEC_SCHEMA
        controls = [c for c in super().control_definitions()
                    if c["function"]["name"] != "focus_task"]
        next(c["function"] for c in controls if c["function"]["name"] == "compare_results")["parameters"]["required"] = []
        controls += [
            control("plan_tasks", "Propose scientific subtask DAG from the user request. No runtime facts or result IDs may be invented.", {
                "nodes": {"type": "array", "minItems": 1, "maxItems": 12,
                          "items": clone(TASK_SPEC_SCHEMA)}}, ["nodes"]),
            control("revise_plan", "Fill missing conditions or legitimately revise this stable task; preserve prior versions and invalidate affected dependents. Never drop user obligations.", {
                "task_id": STRING, "updates": {"type": "object"}, "reason": STRING}, ["task_id", "updates", "reason"]),
            control("select_task", "Choose a ready independent node; no fabricated dependency satisfaction.", {"task_id": STRING}, ["task_id"]),
            control("complete_node", "Declare scientific acceptance after inspecting all real required results. Does not hide missing outputs.", {"task_id": STRING}, ["task_id"]),
            control("wait_node", "Suspend this node for genuine missing science or inability; other ready nodes remain available.", {"task_id": STRING, "reason": STRING}, ["task_id", "reason"]),
            control("check_deliveries", "Read real output matching and scientific predicate evaluation; equally available to every arm.", {"task_id": STRING}, ["task_id"]),
            control("read_dependency", "Read a real planned output at summary/result/process level. All modes have identical raw evidence and process read rights.", {
                "task_id": STRING, "key": STRING, "revision":{"type":"integer","minimum":1}, "level": {"type":"string","enum":["summary","result","process"]},
                "fields": {"type":"array","maxItems":4,"items":{"type":"array","items":{"type":["string","integer"]}}}}, ["task_id","key","level"]),
        ]
        return controls

    def _goal(self, node):
        ident = self.node_goals.get((node.task_id, node.revision))
        return self.store.find_subgoal(ident) if ident else None

    def _activate(self, node):
        if self.current != node.task_id:
            # A closed node's native pair remains in the external archive. Its
            # next consumer receives the dependency view, not an accidental
            # second full-result copy via the controller's pending last pair.
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
                if self._matches(d,entry):
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
            for r in n.input_refs())]
        if ready:
            self._activate(ready[0])

    def _validate_nodes(self, specs):
        for node in specs:
            for d in node.required_outputs:
                if d.record not in self.store.records or d.capability not in NUMERIC_TOOLS | {"compare_results"}:
                    raise ValueError("Unknown record or enabled capability")
                if d.capability in NUMERIC_TOOLS:
                    self.store._parse_requirements([{"tool":d.capability,"record":d.record,"scope":d.scope}],d.record)
                elif d.scope or len(d.input_refs)!=2 or any(len(r.fields)!=1 for r in d.input_refs):
                    raise ValueError("A comparison needs two actual input references with one field each, and empty computation scope")
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
                    node.output_status[key] = "STALE"
                    node.status = "STALE"
                    node.unresolved = ["An actual evidence binding is no longer applicable"]

    def _effective_scope(self, delivery):
        sources = [self._entry_for(self._ref_output(r)) for r in delivery.input_refs]
        same = [e for e in sources if e and e.record == delivery.record and self.store._binding_valid(e)
                and self.store._family(e.capability) == self.store._family(delivery.capability)]
        inherited = same[0].parameters if len(same) == 1 else {}
        return {**clone(inherited),**clone(delivery.scope)}

    def _matches(self, d, entry):
        if not entry or not self.store._binding_valid(entry):
            return False
        if entry.record != d.record or entry.capability != d.capability:
            return False
        scope = self._effective_scope(d)
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

    def _sync_outputs(self, node, result=None):
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
                        self.graph.mark_output(node.task_id,d.key,{"comparison_id":result["comparison_id"],"result":clone(result),"revision":node.revision})
                continue
            found = [self.store.find_entry(i) for i in identifiers if self._matches(d,self.store.find_entry(i))]
            if found:
                entry = found[-1]
                self.graph.mark_output(node.task_id,d.key,{
                    "result_id":entry.task_id,"record":entry.record,"actual_scope":clone(entry.parameters),
                    "originating_task":node.task_id,"actual_parameters":clone(entry.parameters),"source":entry.evidence["source"],
                    "processing_version":clone(entry.evidence["binding"]),"revision_of":entry.revision_of,
                    "input_artifact":entry.evidence["binding"]["artifact_id"] if d.capability!="create_epochs" else None,
                    "output_artifact":entry.evidence["binding"]["artifact_id"] if d.capability=="create_epochs" else None,
                    "unit_or_kind":entry.evidence["unit_or_kind"],
                    "result_pointer":entry.task_id,"AO_pointer":entry.evidence["subgoal_id"],"revision":node.revision},
                    status="TOOL_SUCCEEDED" if d.acceptance_rule else "DELIVERY_SATISFIED")
        if self.automatic_acceptance:
            for row in self.delivery_check(node)["outputs"]:
                if row["accepted"]:
                    node.output_status[row["key"]] = "DELIVERY_SATISFIED"

    def delivery_check(self, node):
        rows = []
        for d in node.required_outputs:
            output = node.outputs.get(d.key)
            entry = self._entry_for(output)
            valid = self._matches(d,entry) if d.capability != "compare_results" else self._valid_comparison(output)
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
        if not proposed and not self.automatic_acceptance and any(d.acceptance_rule for d in node.required_outputs if d.required):
            node.status = "TOOL_SUCCEEDED"
            return {"status":"acceptance_review_required","check":check}
        goal = self._goal(node)
        if goal and goal.requirements and not self.store.completion_check(goal)["valid"]:
            return self.store._error("ARCHIVE_CONTRACT_MISMATCH","Plan outputs and task archive disagree; preserve partial results")
        node.status = "TASK_COMPLETED"
        for row in check["outputs"]:
            if row["output_valid"] and (row["accepted"] or proposed and not self.automatic_acceptance):
                node.output_status[row["key"]] = "DELIVERY_SATISFIED"
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
        if not output:
            return self.store._error("DEPENDENCY_UNDELIVERED","No actual output at that key/version")
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
        payload["plan"] = [{**n.to_dict(runtime=False),"status":n.status,"revision":n.revision}
                           for n in self.graph.nodes.values()]
        payload["phase"] = "local_execution" if node else "plan_or_final_delivery"
        payload["current_plan_task"] = node.task_id if node else None
        payload["dependency_evidence"] = self._inputs(node) if node else []
        payload["task_summaries"] = [{"task_id":n.task_id,"goal":n.goal,"revision":n.revision,
            "status":n.status,"outputs":{k:self._locator(v) for k,v in n.outputs.items()},
            "unresolved":clone(n.unresolved)} for n in self.graph.nodes.values()]
        messages[0]["content"] = SYSTEM + ("\n明确科学条件由程序自动核验。" if self.automatic_acceptance else
            "\n必需结果齐备后，显式科学条件由你据真实结果评估；可调用check_deliveries，再complete_node或明确partial。")
        messages[1]["content"] = encoded(payload).decode("utf8")
        return messages

    def build_messages(self, **kwargs):
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
        messages[0]["content"] = SYSTEM
        payload = json.loads(messages[1]["content"])
        payload["plan_status"] = [{"task_id":n.task_id,"revision":n.revision,"status":n.status,
                                   "unresolved":clone(n.unresolved)} for n in self.graph.nodes.values()]
        messages[1]["content"] = encoded(payload).decode("utf8")
        return messages,tools

    def _dispatch(self, request):
        name,args = request.name,clone(dict(request.arguments))
        spec = next((c["function"] for c in self.control_definitions() if c["function"]["name"] == name),None)
        if spec:
            _validate_schema(args,spec["parameters"])
        if self.final_only and name != "finish_task":
            return self.store._error("FINAL_DELIVERY_ONLY","Only the reserved final answer is available")
        if name == "plan_tasks":
            specs = [TaskSpec.from_dict(n) for n in args["nodes"]]
            self._validate_nodes(specs)
            self.graph.submit(specs)
            self.turn_nodes.update(n.task_id for n in specs)
            return {"status":"planned","task_ids":[n.task_id for n in specs]}
        if name == "revise_plan":
            old = self.graph.nodes[args["task_id"]]
            proposed = old.to_dict()
            allowed = old.to_dict(runtime=False)
            allowed.update(args["updates"])
            revised_spec = TaskSpec.from_dict(allowed)
            self._validate_nodes([revised_spec])
            for old_item in old.required_outputs:
                new_item = revised_spec.delivery(old_item.key)
                if old_item.required and (new_item is None or not new_item.required or
                    any(rule not in new_item.acceptance_rule for rule in old_item.acceptance_rule)):
                    return self.store._error("CANNOT_DROP_OBLIGATION","A replan cannot silently remove required results or weaken accepted scientific conditions")
            if self.store.active:
                self.store.settle_active(["Plan revision preserves the previous version"])
            result = self.graph.revise(args["task_id"],args["updates"],args["reason"])
            for ident in result["invalidated"]:
                dependent = self.graph.nodes[ident]
                self.node_goals.pop((ident,dependent.revision),None)
            self.current = None
            self.turn_nodes.add(args["task_id"])
            self.plan_events.append({"event":"revision",**clone(result)})
            return {"status":"revised",**result}
        if name in {"select_task","complete_node","check_deliveries","wait_node"}:
            node = self.graph.nodes[args["task_id"]]
            if name == "check_deliveries":return {"status":"checked",**self.delivery_check(node)}
            if name == "select_task":
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
            pending = [n for n in self.graph.nodes.values() if n.task_id in self.turn_nodes and n.status != "TASK_COMPLETED"]
            if args.get("status") == "completed" and pending:
                return {**self.store._error("UNFINISHED_PLAN","Deliver required outputs or report honest partial/clarification"),
                        "pending":[n.task_id for n in pending]}
            return ManagedMemoryController._dispatch(self,request)
        if name in NUMERIC_TOOLS | {"compare_results"}:
            if not self.current:
                return self.store._error("PLAN_REQUIRED","Propose scientific tasks from the user request first")
            node = self.graph.nodes[self.current]
            outputs = [d for d in node.required_outputs if d.capability == name]
            if not outputs and name not in node.optional_operations and name not in METADATA:
                return self.store._error("ACTION_OUTSIDE_NODE","Use the current node's outputs or declared optional operations; replan for another scientific task")
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
                    args.setdefault("record",selected.record)
                    spec = self.store.contexts[selected.record].executor.registry.get(name)
                    if not spec.consumes_artifact:
                        for k,v in self._effective_scope(selected).items():args.setdefault(k,clone(v))
                    entries = [self._entry_for(self._ref_output(r)) for r in selected.input_refs]
                    entries = [e for e in entries if e]
                    if spec.consumes_artifact and len({e.evidence["binding"]["artifact_id"] for e in entries})==1:
                        args.setdefault("artifact_id",entries[0].evidence["binding"]["artifact_id"])
                    same = [e for e in entries if e.record==selected.record and self.store._family(e.capability)==self.store._family(name)]
                    if len(same)==1:args.setdefault("inherit_result",same[0].task_id)
                    elif node.revision_history and not args.get("inherit_result"):
                        previous = node.revision_history[-1]["snapshot"]["outputs"].get(selected.key)
                        old_entry = self._entry_for(previous)
                        if old_entry and old_entry.record==selected.record and old_entry.capability==name:
                            args["inherit_result"] = old_entry.task_id
            elif len(outputs)==1:
                refs = outputs[0].input_refs
                for side,ref in zip(("left","right"),refs):
                    ident = (self._ref_output(ref) or {}).get("result_id")
                    args.setdefault(f"{side}_result",ident)
                    args.setdefault(f"{side}_path",ref.fields[0])
                    if args[f"{side}_result"]!=ident or args[f"{side}_path"]!=ref.fields[0]:
                        return self.store._error("COMPARISON_DEPENDENCY_MISMATCH","Use the declared actual operands and fields")
            result = super()._dispatch(ToolRequest(name,args,request.request_id))
            node.attempts.append({"name":name,"arguments":clone(args),"status":result.get("status"),"code":result.get("code")})
            self._sync_outputs(node,result)
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

    def snapshot(self):
        result = super().snapshot()
        result.update(method_version="shared_plan_execute_v1",arm=self.arm,
            plan=[n.to_dict() for n in self.graph.nodes.values()],plan_events=clone(self.plan_events),
            graph_history=clone(self.graph.history),evidence_access=clone(self.evidence_log))
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
