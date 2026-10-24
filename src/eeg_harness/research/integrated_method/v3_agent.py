"""Bounded native tool-calling bridge for instance-goal EEG evidence delivery."""

import json
from dataclasses import replace

from .intent import _value_supported_by_quote
from .semantics import concept_quote_is_grounded
from .v3 import (GoalInstance, InstanceTaskRequest, USER_CAPABILITIES,
                 capability_catalog, capability_inventory, run_instances)


CAPABILITY_CONCEPTS = {
    "record_info": "record_metadata", "record_quality": "quality_measurement",
    "amplitude": "time_domain_amplitude", "psd": "spectral_power",
    "seizure_detection": "seizure_detection", "epoch_quality": "quality_measurement",
    "epoch_summary": "epoch_summary", "event_bandpower": "spectral_power",
}
EVENT_CAPABILITIES = frozenset({"epoch_quality", "epoch_summary", "event_bandpower"})


def _intent_tool(catalog):
    return [{"type": "function", "function": {
        "name": "submit_eeg_goals",
        "description": "Submit every independent user-requested EEG scientific goal. Do not submit prerequisites.",
        "parameters": {"type": "object", "properties": {
            "goals": {"type": "array", "items": {"type": "object", "properties": {
                "instance_id": {"type": "string"},
                "capability": {"type": "string", "enum": [item["name"] for item in catalog]},
                "parameters": {"type": "object"},
                "request_quote": {"type": "string"},
                "concept_quote": {"type": "string"},
                "parameter_quotes": {"type": "object"},
                "source_stage": {"type": "string"},
            }, "required": ["instance_id", "capability", "parameters", "request_quote",
                            "concept_quote", "parameter_quotes"]}},
            "forbidden_operations": {"type": "array", "items": {"type": "string"}},
            "unsupported_requests": {"type": "array", "items": {"type": "string"}},
        }, "required": ["goals", "forbidden_operations", "unsupported_requests"]},
    }}]


def _safe_failure(status, code, details, goal_ids=()):
    unfulfilled = [{"instance_id": goal_id, "code": code,
                    "details": details.get(goal_id) if isinstance(details, dict) else None}
                   for goal_id in goal_ids]
    return {"status": status, "code": code, "details": details,
            "tool_results": [],
            "evidence_bundle": {"schema_version": "1", "status": status,
                                "goals": [], "unfulfilled_goals": unfulfilled,
                                "expected_goal_count": len(goal_ids), "published_goal_count": 0,
                                "publication": "none"},
            "answer": "需要澄清或当前能力不支持；未执行 EEG 工具。"}


def _quote_occurrences(text, quote):
    if not isinstance(quote, str) or not quote:
        return ()
    source, needle = text.casefold(), quote.casefold()
    return tuple((index, index + len(needle)) for index in range(len(source))
                 if source.startswith(needle, index))


def _overlaps(first, second):
    return first[0] < second[1] and second[0] < first[1]


def _preceding_equal_event_scope(goal, earlier_goals, text):
    """Bind a later event goal to the nearest equal scope in one sentence."""
    own = _quote_occurrences(text, goal.request_quote)
    boundary = frozenset("。！？!?；;\n")
    for prior in reversed(earlier_goals):
        if prior.capability not in EVENT_CAPABILITIES or not all(
                prior.parameters.get(key) == goal.parameters.get(key)
                for key in ("labels", "tmin", "tmax", "baseline")):
            continue
        for previous in _quote_occurrences(text, prior.request_quote):
            for current in own:
                if (previous[1] <= current[0]
                        and not any(char in boundary for char in text[previous[1]:current[0]])):
                    return prior.instance_id
    return None


def _same_frozen_quote(before, after):
    return before.strip(" \t\r\n，。,.!?！？；;") == after.strip(" \t\r\n，。,.!?！？；;")


