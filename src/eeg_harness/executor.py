"""Validated tool execution with structured, JSON-safe failures."""

import json
import math
from pathlib import Path
import time

from .legacy.seizure import ModelResourceError
from .profiles import ProfileValidationError
from .tooling import ToolResult


def _validate_schema(arguments, schema):
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be an object")
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    missing = [name for name in required if name not in arguments]
    if missing:
        raise ValueError(f"Missing required parameter(s): {', '.join(missing)}")
    if not schema.get("additionalProperties", True):
        extra = [name for name in arguments if name not in properties]
        if extra:
            raise ValueError(f"Unexpected parameter(s): {', '.join(extra)}")
    for name, value in arguments.items():
        expected = properties.get(name, {}).get("type")
        if expected == "array" and not isinstance(value, (list, tuple)):
            raise ValueError(f"Parameter {name} must be an array")
        if expected == "array" and len(value) < properties[name].get("minItems", 0):
            raise ValueError(f"Parameter {name} must not be empty")
        if expected == "array":
            item_type = properties[name].get("items", {}).get("type")
            if item_type == "string" and any(not isinstance(item, str) for item in value):
                raise ValueError(f"Every item in parameter {name} must be a string")
        if expected == "number" and (not isinstance(value, (int, float)) or isinstance(value, bool)):
            raise ValueError(f"Parameter {name} must be a number")
        if expected == "number" and not math.isfinite(float(value)):
            raise ValueError(f"Parameter {name} must be finite")


class Executor:
    def __init__(self, registry, config, resources=None):
        self.registry = registry
        self.config = config
        self.resources = dict(resources or {})

    def execute(self, record, profile, request):
        started = time.perf_counter()

        def fail(code, message):
            return ToolResult(
                request_id=request.request_id,
                tool_name=request.name,
                success=False,
                error_code=code,
                error_message=str(message),
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
            )

        spec = self.registry.get(request.name)
        if spec is None:
            return fail("TOOL_NOT_FOUND", f"Unknown tool: {request.name}")
        if profile.profile_id not in spec.compatible_profiles or not profile.supports_tool(spec.name):
            return fail(
                "INCOMPATIBLE_PROFILE",
                f"Tool {spec.name} is not compatible with profile {profile.profile_id}",
            )
        record_profile = record.metadata.get("profile_id")
        if record_profile and record_profile != profile.profile_id:
            return fail(
                "INCOMPATIBLE_PROFILE",
                f"Record profile {record_profile} does not match {profile.profile_id}",
            )
        try:
            profile.validate_record(record)
        except ProfileValidationError as exc:
            return fail("PROFILE_VALIDATION_FAILED", exc)
        try:
            _validate_schema(dict(request.arguments), spec.parameters)
        except (TypeError, ValueError) as exc:
            return fail("INVALID_ARGUMENT", exc)

        if spec.required_sfreq is not None and record.sfreq != spec.required_sfreq:
            return fail(
                "MODEL_INPUT_MISMATCH",
                f"Tool {spec.name} requires {spec.required_sfreq:g} Hz, got {record.sfreq:g} Hz",
            )
        for resource_name in spec.required_resources:
            resource = self.resources.get(resource_name)
            if not resource or not Path(resource).expanduser().is_file():
                return fail("MODEL_RESOURCE_MISSING", f"Required resource is missing: {resource_name}")
        if spec.requires_window:
            start = request.arguments["start"]
            end = request.arguments["end"]
            if spec.max_window_seconds is not None and end - start > spec.max_window_seconds:
                return fail(
                    "INVALID_WINDOW",
                    f"Tool {spec.name} window must not exceed {spec.max_window_seconds:g} seconds",
                )
            try:
                record.slice(start, end, request.arguments["channels"])
            except ValueError as exc:
                message = str(exc)
                code = "INVALID_CHANNEL" if "channel" in message.lower() else "INVALID_WINDOW"
                return fail(code, message)

        try:
            data = spec.handler(record, dict(request.arguments), self.config, self.resources)
            json.dumps(data, ensure_ascii=False, allow_nan=False)
        except ModelResourceError as exc:
            return fail("MODEL_RESOURCE_ERROR", exc)
        except (TypeError, ValueError, KeyError) as exc:
            return fail("TOOL_EXECUTION_FAILED", exc)
        except Exception:
            return fail("INTERNAL_TOOL_ERROR", "Tool execution failed without exposing internal traceback")
        return ToolResult(
            request_id=request.request_id,
            tool_name=request.name,
            success=True,
            data=data,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
        )

