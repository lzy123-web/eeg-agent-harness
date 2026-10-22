"""Evidence-bound natural-language intent for the integrated Point-1 method."""

from dataclasses import dataclass, field
import json
import math
import re
from typing import Any, Mapping, Optional


SUPPORTED_ANALYSES = frozenset({
    "record_info", "amplitude", "psd", "event_bandpower", "epoch_quality",
    "quality_selection", "record_quality", "seizure_detection", "unsupported",
})

REQUIRED_SLOTS = {
    "record_info": (),
    "record_quality": (),
    "amplitude": ("channels", "start", "end"),
    "psd": ("channels", "start", "end"),
    "seizure_detection": ("channels", "start", "end"),
    "event_bandpower": ("labels", "tmin", "tmax"),
    "epoch_quality": ("labels", "tmin", "tmax"),
    "quality_selection": ("labels", "tmin", "tmax", "selection_authorized"),
    "unsupported": (),
}


@dataclass(frozen=True)
class IntentSpec:
    analysis_type: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    explicit_evidence: Mapping[str, str] = field(default_factory=dict)
    unknown_slots: tuple[str, ...] = ()
    forbidden_operations: tuple[str, ...] = ()
    source_stage: str = "current"
    output_boundary: str = "research_only"
    rationale: str = ""

    def to_dict(self):
        payload = {
            "analysis_type": self.analysis_type,
            "parameters": dict(self.parameters),
            "explicit_evidence": dict(self.explicit_evidence),
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
                "unknown_slots": {"type": "array", "items": {"type": "string"}},
                "forbidden_operations": {"type": "array", "items": {"type": "string"}},
                "source_stage": {"type": "string", "enum": ["current", "raw", "processed", "unknown"]},
                "output_boundary": {"type": "string"},
                "rationale": {"type": "string"}
            },
            "required": [
                "analysis_type", "parameters", "explicit_evidence", "unknown_slots",
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
    evidence = payload.get("explicit_evidence")
    unknown = payload.get("unknown_slots")
    forbidden = payload.get("forbidden_operations")
    if not isinstance(parameters, dict) or not isinstance(evidence, dict):
        raise ValueError("Intent parameters and explicit_evidence must be objects")
    if not isinstance(unknown, list) or not all(isinstance(item, str) for item in unknown):
        raise ValueError("Intent unknown_slots must be a string array")
    if not isinstance(forbidden, list) or not all(isinstance(item, str) for item in forbidden):
        raise ValueError("Intent forbidden_operations must be a string array")
    return IntentSpec(
        analysis_type=analysis,
        parameters=parameters,
        explicit_evidence=evidence,
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
    bad_evidence = []
    for slot, quote in intent.explicit_evidence.items():
        if not _evidence_is_exact(user_request, quote):
            bad_evidence.append(slot)
            continue
        if slot in intent.parameters and not _value_supported_by_quote(intent.parameters[slot], quote):
            bad_evidence.append(slot)
    required = REQUIRED_SLOTS[intent.analysis_type]
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
            "只有用户明确授权时 selection_authorized=true。严格使用以下映射：普通连续时间窗"
            "频带功率是 analysis_type=psd，参数只能是 channels/start/end；只有用户明确提到事件"
            "或 epoch 时才是 event_bandpower，参数只能是 labels/tmin/tmax；参数键和证据键必须"
            "完全相同。不要创建 channel、event_label、window_start_seconds、power_type 等别名。STATE="
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
