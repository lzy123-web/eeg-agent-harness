import io
import json
import unittest
from unittest.mock import patch
from urllib import error

from eeg_harness.llm import LLMServiceError, OpenAICompatibleClient
from eeg_harness.llm_smoke import run_llm_smoke


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def _completion(message=None, finish_reason="stop", usage=None, model=None):
    payload = {
        "choices": [{
            "message": message or {"role": "assistant", "content": "ok"},
            "finish_reason": finish_reason,
        }],
        "usage": usage or {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
    }
    if model is not None:
        payload["model"] = model
    return payload


class OpenAICompatibleProtocolTest(unittest.TestCase):
    def setUp(self):
        self.client = OpenAICompatibleClient(
            "https://example.invalid", "private-value", "model",
            max_tokens=321, max_retries=0, thinking="disabled",
        )

    def test_request_and_usage_metadata(self):
        captured = {}

        def fake_urlopen(http_request, timeout):
            captured["body"] = json.loads(http_request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return _Response(_completion())

        with patch("eeg_harness.llm.request.urlopen", fake_urlopen):
            message = self.client.complete([{"role": "user", "content": "x"}], [])
        self.assertEqual(message["content"], "ok")
        self.assertEqual(captured["body"]["max_tokens"], 321)
        self.assertEqual(captured["body"]["thinking"], {"type": "disabled"})
        self.assertFalse(captured["body"]["stream"])
        self.assertNotIn("tools", captured["body"])
        self.assertEqual(self.client.total_usage["total_tokens"], 7)
        self.assertEqual(self.client.last_finish_reason, "stop")

    def test_multiple_tool_calls_and_empty_content_are_preserved(self):
        tool_calls = [
            {"id": "a", "type": "function", "function": {"name": "one", "arguments": "{}"}},
            {"id": "b", "type": "function", "function": {"name": "two", "arguments": "{}"}},
        ]
        response = _completion(
            {"role": "assistant", "content": None, "tool_calls": tool_calls},
            finish_reason="tool_calls",
        )
        with patch("eeg_harness.llm.request.urlopen", return_value=_Response(response)):
            message = self.client.complete(
                [{"role": "user", "content": "x"}],
                [{"type": "function", "function": {"name": "one", "parameters": {}}}],
            )
        self.assertIsNone(message["content"])
        self.assertEqual(message["tool_calls"], tool_calls)
        self.assertEqual(self.client.last_finish_reason, "tool_calls")

    def test_response_model_metadata_is_recorded_without_assuming_alias_identity(self):
        with patch(
            "eeg_harness.llm.request.urlopen",
            return_value=_Response(_completion(model="provider-resolved-version")),
        ):
            self.client.complete([{"role": "user", "content": "x"}], [])
        self.assertEqual("provider-resolved-version", self.client.last_response_model)
        self.assertEqual(["provider-resolved-version"], self.client.response_models)

    def test_http_error_is_sanitized_without_provider_body(self):
        failure = error.HTTPError(
            "https://example.invalid", 401, "unauthorized private diagnostic", {},
            io.BytesIO(b'{"error":{"message":"secret provider detail"}}'),
        )
        with patch("eeg_harness.llm.request.urlopen", side_effect=failure):
            with self.assertRaises(LLMServiceError) as caught:
                self.client.complete([{"role": "user", "content": "x"}], [])
        self.assertEqual(caught.exception.code, "AUTHENTICATION_ERROR")
        self.assertNotIn("secret", str(caught.exception))
        self.assertNotIn("private", str(caught.exception))

    def test_rate_limit_is_retried_once(self):
        client = OpenAICompatibleClient(
            "https://example.invalid", "private-value", "model",
            max_retries=1, retry_backoff=0,
        )
        limited = error.HTTPError(
            "https://example.invalid", 429, "limited", {}, io.BytesIO(b"limited")
        )
        with patch(
            "eeg_harness.llm.request.urlopen",
            side_effect=[limited, _Response(_completion())],
        ):
            self.assertEqual(
                client.complete([{"role": "user", "content": "x"}], [])["content"],
                "ok",
            )
        self.assertEqual(client.request_count, 2)

    def test_invalid_response_is_structured_failure(self):
        with patch(
            "eeg_harness.llm.request.urlopen", return_value=_Response({"choices": []})
        ):
            with self.assertRaises(LLMServiceError) as caught:
                self.client.complete([{"role": "user", "content": "x"}], [])
        self.assertEqual(caught.exception.code, "INVALID_RESPONSE")


class LLMSmokeTest(unittest.TestCase):
    def test_complete_probe_roundtrip(self):
        class ProbeClient:
            model = "test-model"
            request_count = 3
            total_usage = {"total_tokens": 12}
            finish_reasons = ["stop", "tool_calls", "stop"]

            def __init__(self):
                self.calls = 0

            def complete(self, messages, tools, tool_choice="auto"):
                self.calls += 1
                if self.calls == 1:
                    return {"role": "assistant", "content": "OK"}
                if self.calls == 2:
                    return {
                        "role": "assistant", "content": None,
                        "tool_calls": [{
                            "id": "probe-1", "type": "function",
                            "function": {"name": "connection_probe", "arguments": "{}"},
                        }],
                    }
                return {"role": "assistant", "content": "Probe completed."}

        report = run_llm_smoke(ProbeClient())
        self.assertTrue(report["success"])
        self.assertEqual(report["structured_tool_call"], "passed")
        self.assertEqual(report["usage"]["total_tokens"], 12)


if __name__ == "__main__":
    unittest.main()
