"""Evidence-addressed answer release for the integrated CCEP runtime."""

import json
import math


ANSWER_TOOL = [{
    "type": "function",
    "function": {
        "name": "submit_evidence_answer",
        "description": (
            "Select exact scalar facts from successful ToolResults. The runtime validates "
            "every JSON path and renders the released answer deterministically."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "evidence_references": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "request_id": {"type": "string"},
                            "path": {
                                "type": "array",
                                "description": (
                                    "JSON path relative to that ToolResult's data object. "
                                    "Never prefix the path with data or ToolResult."
                                ),
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["request_id", "path"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["evidence_references"],
            "additionalProperties": False,
        },
    },
}]

_ORCHESTRATION_TOOLS = frozenset({"list_events", "create_epochs"})


def required_answer_tools(ledger):
    expected = next(
        item.expected for item in ledger.obligations if item.kind == "successful_tools"
    )
    return tuple(name for name in expected if name not in _ORCHESTRATION_TOOLS)


def _parse_submission(message):
    calls = message.get("tool_calls") or []
    if len(calls) != 1 or calls[0].get("function", {}).get("name") != "submit_evidence_answer":
        raise ValueError("Answer model must submit exactly one evidence answer")
    raw = calls[0]["function"].get("arguments", "{}")
    payload = json.loads(raw) if isinstance(raw, str) else raw
    references = payload.get("evidence_references") if isinstance(payload, dict) else None
    if not isinstance(references, list) or not references:
        raise ValueError("Evidence answer requires at least one reference")
    return references


def _resolve_path(value, path):
    current = value
    for component in path:
        if isinstance(current, dict) and isinstance(component, str):
            current = current[component]
        elif isinstance(current, list) and (
            isinstance(component, int) or (isinstance(component, str) and component.isdigit())
        ):
            current = current[int(component)]
        else:
            raise ValueError("Evidence reference path does not match ToolResult data")
    if isinstance(current, bool) or not isinstance(current, (str, int, float)):
        raise ValueError("Evidence reference must resolve to a scalar string or number")
    if isinstance(current, float) and not math.isfinite(current):
        raise ValueError("Evidence reference cannot contain a non-finite number")
    return current


def _render_scalar(value):
    if isinstance(value, float):
        return format(value, ".12g")
    return str(value)


def validate_and_render_answer(message, execution, ledger, required_tools=None):
    """Validate every claim address, then render only verified facts."""
    try:
        references = _parse_submission(message)
        successful = {
            item["request_id"]: item for item in execution.tool_results if item["success"]
        }
        rendered = []
        cited_tools = set()
        normalized_references = []
        for reference in references:
            request_id = reference.get("request_id")
            path = reference.get("path")
            if request_id not in successful or not isinstance(path, list):
                raise ValueError("Evidence reference does not name a successful ToolResult")
            result = successful[request_id]
            value = _resolve_path(result["data"], path)
            cited_tools.add(result["tool_name"])
            path_text = ".".join(str(item) for item in path) or "$"
            scalar = _render_scalar(value)
            rendered.append(f"{result['tool_name']}.{path_text}={scalar}")
            normalized_references.append({
                "request_id": request_id, "tool_name": result["tool_name"],
                "path": list(path), "value": value,
            })
        required = tuple(required_tools or required_answer_tools(ledger))
        missing = [name for name in required if name not in cited_tools]
        if missing:
            raise ValueError("Required answer evidence is not cited: " + ", ".join(missing))
        answer = "证据受限结果：" + "；".join(rendered) + "。以上仅对应已执行工具及当前科学条件，不构成临床诊断。"
        return answer, {
            "valid": True, "code": None, "required_tools": list(required),
            "cited_tools": sorted(cited_tools), "references": normalized_references,
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return "工具结果已保存，但回答证据引用未通过校验；请查阅结构化 ToolResult。", {
            "valid": False, "code": "ANSWER_EVIDENCE_MISMATCH", "message": str(exc),
            "required_tools": list(required_tools or required_answer_tools(ledger)), "cited_tools": [],
            "references": [],
        }

