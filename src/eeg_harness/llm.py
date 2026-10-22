"""OpenAI-compatible structured tool-calling clients."""

import json
import os
import socket
import time
from urllib import error, request


class LLMConfigurationError(RuntimeError):
    """Raised when required LLM configuration is absent or invalid."""


class LLMServiceError(RuntimeError):
    """Sanitized provider error safe to show in local reports."""

    def __init__(self, code, message, *, status=None, retryable=False):
        super().__init__(message)
        self.code = code
        self.status = status
        self.retryable = retryable

    def to_dict(self):
        return {
            "code": self.code,
            "message": str(self),
            "status": self.status,
            "retryable": self.retryable,
        }


def _positive_int(value, name, minimum=1):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise LLMConfigurationError(f"{name} must be an integer") from exc
    if parsed < minimum:
        raise LLMConfigurationError(f"{name} must be at least {minimum}")
    return parsed


def _nonnegative_int(value, name):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise LLMConfigurationError(f"{name} must be an integer") from exc
    if parsed < 0:
        raise LLMConfigurationError(f"{name} must be non-negative")
    return parsed


class OpenAICompatibleClient:
    """Small non-streaming client retaining OpenAI tool-call message semantics."""

    RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

    def __init__(
        self,
        base_url,
        api_key,
        model,
        timeout=60,
        max_tokens=1024,
        max_retries=1,
        retry_backoff=0.5,
        thinking="disabled",
    ):
        if not base_url or not api_key or not model:
            raise LLMConfigurationError("LLM base URL, API key and model are required")
        try:
            timeout = float(timeout)
            retry_backoff = float(retry_backoff)
        except (TypeError, ValueError) as exc:
            raise LLMConfigurationError("LLM timeout and retry backoff must be numeric") from exc
        if timeout <= 0 or retry_backoff < 0:
            raise LLMConfigurationError("LLM timeout must be positive and backoff non-negative")
        if thinking not in {"enabled", "disabled"}:
            raise LLMConfigurationError("LLM thinking must be enabled or disabled")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_tokens = _positive_int(max_tokens, "LLM max tokens")
        self.max_retries = _nonnegative_int(max_retries, "LLM max retries")
        self.retry_backoff = retry_backoff
        self.thinking = thinking
        self.last_usage = {}
        self.total_usage = {}
        self.last_finish_reason = None
        self.finish_reasons = []
        self.request_count = 0

    @classmethod
    def from_env(cls):
        return cls(
            os.environ.get("EEG_HARNESS_LLM_BASE_URL"),
            os.environ.get("EEG_HARNESS_LLM_API_KEY"),
            os.environ.get("EEG_HARNESS_LLM_MODEL"),
            timeout=os.environ.get("EEG_HARNESS_LLM_TIMEOUT", "60"),
            max_tokens=os.environ.get("EEG_HARNESS_LLM_MAX_TOKENS", "1024"),
            max_retries=os.environ.get("EEG_HARNESS_LLM_MAX_RETRIES", "1"),
            retry_backoff=os.environ.get("EEG_HARNESS_LLM_RETRY_BACKOFF", "0.5"),
            thinking=os.environ.get("EEG_HARNESS_LLM_THINKING", "disabled"),
        )

    @property
    def endpoint(self):
        endpoint = self.base_url
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"
        return endpoint

    @staticmethod
    def _sanitized_http_error(status):
        if status in {401, 403}:
            return LLMServiceError(
                "AUTHENTICATION_ERROR", "LLM authentication or authorization failed.",
                status=status,
            )
        if status == 429:
            return LLMServiceError(
                "RATE_LIMITED", "LLM service rate limit was reached.",
                status=status, retryable=True,
            )
        if status in {500, 502, 503, 504}:
            return LLMServiceError(
                "SERVICE_UNAVAILABLE", "LLM service is temporarily unavailable.",
                status=status, retryable=True,
            )
        return LLMServiceError(
            "HTTP_ERROR", f"LLM service returned HTTP status {status}.", status=status,
        )

    def _record_metadata(self, response_body):
        choices = response_body.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise LLMServiceError("INVALID_RESPONSE", "LLM response has no valid choice.")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise LLMServiceError("INVALID_RESPONSE", "LLM response has no valid message.")
        usage = response_body.get("usage") or {}
        self.last_usage = {
            key: int(value) for key, value in usage.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
        for key, value in self.last_usage.items():
            self.total_usage[key] = self.total_usage.get(key, 0) + value
        self.last_finish_reason = choices[0].get("finish_reason")
        self.finish_reasons.append(self.last_finish_reason)
        return message

    def complete(self, messages, tools, tool_choice="auto"):
        body = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "stream": False,
            "thinking": {"type": self.thinking},
        }
        if tools:
            body.update({"tools": tools, "tool_choice": tool_choice})
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        http_request = request.Request(
            self.endpoint,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        attempts = self.max_retries + 1
        for attempt in range(attempts):
            self.request_count += 1
            try:
                with request.urlopen(http_request, timeout=self.timeout) as response:
                    response_body = json.loads(response.read().decode("utf-8"))
                return self._record_metadata(response_body)
            except error.HTTPError as exc:
                sanitized = self._sanitized_http_error(exc.code)
                if not sanitized.retryable or attempt + 1 >= attempts:
                    raise sanitized from None
            except (error.URLError, TimeoutError, socket.timeout):
                sanitized = LLMServiceError(
                    "NETWORK_ERROR", "LLM service could not be reached before timeout.",
                    retryable=True,
                )
                if attempt + 1 >= attempts:
                    raise sanitized from None
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise LLMServiceError(
                    "INVALID_RESPONSE", "LLM service returned invalid JSON."
                ) from None
            if self.retry_backoff:
                time.sleep(self.retry_backoff * (attempt + 1))
        raise LLMServiceError("UNKNOWN_ERROR", "LLM request failed.")


class DemoFakeLLM:
    """Deterministic fake used to verify the complete agent loop."""

    def __init__(self):
        self.calls = []

    def complete(self, messages, tools):
        self.calls.append({"messages": messages, "tools": tools})
        user_text = next(
            message["content"] for message in reversed(messages) if message["role"] == "user"
        )
        is_event_request = any(word in user_text.lower() for word in ("事件", "epoch", "erp"))
        if messages[-1]["role"] == "tool":
            result = json.loads(messages[-1]["content"])
            if is_event_request and result["success"]:
                if result["tool_name"] == "list_events":
                    labels = list(result["data"]["labels"])
                    if not labels:
                        return {"role": "assistant", "content": "当前记录没有可用事件。"}
                    return self._tool_call(
                        "create_epochs",
                        {"labels": [labels[0]], "tmin": -0.2, "tmax": 0.8, "baseline": [-0.2, 0]},
                        "fake-create-epochs",
                    )
                if result["tool_name"] == "create_epochs":
                    return self._tool_call(
                        "epoch_summary",
                        {"artifact_id": result["data"]["artifact_id"]},
                        "fake-epoch-summary",
                    )
                if result["tool_name"] == "epoch_summary":
                    return self._tool_call(
                        "event_bandpower",
                        {"artifact_id": result["data"]["artifact_id"]},
                        "fake-event-bandpower",
                    )
            status = "成功" if result["success"] else f"失败（{result['error']['code']}）"
            return {"role": "assistant", "content": f"工具 {result['tool_name']} 执行{status}。"}

        names = {item["function"]["name"] for item in tools}
        if is_event_request:
            tool_name = "list_events"
        elif any(word in user_text.lower() for word in ("癫痫", "seizure")):
            tool_name = "seizure_detection"
        elif any(word in user_text.lower() for word in ("频带", "功率", "psd")):
            tool_name = "psd"
        else:
            tool_name = "record_info"
        if tool_name not in names:
            return {"role": "assistant", "content": f"当前 Profile 不支持工具 {tool_name}。"}

        arguments = {}
        if tool_name in {"amplitude", "psd", "seizure_detection"}:
            metadata = json.loads(messages[0]["content"].split("RECORD_METADATA=", 1)[1])
            arguments = {
                "channels": [metadata["channel_names"][0]],
                "start": 0,
                "end": 1,
            }
        return self._tool_call(tool_name, arguments, "fake-tool-call-1")

    @staticmethod
    def _tool_call(tool_name, arguments, call_id):
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": tool_name, "arguments": json.dumps(arguments)},
                }
            ],
        }


