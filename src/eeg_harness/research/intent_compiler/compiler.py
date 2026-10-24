"""Typed claim/evidence compiler layered before the frozen CIEDG runtime.

The language model proposes an IntentSpec.  This module projects that proposal
onto registered scientific requirements, verifies evidence frames and
authorization scope, then computes deterministic prerequisite closure.  It does
not change CIEDG planning, lineage or evidence release.
"""

from dataclasses import replace
import json
import re

from ..integrated_method.intent import (
    EvidenceBoundIntentInterpreter, IntentInterpretation, IntentSpec,
    REQUIRED_SLOTS, _parse_message,
)


FRAME_ROLES = {
    "record_metadata": (("record", "metadata", "信息", "采样率", "通道", "时长"),),
    "time_domain_amplitude": (("amplitude", "peak-to-peak", "幅值", "振幅", "峰峰"),),
    "spectral_power": (("power", "psd", "spectral", "频带", "功率", "频谱"),),
    "event_locked": (("epoch", "event", "trial", "事件", "试次"),),
    "quality_measurement": (("quality", "artifact", "noise", "flagged", "marked", "质量", "伪迹", "噪声", "标记"),),
    "trial_selection": (
        ("remove", "discard", "exclude", "reject", "filter", "drop", "筛", "剔除", "排除", "删除"),
        ("epoch", "trial", "flagged", "marked", "试次"),
    ),
    "epoch_summary": (("count", "how many", "remain", "retained", "试次数", "数量", "保留"),),
    "epoch_rereference": (("re-referenc", "rereferenc", "reference", "重参考", "参考"),),
    "seizure_detection": (("seizure", "epilept", "癫痫", "发作"),),
}

CONCEPT_TO_OBJECTIVE = {
    "quality_measurement": "epoch_quality",
    "trial_selection": "trial_selection",
    "epoch_summary": "epoch_summary",
    "spectral_power": "event_bandpower",
    "epoch_rereference": "epoch_rereference",
}

NEGATED_SELECTION = re.compile(
    r"(?:do not|don't|without|no)(?:\s+[\w-]+){0,4}\s+"
    r"(?:remov\w*|discard\w*|exclud\w*|reject\w*|filter\w*|drop\w*)|"
    r"(?:keep|retain)\s+(?:every|all)|(?:不要|不授权|禁止|不得).{0,12}(?:筛|剔除|排除|删除)",
    re.IGNORECASE,
)
NEGATED_REREFERENCE = re.compile(
    r"(?:do not|don't|without|no)\s+(?:re-reference|rereference)|"
    r"(?:不要|不授权|禁止|不得).{0,12}重参考",
    re.IGNORECASE,
)


def _exact_span(request, quote):
    return isinstance(quote, str) and bool(quote.strip()) and quote.casefold() in request.casefold()


def _frame_matches(concept, quote):
    if concept not in FRAME_ROLES or not isinstance(quote, str):
        return False
    folded = quote.casefold()
    return all(any(token.casefold() in folded for token in role) for role in FRAME_ROLES[concept])


def _numbers(text):
    return [float(value.replace("−", "-")) for value in re.findall(r"[-+−]?\d+(?:\.\d+)?", text)]