def _parameter_ownership_errors(goals, text, previous=(), clarification_start=None):
    """Require distinct values of one slot to belong to their goal anchors.

    This is a structural span check, not a vocabulary-level intent parser. A
    shared value (for example a common channel) may be quoted outside both
    anchors; competing values may not be borrowed from another instance.
    """
    errors = {}
    for goal in goals:
        own = _quote_occurrences(text, goal.request_quote)
        for key, value in goal.parameters.items():
            if key in goal.parameter_sources:
                continue
            competitors = [other for other in goals if other is not goal
                           and key in other.parameters and other.parameters[key] != value]
            if not competitors:
                continue
            quoted = _quote_occurrences(text, goal.parameter_quotes.get(key))
            anchored = own and quoted and any(
                _overlaps(anchor, evidence) for anchor in own for evidence in quoted)
            # A new value supplied in a clarification need not be inside the
            # frozen original anchor. It is unambiguous only when this is the
            # sole previously missing slot with that parameter name.
            uniquely_missing = (previous and all(item is not None for item in previous)
                                and clarification_start is not None
                                and sum(item is not None and key not in item.parameters
                                        for item in previous) == 1
                                and goal.instance_id in {
                                    item.instance_id for item in previous
                                    if item is not None and key not in item.parameters
                                }
                                and any(start >= clarification_start for start, _ in quoted))
            if not anchored and not uniquely_missing:
                errors.setdefault(goal.instance_id, []).append("parameter_outside_goal_anchor:" + key)
    return errors


def _resume_drift(previous, current, previous_forbidden, current_forbidden):
    if len(previous) != len(current) or set(previous_forbidden) != set(current_forbidden):
        return True
    for before, after in zip(previous, current):
        if before is None:
            continue
        if (before.capability != after.capability
                or not _same_frozen_quote(before.request_quote, after.request_quote)
                or before.concept_quote != after.concept_quote
                or before.source_stage != after.source_stage
                or any(key not in after.parameters or after.parameters[key] != value
                       for key, value in before.parameters.items())):
            return True
    return False


def _decode_arguments(raw):
    """Repair only one syntactically superfluous final brace, never content."""
    if not isinstance(raw, str):
        return raw, None
    try:
        return json.loads(raw), None
    except json.JSONDecodeError as exc:
        if (exc.msg != "Extra data" or exc.pos != len(raw) - 1
                or not raw.endswith("}")):
            raise
        return json.loads(raw[:-1]), "single_extra_final_brace"


