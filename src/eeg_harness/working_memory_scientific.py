"""Scientific result-instance working memory on the original Agent/Executor.

The model organizes purposes, proposes actions and interprets the request.
The program owns result identity, scoped completion and deterministic arithmetic.
This is an opt-in successor; historical managed experiments are unchanged.
"""
import math

from .executor import _validate_schema
from .result_semantics import read_scalar, result_field_semantics, UnsupportedResultField
from .working_memory import clone, encoded
from .working_memory_agent import control, STRING
from .working_memory_managed import ManagedMemoryController, managed_controls


SCIENTIFIC_SYSTEM = """你是多轮EEG科学分析助手。通过真实科学工具完成用户目的；数值、来源、版本和工件身份由程序维护。
相关的多个结果服务于同一科学目的时，先用focus_task描述这个目的及所需结果实例requirements。同一能力在不同记录、对象或窗口产生不同实例；不是列工具顺序，也不要把每个动作都拆成一个任务。简单单结果可直接执行。
requirements里的scope只填用户实际已给条件，缺少的留空，后续根据用户补充和真实结果完善；一个事件范围缺参不阻断其他独立连续分析。程序会保持未满足项，所有结果都满足后才允许完整归档。切换目的或结束时程序归档/暂挂，模型不用抄结果ID证明已执行。
当前任务行动观察参与下一行动；历史任务摘要保留真实条件、版本、精确小字段及未完成项。read_result读某个真实字段；restore_task恢复旧目的的真实行动观察，用于需要过程的后续分析。简单可见数值不必额外读取；恢复要有实际用途。
科学参数必须来自完整用户请求或明确继承的真实结果。request_span只是可选原文定位，不能通过删去前文改变记录、对象、时间归属。inherit_result继承原条件，改变字段仍须当前用户支持。复用有效结果，只有明确要求才重算。保留旧版本；使用原试次时必须沿用真实artifact_id，内容相等不是同一工件。
若需要两个已有数值的差值或比值，用compare_results对真实字段计算，程序保留双方来源、范围、单位；不要心算改写。比较只是描述，不证明因果。窗口与事件在时间上重叠不能说明含有诱发成分。没有运行质量工具不能声称质量通过。
此入口不授权筛选、基线校正或新变换。事件相对窗不能取连续绝对窗代替。不猜用户没有给的窗口。
finish_task给出完整中文结果(completed)、真实未完成项(partial)或缺失科学参数(clarification_required)。检查原始请求所有科学目的；程序的已声明任务完成不证明未声明意图无遗漏。给对象、范围、版本、必要数值、单位、处理状态和限制。优先canonical_display；幅值V/µV，绝对功率V²/µV²不是ERD/ERS、临床结论或能力评分。"""


def scientific_controls():
    controls = managed_controls()
    controls[0] = control("focus_task", "Organize one scientific purpose with its required result instances; not an execution sequence. Missing scope parameters can be supplied later. Short single-result work needs no declaration.", {
        "title": STRING, "record": STRING,
        "requirements": {"type": "array", "minItems": 1, "maxItems": 12,
            "items": {"type": "object", "properties": {
                "tool": STRING, "record": STRING,
                "scope": {"type": "object", "description": "Actual scientific parameters, e.g. channels/start/end or labels/tmin/tmax. Never artifact IDs or guessed values."}},
                "required": ["tool", "record", "scope"], "additionalProperties": False}}}, ["title", "requirements"])
    path = {"type": "array", "minItems": 1, "items": {"type": ["string", "integer"]}}
    controls.append(control("compare_results", "Calculate right-minus-left and right/left from two valid numeric scientific fields. Retains both scopes and versions; never infers causality or clinical meaning.", {
        "left_result": STRING, "right_result": STRING, "left_path": path, "right_path": path},
        ["left_result", "right_result", "left_path", "right_path"]))
    return controls


