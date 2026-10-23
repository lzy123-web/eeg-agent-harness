"""Evidence-bound natural-language intent for the integrated Point-1 method."""

from dataclasses import dataclass, field
import json
import math
import re
from typing import Any, Mapping, Optional

from .semantics import (
    ANALYSIS_SEMANTIC_CONTRACTS, CONCEPT_ANCHORS,
    concept_quote_is_grounded, resolve_analysis_type, resolve_event_objectives,
)


SUPPORTED_ANALYSES = frozenset({
    "record_info", "amplitude", "psd", "event_workflow", "record_quality",
    "seizure_detection", "unsupported",
})

REQUIRED_SLOTS = {
    "record_info": (),
    "record_quality": (),
    "amplitude": ("channels", "start", "end"),
    "psd": ("channels", "start", "end"),
    "seizure_detection": ("channels", "start", "end"),
    "event_workflow": ("labels", "tmin", "tmax"),
    "unsupported": (),
}


@dataclass(frozen=True)
class IntentSpec:
    analysis_type: str
    objectives: tuple[str, ...] = ()
    parameters: Mapping[str, Any] = field(default_factory=dict)
    explicit_evidence: Mapping[str, str] = field(default_factory=dict)
    semantic_evidence: Mapping[str, str] = field(default_factory=dict)
    unknown_slots: tuple[str, ...] = ()
    forbidden_operations: tuple[str, ...] = ()
    source_stage: str = "current"
    output_boundary: str = "research_only"
    rationale: str = ""

    def to_dict(self):
        payload = {
            "analysis_type": self.analysis_type,
            "objectives": list(self.objectives),
            "parameters": dict(self.parameters),
            "explicit_evidence": dict(self.explicit_evidence),
            "semantic_evidence": dict(self.semantic_evidence),
            "unknown_slots": list(self.unknown_slots),
            "forbidden_operations": list(self.forbidden_operations),
            "source_stage": self.source_stage,
            "output_boundary": self.output_boundary,
            "rationale": self.rationale,
        }
        json.dumps(payload, ensure_ascii=False, allow_nan=False)
        return payload


@dataclass(frozen=True)
class IntentInterpretation:
    success: bool
    intent: Optional[IntentSpec] = None
    disposition: str = "execute"
    missing_slots: tuple[str, ...] = ()
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self):
        return {
            "success": self.success,
            "disposition": self.disposition,
            "intent": None if self.intent is None else self.intent.to_dict(),
            "missing_slots": list(self.missing_slots),
            "error": None if self.error_code is None else {
                "code": self.error_code, "message": self.error_message,
            },
        }


INTENT_TOOL = [{
    "type": "function",
    "function": {
        "name": "submit_eeg_intent",
        "description": (
            "Submit one EEG intent. Every explicit slot must cite an exact substring "
            "from the user request; unsupported or unknown values must not be guessed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "analysis_type": {"type": "string", "enum": sorted(SUPPORTED_ANALYSES)},
                "objectives": {
                    "type": "array",
                    "description": (
                        "Positive atomic event objectives only: epoch_quality, trial_selection, "
                        "epoch_summary, event_bandpower. Negated operations belong only in "
                        "forbidden_operations."
                    ),
                    "items": {
                        "type": "string",
                        "enum": [
                            "epoch_quality", "trial_selection", "epoch_summary", "event_bandpower",
                        ],
                    },
                },
                "parameters": {
                    "type": "object",
                    "description": (
                        "Use only these canonical slot names. Continuous windows use "
                        "channels/start/end. Event windows use labels/tmin/tmax."
                    ),
                    "properties": {
                        "channels": {"type": "array", "items": {"type": "string"}},
                        "start": {"type": "number"},
                        "end": {"type": "number"},
                        "labels": {"type": "array", "items": {"type": "string"}},
                        "tmin": {"type": "number"},
                        "tmax": {"type": "number"},
                        "selection_authorized": {"type": "boolean"},
                    },
                    "additionalProperties": False,
                },
                "explicit_evidence": {"type": "object", "additionalProperties": {"type": "string"}},
                "semantic_evidence": {
                    "type": "object",
                    "description": (
                        "Map every requested scientific operation concept to an exact user span. "
                        "The concept set is resolved independently into one analysis capability."
                    ),
                    "properties": {
                        name: {"type": "string"} for name in sorted(CONCEPT_ANCHORS)
                    },
                    "additionalProperties": False,
                },
                "unknown_slots": {"type": "array", "items": {"type": "string"}},
                "forbidden_operations": {"type": "array", "items": {"type": "string"}},
                "source_stage": {"type": "string", "enum": ["current", "raw", "processed", "unknown"]},
                "output_boundary": {"type": "string"},
                "rationale": {"type": "string"}
            },
            "required": [
                "analysis_type", "objectives", "parameters", "explicit_evidence", "semantic_evidence", "unknown_slots",
                "forbidden_operations", "source_stage", "output_boundary", "rationale"
            ],
            "additionalProperties": False
        }
    }
}]


