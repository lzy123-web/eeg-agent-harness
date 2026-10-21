"""OpenAI-compatible structured tool-calling clients."""

import json
import os
from urllib import request


class LLMConfigurationError(RuntimeError):
    pass


class OpenAICompatibleClient:
    def __init__(self, base_url, api_key, model, timeout=60):
        if not base_url or not api_key or not model:
            raise LLMConfigurationError("LLM base URL, API key and model are required")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    @classmethod
    def from_env(cls):
        return cls(
            os.environ.get("EEG_HARNESS_LLM_BASE_URL"),
            os.environ.get("EEG_HARNESS_LLM_API_KEY"),
            os.environ.get("EEG_HARNESS_LLM_MODEL"),
            timeout=float(os.environ.get("EEG_HARNESS_LLM_TIMEOUT", "60")),
        )

    def complete(self, messages, tools):
        payload = json.dumps(
            {"model": self.model, "messages": messages, "tools": tools, "tool_choice": "auto"},
            ensure_ascii=False,
        ).encode("utf-8")
        endpoint = self.base_url
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"
        http_request = request.Request(
            endpoint,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with request.urlopen(http_request, timeout=self.timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        return body["choices"][0]["message"]


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

