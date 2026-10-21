"""Minimal state and contract model for planning-before-execution research.

The objects in this module describe facts already verified by the Harness.
They deliberately contain no dataset labels, diagnoses, raw EEG, or inferred
signal quality.
"""

from dataclasses import dataclass, field
import json
from typing import Any, Mapping, Optional

from .provenance import source_reference


@dataclass(frozen=True)
class TaskSpec:
    goal: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    subtasks: tuple["TaskSpec", ...] = ()
    task_id: str = "task"

    def to_dict(self):
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "arguments": dict(self.arguments),
            "subtasks": [item.to_dict() for item in self.subtasks],
        }


@dataclass(frozen=True)
class ArtifactSnapshot:
    artifact_id: str
    artifact_type: str
    context_id: str
    profile_id: str
    record_source: Mapping[str, Any]
    summary: Mapping[str, Any]

    def to_dict(self):
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "context_id": self.context_id,
            "profile_id": self.profile_id,
            "record_source": dict(self.record_source),
            "summary": dict(self.summary),
        }


@dataclass(frozen=True)
class EEGStateSnapshot:
    context_id: str
    profile_id: str
    record_source: Mapping[str, Any]
    sfreq: float
    duration_seconds: float
    channel_names: tuple[str, ...]
    event_labels: Mapping[str, int]
    artifacts: tuple[ArtifactSnapshot, ...]
    resources_available: Mapping[str, bool]
    verified_quality_facts: tuple[str, ...] = ()

    @classmethod
    def from_context(cls, context):
        labels = {}
        if context.record.events is not None:
            labels = context.record.events.summary()["labels"]
        record_ref = source_reference(context.record.source)
        artifacts = []
        for artifact_id, artifact in context.artifacts.items():
            summary = artifact.summary() if hasattr(artifact, "summary") else {}
            artifacts.append(
                ArtifactSnapshot(
                    artifact_id=artifact_id,
                    artifact_type="epochs" if hasattr(artifact, "event_labels") else "unknown",
                    context_id=context.task_id,
                    profile_id=context.profile.profile_id,
                    record_source=record_ref,
                    summary=summary,
                )
            )
        resources = {
            name: bool(value)
            for name, value in sorted(context.executor.resources.items())
            if name != "artifact_store"
        }
        return cls(
            context_id=context.task_id,
            profile_id=context.profile.profile_id,
            record_source=record_ref,
            sfreq=context.record.sfreq,
            duration_seconds=context.record.duration_seconds,
            channel_names=context.record.channel_names,
            event_labels=labels,
            artifacts=tuple(artifacts),
            resources_available=resources,
        )

    def artifact(self, artifact_id):
        return next((item for item in self.artifacts if item.artifact_id == artifact_id), None)

    def to_dict(self):
        payload = {
            "context_id": self.context_id,
            "profile_id": self.profile_id,
            "record_source": dict(self.record_source),
            "sfreq": self.sfreq,
            "duration_seconds": self.duration_seconds,
            "channel_names": list(self.channel_names),
            "event_labels": dict(self.event_labels),
            "artifacts": [item.to_dict() for item in self.artifacts],
            "resources_available": dict(self.resources_available),
            "verified_quality_facts": list(self.verified_quality_facts),
        }
        json.dumps(payload, ensure_ascii=False, allow_nan=False)
        return payload


@dataclass(frozen=True)
class OperationContract:
    tool_name: str
    required_parameters: tuple[str, ...]
    compatible_profiles: tuple[str, ...]
    consumes_artifact: Optional[str] = None
    produces_artifact: Optional[str] = None
    requires_events: bool = False
    required_resources: tuple[str, ...] = ()
    state_effect: str = "result_only"

    def to_dict(self):
        return {
            "tool_name": self.tool_name,
            "required_parameters": list(self.required_parameters),
            "compatible_profiles": list(self.compatible_profiles),
            "consumes_artifact": self.consumes_artifact,
            "produces_artifact": self.produces_artifact,
            "requires_events": self.requires_events,
            "required_resources": list(self.required_resources),
            "state_effect": self.state_effect,
        }


def build_operation_contracts(registry):
    """Build contracts for the eight registered tools without loading models."""

    artifact_consumers = {"epoch_summary": "epochs", "event_bandpower": "epochs"}
    contracts = {}
    for spec in registry.list_specs():
        contracts[spec.name] = OperationContract(
            tool_name=spec.name,
            required_parameters=tuple(spec.parameters.get("required", ())),
            compatible_profiles=tuple(spec.compatible_profiles),
            consumes_artifact=artifact_consumers.get(spec.name),
            produces_artifact="epochs" if spec.name == "create_epochs" else None,
            requires_events=spec.name == "create_epochs",
            required_resources=tuple(spec.required_resources),
            state_effect="stores_session_artifact" if spec.name == "create_epochs" else "result_only",
        )
    return contracts


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    tool_name: str
    arguments: Mapping[str, Any]
    depends_on: tuple[str, ...] = ()
    purpose: str = ""

    def to_dict(self):
        return {
            "step_id": self.step_id,
            "tool_name": self.tool_name,
            "arguments": dict(self.arguments),
            "depends_on": list(self.depends_on),
            "purpose": self.purpose,
        }


@dataclass(frozen=True)
class Plan:
    task_id: str
    status: str
    steps: tuple[PlanStep, ...] = ()
    reason_code: Optional[str] = None
    reason: Optional[str] = None
    state_summary: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self):
        payload = {
            "task_id": self.task_id,
            "status": self.status,
            "steps": [item.to_dict() for item in self.steps],
            "reason": None if self.reason_code is None else {
                "code": self.reason_code,
                "message": self.reason,
            },
            "state_summary": dict(self.state_summary),
        }
        json.dumps(payload, ensure_ascii=False, allow_nan=False)
        return payload
