"""Immutable semantic artifacts, operation effects, requirements and plans."""

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Mapping


def stable_id(prefix: str, *parts: Any) -> str:
    encoded = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(encoded).hexdigest()[:16]}"


@dataclass(frozen=True)
class SemanticArtifact:
    artifact_id: str
    kind: str
    stage: str
    root_id: str
    parent_ids: tuple[str, ...] = ()
    sfreq: float | None = None
    reference: str | None = None
    passband_hz: tuple[float | None, float | None] | None = None
    channels: tuple[str, ...] = ()
    time_reference: str | None = None
    event_alignment_source: str | None = None
    event_labels: tuple[str, ...] = ()
    condition_counts: tuple[tuple[str, int], ...] = ()
    filter_history: tuple[str, ...] = ()
    selection_history: tuple[str, ...] = ()
    observability: tuple[tuple[str, str], ...] = ()
    properties: tuple[tuple[str, Any], ...] = ()

    def get(self, name: str, default=None):
        return dict(self.properties).get(name, default)

    def observable(self, name: str) -> str:
        return dict(self.observability).get(name, "unknown")

    def counts(self) -> dict[str, int]:
        return dict(self.condition_counts)

    def to_dict(self):
        return {
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            "stage": self.stage,
            "root_id": self.root_id,
            "parent_ids": list(self.parent_ids),
            "sfreq": self.sfreq,
            "reference": self.reference,
            "passband_hz": list(self.passband_hz) if self.passband_hz else None,
            "channels": list(self.channels),
            "time_reference": self.time_reference,
            "event_alignment_source": self.event_alignment_source,
            "event_labels": list(self.event_labels),
            "condition_counts": dict(self.condition_counts),
            "filter_history": list(self.filter_history),
            "selection_history": list(self.selection_history),
            "observability": dict(self.observability),
            "properties": dict(self.properties),
        }


@dataclass(frozen=True)
class SemanticEffect:
    operation: str
    consumes: str
    produces: str
    preserves: tuple[str, ...]
    changes: tuple[str, ...]
    invalidates: tuple[str, ...]
    scientific_semantics: tuple[str, ...]

    def to_dict(self):
        return {
            "operation": self.operation, "consumes": self.consumes,
            "produces": self.produces, "preserves": list(self.preserves),
            "changes": list(self.changes), "invalidates": list(self.invalidates),
            "scientific_semantics": list(self.scientific_semantics),
        }


@dataclass(frozen=True)
class ScientificRequirement:
    requirement_id: str
    kind: str
    parameters: Mapping[str, Any]

    @classmethod
    def from_dict(cls, goal: Mapping[str, Any], index: int = 0):
        kind = str(goal["kind"])
        parameters = {key: value for key, value in goal.items() if key != "kind"}
        return cls(f"requirement-{index}-{kind}", kind, parameters)


@dataclass(frozen=True)
class PlanStep:
    operation: str
    input_artifact_id: str
    output_artifact_id: str
    arguments: Mapping[str, Any]
    validity_evidence: tuple[str, ...]

    def to_dict(self):
        return {
            "operation": self.operation, "input_artifact_id": self.input_artifact_id,
            "output_artifact_id": self.output_artifact_id,
            "arguments": dict(self.arguments),
            "validity_evidence": list(self.validity_evidence),
        }


@dataclass(frozen=True)
class SemanticPlan:
    planner: str
    status: str
    steps: tuple[PlanStep, ...] = ()
    output_artifact_ids: tuple[str, ...] = ()
    reason_code: str | None = None
    state_queries: int = 0
    planning_duration_ms: float = 0.0

    def to_dict(self):
        return {
            "planner": self.planner, "status": self.status,
            "steps": [step.to_dict() for step in self.steps],
            "output_artifact_ids": list(self.output_artifact_ids),
            "reason_code": self.reason_code, "state_queries": self.state_queries,
            "planning_duration_ms": self.planning_duration_ms,
        }


@dataclass
class ArtifactPayload:
    semantic: SemanticArtifact
    value: Any

    def summary(self):
        return self.semantic.to_dict()