class DeterministicGoalFakeLLM:
    """Human-authored language templates for bridge tests, not an LLM result."""

    def __init__(self):
        self.calls = []

    def complete(self, messages, tools):
        self.calls.append({"messages": messages, "tools": tools})
        user_text = next(item["content"] for item in messages if item["role"] == "user")
        if "__INVALID__" in user_text:
            return {"role": "assistant", "content": "not-json"}
        state = json.loads(messages[0]["content"].split("STATE=", 1)[1])
        channel = state["channel_names"][0]
        label = next(iter(state.get("event_labels", {})), "A")
        lower = user_text.lower()
        if any(word in lower for word in ("诊断", "diagnos")):
            task = {"goal": "clinical_diagnosis", "arguments": {}}
        elif any(word in lower for word in ("组合", "multiple", "先幅值")):
            task = {
                "goal": "sequence",
                "subtasks": [
                    {"goal": "tool", "arguments": {"tool_name": "amplitude", "parameters": {
                        "channels": [channel], "start": 0, "end": 1,
                    }}},
                    {"goal": "event_bandpower", "arguments": {
                        "labels": [label], "tmin": -0.2, "tmax": 0.8,
                    }},
                ],
            }
        elif any(word in lower for word in ("epoch 摘要", "epoch summary")):
            task = {"goal": "epoch_summary", "arguments": {
                "labels": [label], "tmin": -0.2, "tmax": 0.2,
            }}
        elif any(word in lower for word in ("事件", "event", "erp")):
            task = {"goal": "event_bandpower", "arguments": {
                "labels": [label], "tmin": -0.2, "tmax": 0.8,
            }}
        elif any(word in lower for word in ("癫痫", "seizure", "模型")):
            task = {"goal": "tool", "arguments": {
                "tool_name": "seizure_detection", "parameters": {
                    "channels": [channel], "start": 0, "end": 1,
                },
            }}
        elif any(word in lower for word in ("频带", "功率", "psd")):
            task = {"goal": "tool", "arguments": {
                "tool_name": "psd", "parameters": {
                    "channels": [channel], "start": 0, "end": 1,
                },
            }}
        elif any(word in lower for word in ("幅值", "window", "窗口")):
            task = {"goal": "tool", "arguments": {
                "tool_name": "amplitude", "parameters": {
                    "channels": [channel], "start": 0, "end": 1,
                },
            }}
        else:
            task = {"goal": "tool", "arguments": {
                "tool_name": "record_info", "parameters": {},
            }}
        return {"role": "assistant", "content": json.dumps(task, ensure_ascii=False)}


class DeterministicComparisonFakeLLM:
    """One deterministic backend supporting both compared output protocols."""

    def __init__(self):
        self.native = DemoFakeLLM()
        self.goal = DeterministicGoalFakeLLM()

    @property
    def calls(self):
        return self.native.calls + self.goal.calls

    def complete(self, messages, tools):
        if tools:
            return self.native.complete(messages, tools)
        return self.goal.complete(messages, tools)