def _state(context):
    labels = {}
    if context.record.events is not None:
        labels = context.record.events.summary().get("labels", {})
    source_stage = context.record.metadata.get("source_stage", "current")
    return {
        "profile_id": context.profile.profile_id,
        "sfreq": context.record.sfreq,
        "duration_seconds": context.record.duration_seconds,
        "channel_names": list(context.record.channel_names),
        "event_labels": labels,
        "source_stage": source_stage,
        "processing_operations": [
            item.get("operation", "unknown") for item in context.record.processing_metadata
        ],
        "available_analyses": sorted(SUPPORTED_ANALYSES - {"unsupported"}),
    }


def _parse_message(message):
    calls = message.get("tool_calls") or []
    if len(calls) != 1 or calls[0].get("function", {}).get("name") != "submit_eeg_intent":
        raise ValueError("Intent model must submit exactly one submit_eeg_intent call")
    raw = calls[0]["function"].get("arguments", "{}")
    payload = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(payload, dict):
        raise ValueError("Intent payload must be an object")
    analysis = payload.get("analysis_type")
    if analysis not in SUPPORTED_ANALYSES:
        raise ValueError("Intent analysis_type is unsupported")
    parameters = payload.get("parameters")
    objectives = payload.get("objectives")
    evidence = payload.get("explicit_evidence")
    semantic_evidence = payload.get("semantic_evidence")
    unknown = payload.get("unknown_slots")
    forbidden = payload.get("forbidden_operations")
    if not isinstance(objectives, list) or not all(isinstance(item, str) for item in objectives):
        raise ValueError("Intent objectives must be a string array")
    if len(objectives) != len(set(objectives)):
        raise ValueError("Intent objectives must not contain duplicates")
    if not all(isinstance(item, dict) for item in (parameters, evidence, semantic_evidence)):
        raise ValueError("Intent parameters and evidence fields must be objects")
    if not isinstance(unknown, list) or not all(isinstance(item, str) for item in unknown):
        raise ValueError("Intent unknown_slots must be a string array")
    if not isinstance(forbidden, list) or not all(isinstance(item, str) for item in forbidden):
        raise ValueError("Intent forbidden_operations must be a string array")
    return IntentSpec(
        analysis_type=analysis,
        objectives=tuple(objectives),
        parameters=parameters,
        explicit_evidence=evidence,
        semantic_evidence=semantic_evidence,
        unknown_slots=tuple(unknown),
        forbidden_operations=tuple(forbidden),
        source_stage=payload.get("source_stage", "current"),
        output_boundary=payload.get("output_boundary", "research_only"),
        rationale=payload.get("rationale", ""),
    )


def _evidence_is_exact(user_request, quote):
    return isinstance(quote, str) and bool(quote.strip()) and quote.casefold() in user_request.casefold()


def _value_supported_by_quote(value, quote):
    folded = quote.casefold()
    if isinstance(value, str):
        return value.casefold() in folded
    if isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
        return all(item.casefold() in folded for item in value)
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(float(value)):
            return False
        numbers = re.findall(r"[-+−]?\d+(?:\.\d+)?", quote)
        normalized = [float(item.replace("−", "-")) for item in numbers]
        return any(math.isclose(float(value), item, rel_tol=0.0, abs_tol=1e-9) for item in normalized)
    return value is not None


