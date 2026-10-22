"""Sanitized, bounded connectivity and tool-call checks for an LLM provider."""

import json

from .llm import LLMConfigurationError, LLMServiceError, OpenAICompatibleClient


PROBE_TOOL = {
    "type": "function",
    "function": {
        "name": "connection_probe",
        "description": "Return the fixed status of this connectivity probe.",
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
}


def run_llm_smoke(client=None):
    report = {
        "configuration": "not_checked",
        "network_and_authentication": "not_checked",
        "structured_tool_call": "not_checked",
        "tool_result_roundtrip": "not_checked",
        "model": None,
        "request_count": 0,
        "usage": {},
        "finish_reasons": [],
        "error": None,
    }
    try:
        client = client or OpenAICompatibleClient.from_env()
        report["configuration"] = "passed"
        report["model"] = client.model
        client.complete(
            [{"role": "user", "content": "Reply with exactly OK."}], []
        )
        report["network_and_authentication"] = "passed"
        messages = [{
            "role": "user",
            "content": "Call connection_probe exactly once. Do not answer directly.",
        }]
        assistant = client.complete(
            messages,
            [PROBE_TOOL],
            tool_choice={"type": "function", "function": {"name": "connection_probe"}},
        )
        calls = assistant.get("tool_calls") or []
        if len(calls) != 1 or calls[0].get("function", {}).get("name") != "connection_probe":
            raise LLMServiceError(
                "TOOL_CALL_PROTOCOL_ERROR", "LLM did not return the required probe tool call."
            )
        arguments = json.loads(calls[0]["function"].get("arguments") or "{}")
        if arguments != {}:
            raise LLMServiceError(
                "TOOL_CALL_PROTOCOL_ERROR", "LLM returned invalid probe arguments."
            )
        report["structured_tool_call"] = "passed"
        messages.extend([
            {
                "role": "assistant",
                "content": assistant.get("content"),
                "tool_calls": calls,
            },
            {
                "role": "tool",
                "tool_call_id": calls[0].get("id"),
                "name": "connection_probe",
                "content": json.dumps({"status": "ok"}),
            },
        ])
        final = client.complete(messages, [PROBE_TOOL])
        if final.get("tool_calls") or not isinstance(final.get("content"), str):
            raise LLMServiceError(
                "TOOL_RESULT_PROTOCOL_ERROR", "LLM did not close the probe roundtrip."
            )
        report["tool_result_roundtrip"] = "passed"
    except LLMConfigurationError as exc:
        report["configuration"] = "failed"
        report["error"] = {"code": "CONFIGURATION_ERROR", "message": str(exc)}
    except LLMServiceError as exc:
        report["error"] = exc.to_dict()
    except (TypeError, ValueError, json.JSONDecodeError):
        report["error"] = {
            "code": "TOOL_CALL_PROTOCOL_ERROR",
            "message": "LLM returned an invalid structured tool call.",
        }
    if client is not None:
        report["request_count"] = getattr(client, "request_count", 0)
        report["usage"] = dict(getattr(client, "total_usage", {}))
        report["finish_reasons"] = list(getattr(client, "finish_reasons", []))
    report["success"] = all(
        report[key] == "passed" for key in (
            "configuration", "network_and_authentication",
            "structured_tool_call", "tool_result_roundtrip",
        )
    )
    json.dumps(report, ensure_ascii=False, allow_nan=False)
    return report


def main():
    report = run_llm_smoke()
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