def _value_is_grounded(value, quote):
    if not isinstance(quote, str):
        return False
    folded = quote.casefold()
    if isinstance(value, bool):
        return True
    if isinstance(value, str):
        return value.casefold() in folded
    if isinstance(value, (list, tuple)):
        return all(isinstance(item, str) and item.casefold() in folded for item in value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return any(abs(float(value) - candidate) <= 1e-9 for candidate in _numbers(quote))
    return False


def _same_sentence_scope(request, operation_quote, authorization_quote):
    if not (_exact_span(request, operation_quote) and _exact_span(request, authorization_quote)):
        return False
    folded = request.casefold()
    operation_at = folded.find(operation_quote.casefold())
    authorization_at = folded.find(authorization_quote.casefold())
    lo = min(operation_at, authorization_at)
    hi = max(operation_at + len(operation_quote), authorization_at + len(authorization_quote))
    segment = request[lo:hi]
    return hi - lo <= 180 and not re.search(r"[。！？!?;]\s*", segment)


def _canonical_forbidden(request):
    forbidden = []
    if NEGATED_SELECTION.search(request):
        forbidden.append("trial_selection")
    if NEGATED_REREFERENCE.search(request):
        forbidden.append("epoch_rereference")
    return tuple(forbidden)


def validate_intent_v1(intent: IntentSpec, user_request, context):
    """Return interpretation plus auditable compiler diagnostics."""
    diagnostics = {
        "compiler": "typed_claim_evidence_requirement_projection_v1",
        "verified_concepts": [], "unverified_concepts": {},
        "ignored_unknown_slots": [], "required_unknown_slots": [],
        "derived_objectives": [], "authorization_checks": {},
    }
    if intent.analysis_type == "unsupported":
        return IntentInterpretation(
            True, intent, "reject", error_code="UNSUPPORTED_ANALYSIS",
            error_message="The requested analysis is outside registered EEG capabilities.",
        ), diagnostics

    canonical_forbidden = _canonical_forbidden(user_request)
    normalized = replace(intent, forbidden_operations=canonical_forbidden)
    if "epoch_rereference" in intent.objectives and re.search(
        r"重参考(?:前|之前)|重新参考前|before\s+(?:re-reference|rereference)",
        user_request, re.IGNORECASE,
    ):
        return IntentInterpretation(
            True, normalized, "clarify", ("analysis_stage",),
            "MIXED_TRANSFORM_SCOPE_UNSUPPORTED",
            "Pre-transform and post-transform evidence need separate observable branches.",
        ), diagnostics

    verified = set()
    for concept, quote in intent.semantic_evidence.items():
        if not _exact_span(user_request, quote):
            diagnostics["unverified_concepts"][concept] = "non_exact_span"
        elif not _frame_matches(concept, quote):
            diagnostics["unverified_concepts"][concept] = "role_frame_not_satisfied"
        else:
            verified.add(concept)
    diagnostics["verified_concepts"] = sorted(verified)

    expected_type = None
    if "event_locked" in verified:
        expected_type = "event_workflow"
    else:
        for concept, analysis in (
            ("record_metadata", "record_info"),
            ("time_domain_amplitude", "amplitude"),
            ("spectral_power", "psd"),
            ("quality_measurement", "record_quality"),
            ("seizure_detection", "seizure_detection"),
        ):
            if concept in verified:
                expected_type = analysis
                break
    if expected_type != intent.analysis_type:
        return IntentInterpretation(
            True, normalized, "clarify", ("analysis_type",),
            "INTENT_TYPE_MISMATCH",
            "The typed analysis is not supported by a grounded scientific claim frame.",
        ), diagnostics

    if intent.analysis_type == "event_workflow":
        expected = {CONCEPT_TO_OBJECTIVE[c] for c in verified if c in CONCEPT_TO_OBJECTIVE}
        if "trial_selection" in expected:
            expected.add("epoch_quality")
            if "quality_measurement" not in verified:
                diagnostics["derived_objectives"].append("epoch_quality")
        expected -= set(canonical_forbidden)
        if set(intent.objectives) != expected:
            return IntentInterpretation(
                True, normalized, "clarify", ("objectives",),
                "INTENT_OBJECTIVE_MISMATCH",
                "Requested EEG objectives do not equal grounded goals plus scientific prerequisites.",
            ), diagnostics

    required = list(REQUIRED_SLOTS[intent.analysis_type])
    if "trial_selection" in intent.objectives:
        required.append("selection_authorized")
    if "epoch_rereference" in intent.objectives:
        required.extend(("reference_channels", "rereference_authorized"))
    diagnostics["ignored_unknown_slots"] = sorted(set(intent.unknown_slots) - set(required))
    diagnostics["required_unknown_slots"] = sorted(set(intent.unknown_slots) & set(required))

    bad_slots = []
    for slot in required:
        value = intent.parameters.get(slot)
        quote = intent.explicit_evidence.get(slot)
        missing = value in (None, "", []) or not _exact_span(user_request, quote)
        if slot in {"selection_authorized", "rereference_authorized"}:
            missing = value is not True or not _exact_span(user_request, quote)
        elif not missing and not _value_is_grounded(value, quote):
            missing = True
        if missing or slot in diagnostics["required_unknown_slots"]:
            bad_slots.append(slot)

    for objective, auth_slot, concept, forbidden in (
        ("trial_selection", "selection_authorized", "trial_selection", "trial_selection"),
        ("epoch_rereference", "rereference_authorized", "epoch_rereference", "epoch_rereference"),
    ):
        if objective not in intent.objectives:
            continue
        operation_quote = intent.semantic_evidence.get(concept)
        auth_quote = intent.explicit_evidence.get(auth_slot)
        safe = (
            concept in verified and intent.parameters.get(auth_slot) is True
            and _same_sentence_scope(user_request, operation_quote, auth_quote)
            and forbidden not in canonical_forbidden
        )
        diagnostics["authorization_checks"][objective] = {
            "valid": safe, "operation_span_exact": _exact_span(user_request, operation_quote),
            "authorization_span_exact": _exact_span(user_request, auth_quote),
            "same_sentence_scope": _same_sentence_scope(user_request, operation_quote, auth_quote),
        }
        if not safe:
            bad_slots.append(auth_slot)

    if bad_slots:
        ordered = tuple(dict.fromkeys(bad_slots))
        return IntentInterpretation(
            True, normalized, "clarify", ordered,
            "MISSING_OR_UNGROUNDED_INTENT_SLOT",
            "Required EEG slots or scoped transformation authorization are missing.",
        ), diagnostics

    if intent.source_stage in {"raw", "processed"}:
        quote = intent.explicit_evidence.get("source_stage")
        if not _exact_span(user_request, quote):
            return IntentInterpretation(
                True, normalized, "clarify", ("source_stage",),
                "UNGROUNDED_SOURCE_STAGE", "Requested source stage lacks exact evidence.",
            ), diagnostics
    actual_stage = context.record.metadata.get("source_stage", "current")
    if intent.source_stage == "raw" and actual_stage != "raw":
        return IntentInterpretation(
            True, normalized, "reject", error_code="SOURCE_STAGE_UNOBSERVABLE",
            error_message="The current record does not expose a raw signal branch.",
        ), diagnostics
    return IntentInterpretation(True, normalized, "execute"), diagnostics


class _CaptureClient:
    def __init__(self, delegate):
        self.delegate = delegate
        self.response = None

    def complete(self, *args, **kwargs):
        self.response = self.delegate.complete(*args, **kwargs)
        return self.response


class IntentCompilerV1Interpreter:
    """Reuse the exact v0 extraction prompt, replace only post-decode compilation."""

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.last_raw_intent = None
        self.last_diagnostics = None
        self.last_v0_interpretation = None

    def interpret(self, user_request, context):
        capture = _CaptureClient(self.llm_client)
        self.last_v0_interpretation = EvidenceBoundIntentInterpreter(capture).interpret(
            user_request, context)
        if capture.response is None:
            return self.last_v0_interpretation
        try:
            self.last_raw_intent = _parse_message(capture.response)
            decision, diagnostics = validate_intent_v1(
                self.last_raw_intent, user_request, context)
            self.last_diagnostics = diagnostics
            return decision
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            return IntentInterpretation(
                False, disposition="error", error_code="INTENT_PARSE_ERROR",
                error_message=str(exc),
            )