class InstanceGoalEEGAgent:
    """LLM interprets user goals; deterministic graph plans and executes them."""

    def __init__(self, llm_client, context, *, max_tool_calls=20):
        self.llm_client = llm_client
        self.context = context
        self.max_tool_calls = max_tool_calls
        self.pending_request = None
        self._pending_capabilities = None
        self._pending_goals = None
        self._pending_forbidden = None
        self._awaiting_clarification = False

    def run(self, user_request):
        self.pending_request = user_request
        self._pending_capabilities = None
        self._pending_goals = None
        self._pending_forbidden = None
        self._awaiting_clarification = False
        return self._attempt(user_request)

    def resume(self, clarification):
        if self.pending_request is None or not self._awaiting_clarification:
            return _safe_failure("rejected", "NO_PENDING_CLARIFICATION", {})
        return self._attempt(self.pending_request + "\n补充说明：" + clarification)

    def _attempt(self, text):
        if self.context.record.metadata.get("is_synthetic") is not True:
            return _safe_failure("rejected", "EXTERNAL_INTENT_SYNTHETIC_ONLY",
                                 {"message": "Natural-language validation is restricted to synthetic EEG"})
        catalog = capability_catalog(self.context)
        record = self.context.record
        state = {"profile_id": self.context.profile.profile_id,
                 "sfreq": record.sfreq, "duration_seconds": record.duration_seconds,
                 "channel_names": list(record.channel_names),
                 "event_labels": [] if record.events is None else list(record.events.summary()["labels"]),
                 "capabilities": catalog,
                 "capability_status": capability_inventory(self.context)}
        system = (
            "你是 EEG 科学任务编译器。只调用 submit_eeg_goals 一次；列出用户明确要求的所有独立目标，"
            "相同能力的不同参数必须拆成不同 instance_id；不得把内部 create_epochs/list_events 当作用户目标。"
            "每个目标 request_quote 必须是最短的原文连续片段，可只引用窗口片段；不能拼接、省略号或跨越补充说明。"
            "concept_quote 单独引用分析类型的原文证据，"
            "同一句末尾共享的分析概念可被多个实例引用；每个显式参数 parameter_quotes 引用原文连续片段。"
            "若后续目标写'同一事件/同一试次'，参数引文应引用用户先前明确给出的标签/时间原文。"
            "若用户明确要求 raw/processed 数据阶段，填写每目标 source_stage 并在 parameter_quotes"
            " 中引用该阶段原文；否则 source_stage=current。不可编造数据版本。"
            "缺参则省略，绝不从可用通道或事件标签猜测。连续信号与事件 Epoch 功率不能混同；"
            "事件目标参数分别包含 labels/tmin/tmax。否定操作放 forbidden_operations，不可执行。"
            "只有真正不在能力目录里的科学操作才放 unsupported_requests；缺少时间窗/事件标签"
            "不是不支持，仍提交目标但省略缺失参数，由 Harness 合并澄清。不要静默删掉目标。"
            "不得输出诊断、能力评分或原始 EEG。STATE="
            + json.dumps(state, ensure_ascii=False, allow_nan=False)
        )
        try:
            message = self.llm_client.complete(
                [{"role": "system", "content": system}, {"role": "user", "content": text}],
                _intent_tool(catalog),
                tool_choice={"type": "function", "function": {"name": "submit_eeg_goals"}},
            )
            calls = message.get("tool_calls") or []
            if len(calls) != 1 or calls[0].get("function", {}).get("name") != "submit_eeg_goals":
                raise ValueError("Expected exactly one submit_eeg_goals call")
            raw = calls[0]["function"].get("arguments", "{}")
            payload, protocol_repair = _decode_arguments(raw)
            if not isinstance(payload, dict) or not isinstance(payload.get("goals"), list):
                raise ValueError("Goal payload must contain an array")
            goals = tuple(GoalInstance(
                item["instance_id"], item["capability"], item["parameters"],
                item["request_quote"], item["concept_quote"], item["parameter_quotes"],
                source_stage=item.get("source_stage", "current"),
            ) for item in payload["goals"])
            forbidden = payload["forbidden_operations"]
            unsupported = payload["unsupported_requests"]
            if not isinstance(forbidden, list) or not isinstance(unsupported, list):
                raise ValueError("Forbidden and unsupported fields must be arrays")
        except Exception as exc:
            return _safe_failure("intent_error", "INTENT_PARSE_OR_SERVICE_ERROR",
                                 {"error_type": type(exc).__name__})
        if unsupported:
            return _safe_failure("rejected", "UNSUPPORTED_REQUEST_ATOMIC_STOP",
                                 {"unsupported_requests": unsupported},
                                 tuple(f"g{index}" for index in range(1, len(goals) + 1)))
        if not goals or len({goal.instance_id for goal in goals}) != len(goals):
            return _safe_failure("clarification_required", "INVALID_GOAL_SET", {},
                                 tuple(f"g{index}" for index in range(1, len(goals) + 1)))
        capabilities = tuple(goal.capability for goal in goals)
        if self._pending_capabilities is not None and capabilities != self._pending_capabilities:
            return _safe_failure("clarification_required", "GOAL_SET_CHANGED_ON_RESUME",
                                 {"expected_capabilities": self._pending_capabilities,
                                  "observed_capabilities": capabilities},
                                 tuple(f"g{index}" for index in range(1, len(goals) + 1)))
        # Stable task-local identity is assigned by the Harness, not entrusted
        # to a model-generated label that may change after clarification.
        goals = tuple(replace(goal, instance_id=f"g{index}")
                      for index, goal in enumerate(goals, 1))
        if self._pending_goals is not None and _resume_drift(
                self._pending_goals, goals, self._pending_forbidden, forbidden):
            return _safe_failure("clarification_required", "GOAL_SET_CHANGED_ON_RESUME",
                                 {"reason": "Confirmed goal, scope, source or prohibition changed"},
                                 tuple(goal.instance_id for goal in goals))
        errors = {}
        grounded = []
        revised = []
        for goal in goals:
            bad = []
            inherited = {}
            scope_source = None
            if goal.capability not in USER_CAPABILITIES:
                bad.append("unknown_capability")
            if not goal.request_quote or goal.request_quote.casefold() not in text.casefold():
                bad.append("request_quote_not_exact")
            if (not goal.concept_quote or goal.concept_quote.casefold() not in text.casefold()
                    or goal.capability in CAPABILITY_CONCEPTS and not concept_quote_is_grounded(
                        CAPABILITY_CONCEPTS[goal.capability], goal.concept_quote)):
                bad.append("capability_quote_not_grounded")
            if goal.capability in EVENT_CAPABILITIES and not any(
                word in goal.request_quote.casefold() for word in ("事件", "试次", "epoch", "event", "trigger")
            ):
                scope_source = _preceding_equal_event_scope(goal, grounded, text)
                if scope_source is None:
                    bad.append("event_scope_not_grounded")
            for key, value in goal.parameters.items():
                quote = goal.parameter_quotes.get(key)
                if (not isinstance(quote, str) or quote.casefold() not in text.casefold()
                        or not _value_supported_by_quote(value, quote)):
                    # A later "same event" may reference an earlier, fully
                    # grounded goal. The entire Epoch scope must be identical;
                    # a partial match cannot silently substitute conditions.
                    coreference = any(marker in goal.request_quote.casefold()
                                      for marker in ("同一", "相同", "same"))
                    source = next((prior for prior in grounded
                                   if coreference and goal.capability in EVENT_CAPABILITIES
                                   and prior.capability in EVENT_CAPABILITIES
                                   and all(prior.parameters.get(field) == goal.parameters.get(field)
                                           for field in ("labels", "tmin", "tmax", "baseline"))
                                   and key in prior.parameters), None)
                    if source is None:
                        bad.append("ungrounded_parameter:" + key)
                    else:
                        inherited[key] = source.instance_id
            if goal.source_stage != "current":
                quote = goal.parameter_quotes.get("source_stage")
                if (not isinstance(quote, str) or quote.casefold() not in text.casefold()
                        or goal.source_stage.casefold() not in quote.casefold()):
                    bad.append("ungrounded_source_stage")
            if bad:
                errors[goal.instance_id] = bad
            else:
                revised_goal = replace(goal, parameter_sources=inherited,
                                       scope_source=scope_source)
                grounded.append(revised_goal)
                revised.append(revised_goal)
        if errors:
            self._pending_capabilities = capabilities
            self._pending_goals = tuple(next((item for item in revised
                                              if item.instance_id == goal.instance_id), None)
                                        for goal in goals)
            self._pending_forbidden = tuple(forbidden)
            self._awaiting_clarification = True
            return _safe_failure("clarification_required", "UNGROUNDED_GOAL_OR_PARAMETER", errors,
                                 tuple(goal.instance_id for goal in goals))
        ownership_errors = _parameter_ownership_errors(
            revised, text, self._pending_goals or (),
            len(self.pending_request) + len("\n补充说明：") if self._awaiting_clarification else None)
        if ownership_errors:
            self._pending_capabilities = capabilities
            self._pending_goals = tuple(None if goal.instance_id in ownership_errors else goal
                                        for goal in revised)
            self._pending_forbidden = tuple(forbidden)
            self._awaiting_clarification = True
            return _safe_failure("clarification_required", "PARAMETER_GOAL_OWNERSHIP_UNCLEAR",
                                 ownership_errors, tuple(goal.instance_id for goal in goals))
        result = run_instances(self.context, InstanceTaskRequest(tuple(revised), tuple(forbidden)),
                               max_tool_calls=self.max_tool_calls)
        result["protocol_repair"] = protocol_repair
        if result["status"] == "clarification_required":
            self._pending_capabilities = capabilities
            self._pending_goals = tuple(revised)
            self._pending_forbidden = tuple(forbidden)
            self._awaiting_clarification = True
            result["answer"] = "请补充各目标缺失的科学参数：" + json.dumps(result["details"], ensure_ascii=False)
            return result
        if result["status"] != "completed":
            result["answer"] = "科学约束未闭合；未发布不完整分析。"
            return result
        self.pending_request = None
        self._pending_capabilities = None
        self._pending_goals = None
        self._pending_forbidden = None
        self._awaiting_clarification = False
        result["answer"] = "已完成 " + "、".join(
            f"{item['instance_id']}({item['capability']})" for item in result["evidence_bundle"]["goals"]
        ) + "；逐目标数值、单位、来源与限制见 evidence_bundle。仅供研究分析，不能作为诊断或能力评分。"
        return result