class ScientificMemoryController(ManagedMemoryController):
    def __init__(self, store, **kwargs):
        super().__init__(store, **kwargs)
        self.comparisons = []
        self.visible_comparisons = []

    def begin_turn(self, request):
        super().begin_turn(request)
        self.visible_comparisons = []

    def control_definitions(self):
        return scientific_controls()

    def _card(self, goal, **kwargs):
        card = super()._card(goal, **kwargs)
        actual = self.store.goal_card(goal)
        for key in ("requirements", "records", "default_record", "current_execution_record", "contract_version"):
            if key in actual:
                card[key] = clone(actual[key])
        return card

    def _view(self):
        messages = super()._view()
        messages[0]["content"] = SCIENTIFIC_SYSTEM
        if self._current_comparisons():
            messages.append({"role": "user", "content": encoded({"verified_comparisons": self._current_comparisons()}).decode("utf8")})
        return messages

    def build_final_messages(self, reason="resource_reserve"):
        messages, tools = super().build_final_messages(reason)
        messages[0]["content"] = SCIENTIFIC_SYSTEM
        if self._current_comparisons():
            messages.append({"role": "user", "content": encoded({"verified_comparisons": self._current_comparisons()}).decode("utf8")})
        return messages, tools

    def _current_comparisons(self):
        valid = []
        for comparison in self.visible_comparisons:
            operands_valid = True
            for row in comparison["operands"]:
                entry = self.store.find_entry(row["result_id"])
                try:
                    operands_valid &= bool(entry and self.store._binding_valid(entry)
                        and row["binding"] == entry.evidence["binding"]
                        and float(read_scalar(entry.result, row["field"])) == row["value"])
                except (UnsupportedResultField, ValueError, TypeError):
                    operands_valid = False
            if operands_valid:
                valid.append(comparison)
        return valid

    def _compare(self, left_result, right_result, left_path, right_path):
        s = self.store
        entries = [s.find_entry(left_result), s.find_entry(right_result)]
        if any(e is None or not s._binding_valid(e) for e in entries):
            return s._error("INVALID_RESULT", "Both results must be real, immutable and currently valid")
        rows = []
        signatures = []
        try:
            for entry, path in zip(entries, (left_path, right_path)):
                cfg = entry.evidence["analysis_configuration"]
                meaning = result_field_semantics(entry.capability, path, entry.result,
                    parameters=entry.parameters, analysis_configuration=cfg)
                if meaning["value_type"] == "string":
                    raise UnsupportedResultField("Metadata is not a numeric comparison")
                value = float(read_scalar(entry.result, path))
                if not math.isfinite(value):
                    raise UnsupportedResultField("Nonfinite value")
                # A common unit alone is insufficient (alpha vs theta, RMS vs
                # maximum, continuous vs mean Epoch power must not be conflated).
                signatures.append((entry.capability, meaning["kind"], meaning["unit_or_kind"], path[-1],
                    encoded(cfg)))
                rows.append({"result_id": entry.task_id, "record": entry.record,
                    "scope": clone(entry.parameters), "source": entry.evidence["source"],
                    "revision_of": entry.revision_of, "field": clone(path), "value": value,
                    "unit": meaning["unit_or_kind"], "binding": clone(entry.evidence["binding"])})
            if signatures[0] != signatures[1]:
                return s._error("INCOMPARABLE_FIELDS", "Quantity, field, capability and analysis configuration must agree")
        except (UnsupportedResultField, ValueError, TypeError, KeyError):
            return s._error("UNSUPPORTED_COMPARISON", "Select numeric fields with an actual field-level scientific contract")
        a, b = (row["value"] for row in rows)
        delta, ratio = b-a, b/a if a else None
        if not math.isfinite(delta) or ratio is not None and not math.isfinite(ratio):
            return s._error("NONFINITE_COMPARISON", "Difference or ratio is not finite")
        result = {"status": "compared", "comparison_id": f"{s.session_id}-c{len(self.comparisons)+1}",
            "operands": rows, "right_minus_left": delta, "difference_unit": rows[0]["unit"],
            "right_divided_by_left": ratio, "ratio_unit": "dimensionless",
            "ratio_undefined_reason": "zero denominator" if a == 0 else None,
            "canonical_display": f"right-minus-left={delta:.12g} {rows[0]['unit']}; right/left={ratio:.12g}" if ratio is not None else f"right-minus-left={delta:.12g} {rows[0]['unit']}; ratio undefined (zero denominator)",
            "limitations": "Descriptive arithmetic across explicitly identified scopes/versions, not causal inference, normalized event response or clinical interpretation"}
        for entry, path in zip(entries, (left_path, right_path)):
            self._merge_seen_fields(entry, [{"path": path, "value": read_scalar(entry.result, path)}])
        self.comparisons.append(clone(result))
        self.visible_comparisons.append(clone(result))
        return result

    def _dispatch(self, request):
        if request.name == "finish_task" and request.arguments.get("status") == "completed":
            # Switching focus cannot make an already declared current purpose
            # disappear. Untouched historical suspensions are not a global gate.
            unmet = [g for g in self.store.subgoals
                     if getattr(g, "requirements", None)
                     and (g.turn == self.store.turn or g.subgoal_id in self.touched_goals)
                     and not self.store.completion_check(g)["valid"]]
            if unmet:
                return {**self.store._error("UNFINISHED_DECLARED_TASK", "Declared scientific results remain missing; continue or deliver an honest partial/clarification"),
                        "pending": [self._card(g) for g in unmet]}
        if request.name in {"focus_task", "compare_results"}:
            if self.final_only:
                return self.store._error("FINAL_DELIVERY_ONLY", "Only reserved final delivery is available")
            spec = next(x["function"] for x in scientific_controls() if x["function"]["name"] == request.name)
            _validate_schema(request.arguments, spec["parameters"])
            if request.name == "focus_task":
                result = self.store.focus_task(**request.arguments)
                if result.get("status") == "active":
                    # Selecting a purpose is not a read of all archived values.
                    # The canonical current requirement set is constructed once
                    # in active_task, rather than copied into every native reply.
                    return {"status": "active", "subgoal_id": self.store.active.subgoal_id,
                            "title": self.store.active.title,
                            "meaning": "Required results and readiness are in active_task; continue with actual scientific observations"}
                return result
            return self._compare(**request.arguments)
        return super()._dispatch(request)

    def execute(self, request, *, batch_size=1):
        result = super().execute(request, batch_size=batch_size)
        if isinstance(result.data, dict) and isinstance(result.data.get("progress"), dict):
            progress = result.data["progress"]
            rows = progress.get("deliveries", [])
            result.data["progress"] = {
                "subgoal_id": progress.get("subgoal_id"), "status": progress.get("status"),
                "deliveries": [{"instance_index": index, "status": row["status"],
                    "result_id": row.get("result_id")} for index, row in enumerate(rows)],
                "unresolved": progress.get("unresolved", [])}
        return result

    def snapshot(self):
        result = super().snapshot()
        result["verified_comparisons"] = clone(self.comparisons)
        result["method_version"] = "scientific_result_instances_v1"
        return result
