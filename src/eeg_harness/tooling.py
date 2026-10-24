"""Tool contracts and an explicit registry without eager model loading."""

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional
from uuid import uuid4


@dataclass(frozen=True)
class ToolRequest:
    name: str
    arguments: Mapping[str, Any]
    request_id: str = field(default_factory=lambda: str(uuid4()))


@dataclass(frozen=True)
class ToolResult:
    request_id: str
    tool_name: str
    success: bool
    data: Any = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    duration_ms: float = 0.0

    def to_dict(self):
        return {
            "request_id": self.request_id,
            "tool_name": self.tool_name,
            "success": self.success,
            "data": self.data,
            "error": None
            if self.success
            else {"code": self.error_code, "message": self.error_message},
            "duration_ms": self.duration_ms,
        }


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: Mapping[str, Any]
    return_type: str
    compatible_profiles: tuple[str, ...]
    handler: Callable
    requires_window: bool = False
    max_window_seconds: Optional[float] = None
    required_sfreq: Optional[float] = None
    required_resources: tuple[str, ...] = ()
    config_keys: tuple[str, ...] = ()
    consumes_artifact: Optional[str] = None
    produces_artifact: Optional[str] = None
    requires_events: bool = False
    observes_state: tuple[str, ...] = ()
    state_effect: str = "result_only"
    preconditions: Mapping[str, Any] = field(default_factory=dict)

    def public_definition(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": dict(self.parameters),
            },
        }


class ToolRegistry:
    def __init__(self):
        self._tools = {}

    def register(self, spec):
        if spec.name in self._tools:
            raise ValueError(f"Tool is already registered: {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name):
        return self._tools.get(name)

    def list_specs(self, profile_id=None):
        specs = tuple(self._tools.values())
        if profile_id is None:
            return specs
        return tuple(
            spec for spec in specs
            if "*" in spec.compatible_profiles or profile_id in spec.compatible_profiles
        )

    def public_definitions(self, profile_id=None):
        return [spec.public_definition() for spec in self.list_specs(profile_id)]

