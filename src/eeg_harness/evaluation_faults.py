"""Deterministic, strategy-neutral faults used only by planning evaluation."""

from dataclasses import dataclass

from .tooling import ToolResult


@dataclass(frozen=True)
class FaultSpec:
    name: str
    before_tool: str


FAULTS = {
    "artifact_expired": FaultSpec("artifact_expired", "event_bandpower"),
    "events_removed": FaultSpec("events_removed", "create_epochs"),
    "model_resource_removed": FaultSpec("model_resource_removed", "seizure_detection"),
    "profile_mismatch": FaultSpec("profile_mismatch", "seizure_detection"),
    "transient_tool_failure": FaultSpec("transient_tool_failure", "amplitude"),
}


class FaultInjectingExecutor:
    """Apply one declared change immediately before the same affected tool call."""

    def __init__(self, executor, fault_name):
        self._executor = executor
        self.registry = executor.registry
        self.config = executor.config
        self.resources = executor.resources
        try:
            self.fault = FAULTS[fault_name]
        except KeyError as exc:
            raise ValueError(f"Unknown evaluation fault: {fault_name}") from exc
        self.applied = False

    def execute(self, record, profile, request, session_resources=None):
        if self.applied or request.name != self.fault.before_tool:
            return self._executor.execute(record, profile, request, session_resources)
        self.applied = True
        resources = session_resources or {}
        if self.fault.name == "artifact_expired":
            resources.get("artifact_store", {}).clear()
        elif self.fault.name == "events_removed":
            object.__setattr__(record, "events", None)
        elif self.fault.name == "model_resource_removed":
            self.resources["seizure_model"] = ""
        elif self.fault.name == "profile_mismatch":
            metadata = dict(record.metadata)
            metadata["profile_id"] = "edf_native"
            object.__setattr__(record, "metadata", metadata)
        elif self.fault.name == "transient_tool_failure":
            return ToolResult(
                request_id=request.request_id,
                tool_name=request.name,
                success=False,
                error_code="INJECTED_TRANSIENT_FAILURE",
                error_message="Deterministic evaluation fault",
            )
        return self._executor.execute(record, profile, request, session_resources)
