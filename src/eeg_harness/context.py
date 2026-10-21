"""Per-task execution state and reproducible trace collection."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from typing import Any
from uuid import uuid4

from .provenance import source_reference
from .tooling import ToolRequest


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _summary(result):
    if not result.success:
        return {"error_code": result.error_code}
    data = result.data
    if isinstance(data, dict):
        return {"type": "object", "keys": list(data)[:20]}
    if isinstance(data, list):
        return {"type": "array", "length": len(data)}
    return {"type": type(data).__name__, "value": data}


@dataclass
class TraceEvent:
    sequence: int
    request_id: str
    tool_name: str
    arguments: dict
    validation_passed: bool
    output_summary: dict
    duration_ms: float
    error: Any = None

    def to_dict(self):
        return {
            "sequence": self.sequence,
            "request_id": self.request_id,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "validation_passed": self.validation_passed,
            "output_summary": self.output_summary,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


@dataclass
class ExecutionTrace:
    task_id: str
    profile_id: str
    source: Any
    started_at_utc: str = field(default_factory=_utc_now)
    events: list[TraceEvent] = field(default_factory=list)
    ended_at_utc: str = None
    termination_reason: str = None

    def finish(self, reason):
        self.termination_reason = reason
        self.ended_at_utc = _utc_now()

    def to_dict(self):
        return {
            "task_id": self.task_id,
            "profile_id": self.profile_id,
            "source": self.source,
            "started_at_utc": self.started_at_utc,
            "ended_at_utc": self.ended_at_utc,
            "termination_reason": self.termination_reason,
            "events": [event.to_dict() for event in self.events],
        }


class ExecutionContext:
    def __init__(self, record, profile, executor, task_id=None):
        self.record = record
        self.profile = profile
        self.executor = executor
        self.task_id = task_id or str(uuid4())
        self.results = {}
        self.artifacts = {}
        self.history = []
        self.trace = ExecutionTrace(
            self.task_id, profile.profile_id, source_reference(record.source)
        )

    def _resolve_reference(self, value):
        if isinstance(value, list):
            return [self._resolve_reference(item) for item in value]
        if not isinstance(value, dict) or "$result" not in value:
            return value
        request_id = value["$result"]
        if request_id not in self.results:
            raise ValueError(f"Referenced result does not exist: {request_id}")
        current = self.results[request_id].data
        for component in value.get("path", []):
            current = current[component]
        return current

    def execute(self, request):
        try:
            arguments = {
                name: self._resolve_reference(value)
                for name, value in dict(request.arguments).items()
            }
            resolved = ToolRequest(request.name, arguments, request.request_id)
            result = self.executor.execute(
                self.record,
                self.profile,
                resolved,
                session_resources={"artifact_store": self.artifacts},
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            from .tooling import ToolResult

            arguments = dict(request.arguments)
            result = ToolResult(
                request_id=request.request_id,
                tool_name=request.name,
                success=False,
                error_code="RESULT_REFERENCE_ERROR",
                error_message=str(exc),
            )
        self.results[result.request_id] = result
        self.history.append(result.request_id)
        self.trace.events.append(
            TraceEvent(
                sequence=len(self.trace.events) + 1,
                request_id=result.request_id,
                tool_name=result.tool_name,
                arguments=arguments,
                validation_passed=result.success,
                output_summary=_summary(result),
                duration_ms=result.duration_ms,
                error=None
                if result.success
                else {"code": result.error_code, "message": result.error_message},
            )
        )
        return result

    def execute_many(self, requests, continue_on_error=True):
        outputs = []
        for request in requests:
            result = self.execute(request)
            outputs.append(result)
            if not result.success and not continue_on_error:
                self.trace.finish("stopped_on_error")
                return outputs
        reason = "completed" if all(item.success for item in outputs) else "completed_with_errors"
        self.trace.finish(reason)
        return outputs

    def reproducibility_bundle(self):
        bundle = {
            "schema_version": "1.0",
            "record": {
                "source": source_reference(self.record.source),
                "profile_id": self.profile.profile_id,
                "sfreq": self.record.sfreq,
                "channel_names": list(self.record.channel_names),
                "shape": list(self.record.data.shape),
                "processing": list(self.record.processing_metadata),
            },
            "config": dict(self.executor.config),
            "requests": [
                {
                    "request_id": event.request_id,
                    "tool_name": event.tool_name,
                    "arguments": event.arguments,
                }
                for event in self.trace.events
            ],
            "results": [self.results[request_id].to_dict() for request_id in self.history],
            "artifacts": [
                artifact.summary() if hasattr(artifact, "summary") else {"artifact_id": artifact_id}
                for artifact_id, artifact in self.artifacts.items()
            ],
            "trace": self.trace.to_dict(),
        }
        json.dumps(bundle, ensure_ascii=False, allow_nan=False)
        return bundle

