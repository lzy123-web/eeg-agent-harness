"""Deterministic controlled-language protocol for Issue #21.

Gold contracts are defined before text rendering. The renderer and controlled
parser use a closed grammar; neither calls an LLM. This validates a limited
grammar and typed matcher, not free natural-language understanding.
"""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .models import ScientificClaim, ScientificContract, SUPPORTED_OPERATIONS


PROTOCOL_PATH = Path("config/eeg_goal_completeness_cases_v1.json")
FROZEN_PROTOCOL_SHA256 = "94111eb7a025c0fc7bb4780e53d894cac2d5833c8c21f4ac613b9b073541381a"
SEED = 21021

FAMILY_META = {
    "dev_en_direct": ("development", "en", "; "),
    "dev_zh_direct": ("development", "zh", "；"),
    "holdout_en_sequence": ("holdout", "en", "; "),
    "holdout_zh_sequence": ("holdout", "zh", "；"),
}


def _claim(
    operation: str,
    stage: str = "source_epochs",
    *,
    polarity: str = "required",
    authorization: str = "not_required",
    output_stage: str | None = None,
    parameters: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if parameters is None and operation == "trial_selection":
        parameters = {"criterion": "quality_flagged"}
    if parameters is None and operation == "epoch_rereference":
        parameters = {"reference_channels": ["SYNTH-C2"]}
    if output_stage is None and operation not in {"trial_selection", "epoch_rereference"}:
        output_stage = stage
    if operation in {"trial_selection", "epoch_rereference"} and polarity == "required":
        output_stage = "effective_epochs"
    return {
        "operation": operation,
        "input_stage": stage,
        "output_stage": output_stage,
        "polarity": polarity,
        "authorization": authorization,
        "parameters": dict(parameters or {}),
    }


PROTOTYPES = (
    # Development families use direct imperative wording.
    {"id": "GD01", "family": "dev_en_direct", "claims": [_claim("epoch_quality")],
     "fault": ("omit_operation", "epoch_quality")},
    {"id": "GD02", "family": "dev_zh_direct", "claims": [
        _claim("epoch_quality"), _claim("event_bandpower")],
     "fault": ("relation_missing", None)},
    {"id": "GD03", "family": "dev_en_direct", "claims": [
        _claim("epoch_quality"),
        _claim("trial_selection", polarity="forbidden", authorization="denied"),
        _claim("event_bandpower")],
     "fault": ("authorization_conflict", "trial_selection")},
    {"id": "GD04", "family": "dev_zh_direct", "claims": [
        _claim("epoch_quality"),
        _claim("trial_selection", authorization="granted",
               parameters={"criterion": "quality_flagged"}),
        _claim("epoch_summary", "effective_epochs")],
     "fault": ("omit_operation", "trial_selection")},
    {"id": "GD05", "family": "dev_en_direct", "target": "control", "claims": [
        _claim("epoch_quality"),
        _claim("trial_selection", authorization="granted",
               parameters={"criterion": "quality_flagged"}),
        _claim("event_bandpower", "effective_epochs")],
     "fault": ("stage_conflict", "event_bandpower")},
    {"id": "GD06", "family": "dev_zh_direct", "claims": [
        _claim("epoch_rereference", authorization="granted",
               parameters={"reference_channels": ["SYNTH-C2"]}),
        _claim("epoch_quality", "effective_epochs"),
        _claim("event_bandpower", "effective_epochs")],
     "fault": ("authorization_conflict", "epoch_rereference")},
    {"id": "GD07", "family": "dev_en_direct", "claims": [
        _claim("epoch_quality"),
        _claim("epoch_rereference", authorization="granted",
               parameters={"reference_channels": ["SYNTH-C2"]}),
        _claim("event_bandpower", "effective_epochs")],
     "fault": ("relation_missing", None)},
    {"id": "GD08", "family": "dev_zh_direct", "claims": [
        _claim("epoch_rereference", authorization="unspecified",
               parameters={"reference_channels": ["SYNTH-C2"]}),
        _claim("event_bandpower", "effective_epochs")],
     "fault": ("authorization_conflict", "epoch_rereference")},
    {"id": "GD09", "family": "dev_en_direct", "claims": [
        _claim("epoch_rereference", polarity="forbidden", authorization="denied",
               parameters={"reference_channels": ["SYNTH-C2"]}),
        _claim("epoch_quality")],
     "fault": ("omit_operation", "epoch_rereference")},
    {"id": "GD10", "family": "dev_zh_direct", "claims": [_claim("erd_ers")],
     "fault": ("extra_operation", "epoch_quality")},
    {"id": "GD11", "family": "dev_en_direct", "claims": [
        _claim("epoch_quality"),
        _claim("trial_selection", authorization="unspecified",
               parameters={"criterion": "quality_flagged"}),
        _claim("epoch_summary", "effective_epochs")],
     "fault": ("authorization_conflict", "trial_selection")},
    {"id": "GD12", "family": "dev_zh_direct", "target": "control", "tmin": -0.2,
     "tmax": 0.8, "claims": [
        _claim("epoch_quality"),
        _claim("trial_selection", authorization="granted",
               parameters={"criterion": "quality_flagged"}),
        _claim("epoch_summary", "effective_epochs"),
        _claim("event_bandpower", "effective_epochs")],
     "fault": ("extra_operation", "epoch_rereference")},

    # Holdout uses disjoint surface template families and different contracts.
    {"id": "GH01", "family": "holdout_en_sequence", "claims": [_claim("event_bandpower")],
     "fault": ("stage_conflict", "event_bandpower")},
    {"id": "GH02", "family": "holdout_zh_sequence", "claims": [
        _claim("epoch_quality"), _claim("epoch_summary")],
     "fault": ("omit_operation", "epoch_summary")},
    {"id": "GH03", "family": "holdout_en_sequence", "target": "control", "claims": [
        _claim("trial_selection", polarity="forbidden", authorization="denied"),
        _claim("epoch_summary"), _claim("event_bandpower")],
     "fault": ("authorization_conflict", "trial_selection")},
    {"id": "GH04", "family": "holdout_zh_sequence", "claims": [
        _claim("epoch_quality"),
        _claim("trial_selection", authorization="granted",
               parameters={"criterion": "quality_flagged"}),
        _claim("epoch_summary", "effective_epochs"),
        _claim("event_bandpower", "effective_epochs")],
     "fault": ("relation_missing", None)},
    {"id": "GH05", "family": "holdout_en_sequence", "target": "control", "claims": [
        _claim("epoch_quality"),
        _claim("trial_selection", authorization="granted",
               parameters={"criterion": "quality_flagged"}),
        _claim("event_bandpower", "effective_epochs")],
     "fault": ("omit_operation", "event_bandpower")},
    {"id": "GH06", "family": "holdout_zh_sequence", "claims": [
        _claim("epoch_rereference", authorization="granted",
               parameters={"reference_channels": ["SYNTH-C2"]}),
        _claim("epoch_summary", "effective_epochs"),
        _claim("event_bandpower", "effective_epochs")],
     "fault": ("stage_conflict", "epoch_summary")},
    {"id": "GH07", "family": "holdout_en_sequence", "claims": [
        _claim("event_bandpower"), _claim("epoch_quality"),
        _claim("trial_selection", authorization="granted",
               parameters={"criterion": "quality_flagged"}),
        _claim("epoch_summary", "effective_epochs")],
     "fault": ("relation_missing", None)},
    {"id": "GH08", "family": "holdout_zh_sequence", "claims": [
        _claim("epoch_rereference", authorization="unspecified",
               parameters={"reference_channels": ["SYNTH-C2"]}),
        _claim("epoch_quality", "effective_epochs")],
     "fault": ("authorization_conflict", "epoch_rereference")},
    {"id": "GH09", "family": "holdout_en_sequence", "claims": [
        _claim("epoch_rereference", polarity="forbidden", authorization="denied",
               parameters={"reference_channels": ["SYNTH-C2"]}),
        _claim("event_bandpower")],
     "fault": ("omit_operation", "epoch_rereference")},
    {"id": "GH10", "family": "holdout_zh_sequence", "claims": [
        _claim("functional_connectivity")],
     "fault": ("extra_operation", "epoch_quality")},
    {"id": "GH11", "family": "holdout_en_sequence", "target": "control", "claims": [
        _claim("epoch_quality"),
        _claim("trial_selection", authorization="unspecified",
               parameters={"criterion": "quality_flagged"}),
        _claim("event_bandpower", "effective_epochs")],
     "fault": ("authorization_conflict", "trial_selection")},
    {"id": "GH12", "family": "holdout_zh_sequence", "target": "control", "tmin": -0.1,
     "tmax": 0.9, "claims": [
        _claim("epoch_rereference", authorization="granted",
               parameters={"reference_channels": ["SYNTH-C2"]}),
        _claim("epoch_quality", "effective_epochs"),
        _claim("epoch_summary", "effective_epochs"),
        _claim("event_bandpower", "effective_epochs")],
     "fault": ("extra_operation", "trial_selection")},
)


def _stage_text(stage: str, language: str, variant: str) -> str:
    if language == "en":
        if variant == "direct":
            return "source epochs" if stage == "source_epochs" else "effective epochs"
        return "untouched epochs" if stage == "source_epochs" else "resulting epochs"
    if variant == "direct":
        return "源 Epoch" if stage == "source_epochs" else "有效 Epoch"
    return "未转换 Epoch" if stage == "source_epochs" else "转换后 Epoch"


def _render_claim(claim: ScientificClaim, family: str) -> str:
    language = FAMILY_META[family][1]
    variant = "direct" if family.startswith("dev_") else "sequence"
    stage = _stage_text(claim.input_stage, language, variant)
    op = claim.operation
    if language == "en":
        if op == "epoch_quality":
            return (f"measure epoch quality on {stage}" if variant == "direct"
                    else f"assess epoch quality using {stage}")
        if op == "epoch_summary":
            return (f"report the trial count on {stage}" if variant == "direct"
                    else f"state the retained trial count from {stage}")
        if op == "event_bandpower":
            return (f"compute absolute band power on {stage}" if variant == "direct"
                    else f"obtain absolute band power from {stage}")
        if op == "trial_selection":
            if claim.polarity == "forbidden":
                return ("do not remove any trial from source epochs" if variant == "direct"
                        else "keep every trial in the untouched epochs")
            if claim.authorization == "granted":
                return ("with explicit authorization, remove quality-flagged trials from source epochs"
                        if variant == "direct" else
                        "I explicitly permit dropping quality-flagged trials from the untouched epochs")
            return ("request removal of quality-flagged trials without granting authorization"
                    if variant == "direct" else
                    "consider dropping quality-flagged trials, but no permission is granted")
        if op == "epoch_rereference":
            if claim.polarity == "forbidden":
                return ("do not re-reference source epochs to SYNTH-C2" if variant == "direct"
                        else "keep the untouched reference and forbid changing it to SYNTH-C2")
            if claim.authorization == "granted":
                return ("with explicit authorization, re-reference source epochs to SYNTH-C2"
                        if variant == "direct" else
                        "I explicitly permit changing the untouched epochs to reference SYNTH-C2")
            return ("request re-referencing source epochs to SYNTH-C2 without granting authorization"
                    if variant == "direct" else
                    "consider reference SYNTH-C2, but no permission to change the epochs is granted")
        if op == "erd_ers":
            return "compute ERD/ERS on source epochs"
        if op == "functional_connectivity":
            return "compute functional connectivity on untouched epochs"
    else:
        if op == "epoch_quality":
            return (f"在{stage}上测量 Epoch 质量" if variant == "direct"
                    else f"使用 {stage} 评估 Epoch 质量")
        if op == "epoch_summary":
            return (f"在{stage}上报告试次数" if variant == "direct"
                    else f"从 {stage} 报告保留试次数")
        if op == "event_bandpower":
            return (f"在{stage}上计算绝对频带功率" if variant == "direct"
                    else f"从 {stage} 获得绝对频带功率")
        if op == "trial_selection":
            if claim.polarity == "forbidden":
                return ("禁止从源 Epoch 删除任何试次" if variant == "direct"
                        else "保留未转换 Epoch 的全部试次，禁止筛除")
            if claim.authorization == "granted":
                return ("经明确授权，从源 Epoch 移除质量标记试次" if variant == "direct"
                        else "我明确允许从未转换 Epoch 剔除质量标记试次")
            return ("要求移除质量标记试次，但未授予执行授权" if variant == "direct"
                    else "考虑剔除质量标记试次，但没有授予权限")
        if op == "epoch_rereference":
            if claim.polarity == "forbidden":
                return ("禁止将源 Epoch 重参考到 SYNTH-C2" if variant == "direct"
                        else "保持原参考，禁止改为 SYNTH-C2")
            if claim.authorization == "granted":
                return ("经明确授权，将源 Epoch 重参考到 SYNTH-C2" if variant == "direct"
                        else "我明确允许把未转换 Epoch 改为 SYNTH-C2 参考")
            return ("要求将源 Epoch 重参考到 SYNTH-C2，但未授予执行授权" if variant == "direct"
                    else "考虑使用 SYNTH-C2 参考，但没有授予修改权限")
        if op == "erd_ers":
            return "在源 Epoch 上计算 ERD/ERS"
        if op == "functional_connectivity":
            return "在未转换 Epoch 上计算功能连接"
    raise ValueError(f"Cannot render claim: {claim}")


def _render_request(family: str, target: str, tmin: float, tmax: float,
                    claims: tuple[ScientificClaim, ...]) -> str:
    separator = FAMILY_META[family][2]
    clauses = separator.join(_render_claim(claim, family) for claim in claims)
    if family == "dev_en_direct":
        return f"For {target} event epochs from {tmin:g} to {tmax:g} seconds, perform these clauses in order: {clauses}."
    if family == "dev_zh_direct":
        return f"针对 {target} 事件后 {tmin:g} 到 {tmax:g} 秒的 Epoch，按顺序执行：{clauses}。"
    if family == "holdout_en_sequence":
        return f"Using {target} event epochs in the {tmin:g}–{tmax:g} second window, keep this sequence: {clauses}."
    if family == "holdout_zh_sequence":
        return f"使用 {target} 事件 {tmin:g}–{tmax:g} 秒窗内的 Epoch，并保持以下顺序：{clauses}。"
    raise ValueError(f"Unknown family: {family}")


def _positive_precedence(claims: tuple[ScientificClaim, ...]) -> tuple[tuple[str, str], ...]:
    ids = [claim.claim_id for claim in claims if claim.polarity == "required"]
    return tuple(zip(ids, ids[1:]))


def _derive_status(claims: tuple[ScientificClaim, ...]) -> tuple[bool, str]:
    if any(not claim.supported and claim.polarity == "required" for claim in claims):
        return False, "reject"
    required_transitions = [claim for claim in claims
                            if claim.operation in {"trial_selection", "epoch_rereference"}
                            and claim.polarity == "required"]
    if any(claim.authorization != "granted" for claim in required_transitions):
        return False, "clarify"
    if len(required_transitions) > 1:
        return False, "clarify"
    if required_transitions:
        transition = required_transitions[0]
        transition_index = claims.index(transition)
        before = claims[:transition_index]
        after = claims[transition_index + 1:]
        source_outputs = [
            item for item in before
            if item.polarity == "required"
            and item.input_stage == "source_epochs"
            and not (transition.operation == "trial_selection"
                     and item.operation == "epoch_quality")
        ]
        if (source_outputs
                and any(item.polarity == "required" and item.input_stage == "effective_epochs"
                        for item in after)):
            # Frozen CIEDG has one effective branch and cannot preserve both requested outputs.
            return False, "clarify"
    return True, "accept"


def _build_claims(spec: Mapping[str, Any]) -> tuple[ScientificClaim, ...]:
    target = str(spec.get("target", "target"))
    tmin = float(spec.get("tmin", 0.0))
    tmax = float(spec.get("tmax", 1.0))
    claims = []
    for index, raw in enumerate(spec["claims"], 1):
        claims.append(ScientificClaim(
            claim_id=f"c{index}",
            operation=raw["operation"],
            object_type="event_epochs",
            target_label=target,
            tmin=tmin,
            tmax=tmax,
            input_stage=raw["input_stage"],
            output_stage=raw["output_stage"],
            polarity=raw["polarity"],
            authorization=raw["authorization"],
            supported=raw["operation"] in SUPPORTED_OPERATIONS,
            parameters=raw["parameters"],
        ))
    return tuple(claims)


def _with_evidence(claims: tuple[ScientificClaim, ...], family: str) -> tuple[ScientificClaim, ...]:
    return tuple(ScientificClaim.from_dict({
        **claim.to_dict(include_evidence=False),
        "evidence_span": _render_claim(claim, family),
    }) for claim in claims)


def _candidate_fault(contract: ScientificContract, fault: tuple[str, str | None]) -> ScientificContract:
    kind, target = fault
    claims = [claim.to_dict(include_evidence=False) for claim in contract.claims]
    precedence = [list(edge) for edge in contract.precedence]
    if kind == "omit_operation":
        removed = next(item for item in claims if item["operation"] == target)
        claims.remove(removed)
        precedence = [edge for edge in precedence if removed["claim_id"] not in edge]
    elif kind == "authorization_conflict":
        item = next(item for item in claims if item["operation"] == target)
        item["authorization"] = "granted" if item["authorization"] != "granted" else "denied"
    elif kind == "stage_conflict":
        item = next(item for item in claims if item["operation"] == target)
        wrong = "effective_epochs" if item["input_stage"] == "source_epochs" else "source_epochs"
        item["input_stage"] = wrong
        if item["operation"] not in {"trial_selection", "epoch_rereference"}:
            item["output_stage"] = wrong
    elif kind == "relation_missing":
        if not precedence:
            raise ValueError("relation_missing fault requires a precedence edge")
        precedence.pop(0)
    elif kind == "extra_operation":
        operation = str(target)
        source = contract.claims[0]
        claims.append(ScientificClaim(
            claim_id="cx",
            operation=operation,
            object_type="event_epochs",
            target_label=source.target_label,
            tmin=source.tmin,
            tmax=source.tmax,
            input_stage="source_epochs",
            output_stage=("effective_epochs" if operation in {
                "trial_selection", "epoch_rereference"} else "source_epochs"),
            authorization=("granted" if operation in {
                "trial_selection", "epoch_rereference"} else "not_required"),
            supported=operation in SUPPORTED_OPERATIONS,
            parameters=({"criterion": "quality_flagged"} if operation == "trial_selection"
                        else {"reference_channels": ["SYNTH-C2"]}
                        if operation == "epoch_rereference" else {}),
        ).to_dict(include_evidence=False))
    else:
        raise ValueError(f"Unknown fault: {kind}")
    return ScientificContract.from_dict({
        "claims": claims,
        "precedence": precedence,
        "runtime_supported": contract.runtime_supported,
        "expected_disposition": contract.expected_disposition,
    })


def generate_protocol() -> dict[str, Any]:
    cases = []
    for spec in PROTOTYPES:
        family = spec["family"]
        split, language, _ = FAMILY_META[family]
        claims = _with_evidence(_build_claims(spec), family)
        runtime_supported, disposition = _derive_status(claims)
        gold = ScientificContract(
            claims=claims,
            precedence=_positive_precedence(claims),
            runtime_supported=runtime_supported,
            expected_disposition=disposition,
            metadata={"ontology": "eeg_goal_claims_v1"},
        )
        gold.validate()
        request = _render_request(
            family, claims[0].target_label, claims[0].tmin, claims[0].tmax, claims)
        for claim in claims:
            if request.count(claim.evidence_span) != 1:
                raise ValueError(f"Evidence span is not unique in {spec['id']}: {claim.evidence_span}")
        exact = ScientificContract.from_dict(gold.to_dict(include_evidence=False))
        faulty = _candidate_fault(exact, spec["fault"])
        cases.append({
            "id": spec["id"],
            "split": split,
            "language": language,
            "template_family": family,
            "prototype_id": spec["id"],
            "request": request,
            "gold_strength": "controlled_strong_gold",
            "source_contract": gold.to_dict(),
            "candidates": [
                {"id": "exact", "fault_type": "none",
                 "contract": exact.to_dict(include_evidence=False)},
                {"id": "fault", "fault_type": spec["fault"][0],
                 "fault_target": spec["fault"][1],
                 "contract": faulty.to_dict(include_evidence=False)},
            ],
        })
    payload = {
        "protocol": "eeg_goal_completeness_controlled_gold_v1",
        "seed": SEED,
        "ontology": {
            "version": "eeg_goal_claims_v1",
            "supported_operations": sorted(SUPPORTED_OPERATIONS),
            "unsupported_operations": ["erd_ers", "functional_connectivity"],
            "stages": ["source_epochs", "effective_epochs"],
            "authorization": ["not_required", "granted", "denied", "unspecified"],
        },
        "annotation": {
            "origin": "single-author deterministic templates from structured contracts",
            "independent_human_annotation": False,
            "llm_generated_or_scored": False,
            "validity_scope": "closed controlled grammar only",
        },
        "split_policy": {
            "development_families": ["dev_en_direct", "dev_zh_direct"],
            "holdout_families": ["holdout_en_sequence", "holdout_zh_sequence"],
            "families_disjoint": True,
        },
        "cases": cases,
    }
    json.dumps(payload, ensure_ascii=False, allow_nan=False)
    return payload


HEADER_PATTERNS = {
    "dev_en_direct": re.compile(
        r"^For (?P<label>[^ ]+) event epochs from (?P<tmin>-?\d+(?:\.\d+)?) to "
        r"(?P<tmax>-?\d+(?:\.\d+)?) seconds, perform these clauses in order: (?P<body>.+)\.$"),
    "dev_zh_direct": re.compile(
        r"^针对 (?P<label>[^ ]+) 事件后 (?P<tmin>-?\d+(?:\.\d+)?) 到 "
        r"(?P<tmax>-?\d+(?:\.\d+)?) 秒的 Epoch，按顺序执行：(?P<body>.+)。$"),
    "holdout_en_sequence": re.compile(
        r"^Using (?P<label>[^ ]+) event epochs in the (?P<tmin>-?\d+(?:\.\d+)?)–"
        r"(?P<tmax>-?\d+(?:\.\d+)?) second window, keep this sequence: (?P<body>.+)\.$"),
    "holdout_zh_sequence": re.compile(
        r"^使用 (?P<label>[^ ]+) 事件 (?P<tmin>-?\d+(?:\.\d+)?)–"
        r"(?P<tmax>-?\d+(?:\.\d+)?) 秒窗内的 Epoch，并保持以下顺序：(?P<body>.+)。$"),
}


def _claim_forms(target: str, tmin: float, tmax: float) -> tuple[ScientificClaim, ...]:
    forms = []
    for operation in ("epoch_quality", "epoch_summary", "event_bandpower"):
        for stage in ("source_epochs", "effective_epochs"):
            forms.append(ScientificClaim(
                "form", operation, "event_epochs", target, tmin, tmax,
                stage, stage,
            ))
    for operation in ("trial_selection", "epoch_rereference"):
        parameters = ({"criterion": "quality_flagged"} if operation == "trial_selection"
                      else {"reference_channels": ["SYNTH-C2"]})
        for polarity, authorization, output in (
            ("required", "granted", "effective_epochs"),
            ("required", "unspecified", "effective_epochs"),
            ("forbidden", "denied", None),
        ):
            forms.append(ScientificClaim(
                "form", operation, "event_epochs", target, tmin, tmax,
                "source_epochs", output, polarity, authorization, True, parameters,
            ))
    for operation in ("erd_ers", "functional_connectivity"):
        forms.append(ScientificClaim(
            "form", operation, "event_epochs", target, tmin, tmax,
            "source_epochs", "source_epochs", supported=False,
        ))
    return tuple(forms)


def parse_controlled_request(request: str) -> ScientificContract:
    """Parse only the frozen controlled grammar; reject all other prose."""
    matched_family = None
    match = None
    for family, pattern in HEADER_PATTERNS.items():
        candidate = pattern.fullmatch(request)
        if candidate is not None:
            matched_family = family
            match = candidate
            break
    if match is None or matched_family is None:
        raise ValueError("Request is outside the frozen controlled grammar")
    target = match.group("label")
    tmin = float(match.group("tmin"))
    tmax = float(match.group("tmax"))
    separator = FAMILY_META[matched_family][2]
    clauses = match.group("body").split(separator)
    forms = _claim_forms(target, tmin, tmax)
    parsed = []
    for index, clause in enumerate(clauses, 1):
        matches = [form for form in forms if _render_claim(form, matched_family) == clause]
        if len(matches) != 1:
            raise ValueError(f"Clause is ambiguous or outside grammar: {clause}")
        raw = matches[0].to_dict(include_evidence=False)
        raw["claim_id"] = f"c{index}"
        raw["evidence_span"] = clause
        parsed.append(ScientificClaim.from_dict(raw))
    claims = tuple(parsed)
    runtime_supported, disposition = _derive_status(claims)
    return ScientificContract(
        claims=claims,
        precedence=_positive_precedence(claims),
        runtime_supported=runtime_supported,
        expected_disposition=disposition,
        metadata={"parser": "controlled_eeg_claim_grammar_v1", "family": matched_family},
    )


def protocol_bytes(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
            + "\n").encode("utf-8")


def protocol_digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(protocol_bytes(payload)).hexdigest()


def write_protocol(path: Path = PROTOCOL_PATH) -> str:
    payload = generate_protocol()
    data = protocol_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def load_protocol(path: Path = PROTOCOL_PATH, *, verify_frozen: bool = True) -> tuple[dict[str, Any], str]:
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if verify_frozen and FROZEN_PROTOCOL_SHA256 != "TO_BE_GENERATED" and digest != FROZEN_PROTOCOL_SHA256:
        raise ValueError(
            f"Controlled-gold protocol hash mismatch: {digest} != {FROZEN_PROTOCOL_SHA256}")
    payload = json.loads(data.decode("utf-8"))
    return payload, digest
