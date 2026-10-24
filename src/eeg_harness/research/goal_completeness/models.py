"""Typed contracts used only by the goal-completeness research pilot."""

from dataclasses import dataclass, field
import json
from typing import Any, Mapping, Optional


OPERATIONS = frozenset({
    "epoch_quality",
    "trial_selection",
    "epoch_summary",
    "event_bandpower",
    "epoch_rereference",
    "erd_ers",
    "functional_connectivity",
})
SUPPORTED_OPERATIONS = frozenset({
    "epoch_quality",
    "trial_selection",
    "epoch_summary",
    "event_bandpower",
    "epoch_rereference",
})
STAGES = frozenset({"source_epochs", "effective_epochs"})
POLARITIES = frozenset({"required", "forbidden"})
AUTHORIZATIONS = frozenset({"not_required", "granted", "denied", "unspecified"})


@dataclass(frozen=True)
class ScientificClaim:
    claim_id: str
    operation: str
    object_type: str
    target_label: str
    tmin: float
    tmax: float
    input_stage: str
    output_stage: Optional[str]
    polarity: str = "required"
    authorization: str = "not_required"
    supported: bool = True
    parameters: Mapping[str, Any] = field(default_factory=dict)
    evidence_span: str = ""

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ScientificClaim":
        claim = cls(
            claim_id=str(payload["claim_id"]),
            operation=str(payload["operation"]),
            object_type=str(payload["object_type"]),
            target_label=str(payload["target_label"]),
            tmin=float(payload["tmin"]),
            tmax=float(payload["tmax"]),
            input_stage=str(payload["input_stage"]),
            output_stage=(None if payload.get("output_stage") is None
                          else str(payload["output_stage"])),
            polarity=str(payload.get("polarity", "required")),
            authorization=str(payload.get("authorization", "not_required")),
            supported=bool(payload.get("supported", True)),
            parameters=dict(payload.get("parameters", {})),
            evidence_span=str(payload.get("evidence_span", "")),
        )
        claim.validate()
        return claim

    def validate(self) -> None:
        if self.operation not in OPERATIONS:
            raise ValueError(f"Unknown operation: {self.operation}")
        if self.input_stage not in STAGES:
            raise ValueError(f"Unknown input stage: {self.input_stage}")
        if self.output_stage is not None and self.output_stage not in STAGES:
            raise ValueError(f"Unknown output stage: {self.output_stage}")
        if self.polarity not in POLARITIES:
            raise ValueError(f"Unknown polarity: {self.polarity}")
        if self.authorization not in AUTHORIZATIONS:
            raise ValueError(f"Unknown authorization: {self.authorization}")
        if not self.claim_id:
            raise ValueError("claim_id must not be empty")
        if not self.target_label:
            raise ValueError("target_label must not be empty")
        if self.tmax <= self.tmin:
            raise ValueError("tmax must be greater than tmin")
        expected_supported = self.operation in SUPPORTED_OPERATIONS
        if self.supported != expected_supported:
            raise ValueError(
                f"supported flag disagrees with frozen ontology for {self.operation}")

    def semantic_anchor(self) -> tuple[str, str, str, float, float]:
        return (
            self.operation,
            self.object_type,
            self.target_label,
            self.tmin,
            self.tmax,
        )

    def to_dict(self, *, include_evidence: bool = True) -> dict[str, Any]:
        payload = {
            "claim_id": self.claim_id,
            "operation": self.operation,
            "object_type": self.object_type,
            "target_label": self.target_label,
            "tmin": self.tmin,
            "tmax": self.tmax,
            "input_stage": self.input_stage,
            "output_stage": self.output_stage,
            "polarity": self.polarity,
            "authorization": self.authorization,
            "supported": self.supported,
            "parameters": dict(self.parameters),
        }
        if include_evidence:
            payload["evidence_span"] = self.evidence_span
        return payload


@dataclass(frozen=True)
class ScientificContract:
    claims: tuple[ScientificClaim, ...]
    precedence: tuple[tuple[str, str], ...] = ()
    runtime_supported: bool = True
    expected_disposition: str = "accept"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ScientificContract":
        contract = cls(
            claims=tuple(ScientificClaim.from_dict(item) for item in payload["claims"]),
            precedence=tuple(tuple(edge) for edge in payload.get("precedence", ())),
            runtime_supported=bool(payload.get("runtime_supported", True)),
            expected_disposition=str(payload.get("expected_disposition", "accept")),
            metadata=dict(payload.get("metadata", {})),
        )
        contract.validate()
        return contract

    def validate(self) -> None:
        ids = [claim.claim_id for claim in self.claims]
        if len(ids) != len(set(ids)):
            raise ValueError("claim ids must be unique")
        known = set(ids)
        for edge in self.precedence:
            if len(edge) != 2 or edge[0] not in known or edge[1] not in known:
                raise ValueError(f"Invalid precedence edge: {edge}")
            if edge[0] == edge[1]:
                raise ValueError("Self precedence is invalid")
        if self.expected_disposition not in {"accept", "clarify", "reject"}:
            raise ValueError("Unknown expected disposition")

    def to_dict(self, *, include_evidence: bool = True) -> dict[str, Any]:
        payload = {
            "claims": [claim.to_dict(include_evidence=include_evidence)
                       for claim in self.claims],
            "precedence": [list(edge) for edge in self.precedence],
            "runtime_supported": self.runtime_supported,
            "expected_disposition": self.expected_disposition,
            "metadata": dict(self.metadata),
        }
        json.dumps(payload, ensure_ascii=False, allow_nan=False)
        return payload


@dataclass(frozen=True)
class CoverageReport:
    disposition: str
    covered: tuple[Mapping[str, Any], ...]
    missing: tuple[Mapping[str, Any], ...]
    extra: tuple[Mapping[str, Any], ...]
    conflicts: tuple[Mapping[str, Any], ...]
    missing_relations: tuple[tuple[str, str], ...]
    extra_relations: tuple[tuple[str, str], ...]
    unsupported_operations: tuple[str, ...]

    def issue_types(self) -> tuple[str, ...]:
        result = []
        if self.missing:
            result.append("missing_operation")
        if self.extra:
            result.append("extra_operation")
        result.extend(sorted({str(item["type"]) for item in self.conflicts}))
        if self.missing_relations:
            result.append("missing_relation")
        if self.extra_relations:
            result.append("extra_relation")
        if self.unsupported_operations:
            result.append("unsupported_operation")
        return tuple(result)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "disposition": self.disposition,
            "covered": [dict(item) for item in self.covered],
            "missing": [dict(item) for item in self.missing],
            "extra": [dict(item) for item in self.extra],
            "conflicts": [dict(item) for item in self.conflicts],
            "missing_relations": [list(edge) for edge in self.missing_relations],
            "extra_relations": [list(edge) for edge in self.extra_relations],
            "unsupported_operations": list(self.unsupported_operations),
            "issue_types": list(self.issue_types()),
        }
        json.dumps(payload, ensure_ascii=False, allow_nan=False)
        return payload