def validate_intent(intent, user_request, context):
    """Fail closed on unsupported, uncited, unknown, or unobservable intent slots."""
    if intent.analysis_type == "unsupported":
        return IntentInterpretation(
            True, intent, "reject", error_code="UNSUPPORTED_ANALYSIS",
            error_message="The requested analysis is outside the registered EEG capabilities.",
        )
    semantic_failures = []
    for concept, quote in intent.semantic_evidence.items():
        if not _evidence_is_exact(user_request, quote):
            semantic_failures.append(f"non_exact:{concept}")
        elif not concept_quote_is_grounded(concept, quote):
            semantic_failures.append(f"ungrounded:{concept}")
    resolved_analysis = resolve_analysis_type(intent.semantic_evidence)
    expected_contract = ANALYSIS_SEMANTIC_CONTRACTS.get(intent.analysis_type)
    if (
        semantic_failures or expected_contract is None
        or not expected_contract.matches(intent.semantic_evidence)
        or resolved_analysis != intent.analysis_type
    ):
        return IntentInterpretation(
            True, intent, "clarify", ("analysis_type",),
            "INTENT_TYPE_MISMATCH",
            "The declared analysis does not match independently grounded request semantics.",
        )
    bad_evidence = []
    for slot, quote in intent.explicit_evidence.items():
        if not _evidence_is_exact(user_request, quote):
            bad_evidence.append(slot)
            continue
        if slot in intent.parameters and not _value_supported_by_quote(intent.parameters[slot], quote):
            bad_evidence.append(slot)
    expected_objectives = (
        resolve_event_objectives(intent.semantic_evidence, intent.forbidden_operations)
        if intent.analysis_type == "event_workflow" else ()
    )
    if set(intent.objectives) != set(expected_objectives) or (
        intent.analysis_type == "event_workflow" and not intent.objectives
    ):
        return IntentInterpretation(
            True, intent, "clarify", ("objectives",),
            "INTENT_OBJECTIVE_MISMATCH",
            "Positive event objectives do not match grounded concepts and prohibitions.",
        )
    required = list(REQUIRED_SLOTS[intent.analysis_type])
    if "trial_selection" in intent.objectives:
        required.append("selection_authorized")
    missing = []
    for slot in required:
        value = intent.parameters.get(slot)
        if slot == "selection_authorized":
            missing_slot = value is not True or slot not in intent.explicit_evidence
        else:
            missing_slot = value in (None, "", []) or slot not in intent.explicit_evidence
        if missing_slot or slot in intent.unknown_slots or slot in bad_evidence:
            missing.append(slot)
    if missing:
        return IntentInterpretation(
            True, intent, "clarify", tuple(dict.fromkeys(missing)),
            "MISSING_OR_UNGROUNDED_INTENT_SLOT",
            "Required EEG intent slots are unknown or lack exact user-language evidence.",
        )
    if intent.source_stage in {"raw", "processed"}:
        quote = intent.explicit_evidence.get("source_stage")
        if not _evidence_is_exact(user_request, quote):
            return IntentInterpretation(
                True, intent, "clarify", ("source_stage",),
                "UNGROUNDED_SOURCE_STAGE", "Requested source stage lacks user-language evidence.",
            )
    actual_stage = context.record.metadata.get("source_stage", "current")
    if intent.source_stage == "raw" and actual_stage != "raw":
        return IntentInterpretation(
            True, intent, "reject", error_code="SOURCE_STAGE_UNOBSERVABLE",
            error_message=(
                "The current EEGRecord does not explicitly expose a raw signal branch; "
                "raw-source evidence is unobservable."
            ),
        )
    return IntentInterpretation(True, intent, "execute")


class EvidenceBoundIntentInterpreter:
    def __init__(self, llm_client):
        self.llm_client = llm_client

    def interpret(self, user_request, context):
        system = (
            "你是 EEG 科学意图编译器。只提交一个 submit_eeg_intent。parameters 中每个"
            "显式科学 slot 必须在 explicit_evidence 中引用用户原文的精确连续片段；不能用"
            "记录里已有的通道或事件标签替用户补全。缺失值放入 unknown_slots。事件绝对频带"
            "功率不是 ERP/ERD-ERS；临床诊断和未注册分析标为 unsupported。选择或筛除试次"
            "只有用户明确授权时 selection_authorized=true。普通连续时间窗频带功率使用"
            "analysis_type=psd 和 channels/start/end。明确提到事件、试次或 epoch 时使用"
            "analysis_type=event_workflow 和 labels/tmin/tmax，并把正向目标拆成 objectives："
            "epoch_quality、trial_selection、epoch_summary、event_bandpower。参数键和证据键必须"
            "完全相同。不要创建 channel、event_label、window_start_seconds、power_type 等别名。"
            "semantic_evidence 必须列出用户真正要求的全部科学操作概念，并为每个概念引用"
            "用户原文精确片段；analysis_type 必须与概念组合一致，不能只根据参数形状猜测。"
            "否定的操作只放 forbidden_operations，不得放入正向 objectives；例如测量质量、"
            "禁止筛选、随后计算功率的 objectives 是 epoch_quality+event_bandpower。STATE="
            + json.dumps(_state(context), ensure_ascii=False, allow_nan=False)
        )
        try:
            message = self.llm_client.complete(
                [{"role": "system", "content": system}, {"role": "user", "content": user_request}],
                INTENT_TOOL,
                tool_choice={"type": "function", "function": {"name": "submit_eeg_intent"}},
            )
            intent = _parse_message(message)
            return validate_intent(intent, user_request, context)
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return IntentInterpretation(
                False, disposition="error", error_code="INTENT_PARSE_ERROR",
                error_message=str(exc),
            )
        except Exception:
            return IntentInterpretation(
                False, disposition="error", error_code="LLM_ERROR",
                error_message="Intent model failed without exposing internal traceback.",
            )
