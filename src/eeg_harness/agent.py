"""Bounded LLM agent loop using native structured tool calls."""

from dataclasses import dataclass
import json

from .llm import LLMServiceError
from .tooling import ToolRequest


@dataclass(frozen=True)
class AgentRunResult:
    final_answer: str
    stop_reason: str
    rounds: int
    tool_calls: int
    tool_results: tuple[dict, ...]
    execution_trace: dict
    llm: dict

    def to_dict(self):
        return {
            "final_answer": self.final_answer,
            "stop_reason": self.stop_reason,
            "rounds": self.rounds,
            "tool_calls": self.tool_calls,
            "tool_results": list(self.tool_results),
            "execution_trace": self.execution_trace,
            "llm": self.llm,
        }


class EEGAgent:
    def __init__(self, llm_client, context, max_rounds=6, max_tool_calls=8):
        if max_rounds < 1 or max_tool_calls < 1:
            raise ValueError("Agent limits must be positive")
        self.llm_client = llm_client
        self.context = context
        self.max_rounds = max_rounds
        self.max_tool_calls = max_tool_calls

    def _system_message(self):
        record = self.context.record
        metadata = {
            "profile_id": self.context.profile.profile_id,
            "sfreq": record.sfreq,
            "duration_seconds": record.duration_seconds,
            "channel_names": list(record.channel_names),
            "reference": record.reference,
            "montage": record.montage,
            "shape": list(record.data.shape),
        }
        return (
            "你是 EEG 分析执行助手。分析请求必须使用提供的工具取得证据；不得编造数据、转换、"
            "artifact_id、模型结果或临床诊断。只依据当前 Profile 和成功的工具结果回答，"
            "并明确说明失败或不兼容。事件条件频带功率必须依次执行 list_events、create_epochs、"
            "event_bandpower；必须从前一步结果原样复制真实标签和 artifact_id。"
            "不要把 event_bandpower 解释为 ERD/ERS。工具不可用时不得自行模拟结果。"
            "RECORD_METADATA="
            + json.dumps(metadata, ensure_ascii=False, allow_nan=False)
        )

    def _llm_summary(self, error=None):
        return {
            "provider_model": getattr(self.llm_client, "model", None),
            "request_count": getattr(self.llm_client, "request_count", None),
            "usage": dict(getattr(self.llm_client, "total_usage", {})),
            "finish_reasons": list(getattr(self.llm_client, "finish_reasons", [])),
            "error": error,
        }

    def run(self, user_request):
        messages = [
            {"role": "system", "content": self._system_message()},
            {"role": "user", "content": user_request},
        ]
        tools = self.context.executor.registry.public_definitions(
            self.context.profile.profile_id
        )
        collected = []
        total_calls = 0

        for round_number in range(1, self.max_rounds + 1):
            try:
                assistant = self.llm_client.complete(messages, tools)
            except Exception as exc:
                self.context.trace.finish("llm_error")
                error = (
                    exc.to_dict() if isinstance(exc, LLMServiceError)
                    else {"code": "LLM_ERROR", "message": "LLM call failed."}
                )
                return AgentRunResult(
                    final_answer=f"LLM 调用失败（{error['code']}）。",
                    stop_reason="llm_error",
                    rounds=round_number,
                    tool_calls=total_calls,
                    tool_results=tuple(collected),
                    execution_trace=self.context.trace.to_dict(),
                    llm=self._llm_summary(error),
                )
            tool_calls = assistant.get("tool_calls") or []
            if not tool_calls:
                self.context.trace.finish("completed")
                result = AgentRunResult(
                    final_answer=assistant.get("content") or "",
                    stop_reason="completed",
                    rounds=round_number,
                    tool_calls=total_calls,
                    tool_results=tuple(collected),
                    execution_trace=self.context.trace.to_dict(),
                    llm=self._llm_summary(),
                )
                json.dumps(result.to_dict(), ensure_ascii=False, allow_nan=False)
                return result

            messages.append(
                {
                    "role": "assistant",
                    "content": assistant.get("content"),
                    "tool_calls": tool_calls,
                }
            )
            for call in tool_calls:
                if total_calls >= self.max_tool_calls:
                    self.context.trace.finish("tool_call_limit")
                    return AgentRunResult(
                        final_answer="达到工具调用次数上限。",
                        stop_reason="tool_call_limit",
                        rounds=round_number,
                        tool_calls=total_calls,
                        tool_results=tuple(collected),
                        execution_trace=self.context.trace.to_dict(),
                        llm=self._llm_summary(),
                    )
                function = call.get("function", {})
                try:
                    raw_arguments = function.get("arguments", "{}")
                    arguments = (
                        json.loads(raw_arguments)
                        if isinstance(raw_arguments, str)
                        else raw_arguments
                    )
                    request = ToolRequest(
                        function.get("name", ""), arguments, request_id=call.get("id") or "llm-call"
                    )
                    tool_result = self.context.execute(request)
                    rendered = tool_result.to_dict()
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    rendered = {
                        "request_id": call.get("id"),
                        "tool_name": function.get("name"),
                        "success": False,
                        "data": None,
                        "error": {"code": "INVALID_TOOL_CALL", "message": str(exc)},
                        "duration_ms": 0.0,
                    }
                total_calls += 1
                collected.append(rendered)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id"),
                        "name": function.get("name"),
                        "content": json.dumps(rendered, ensure_ascii=False, allow_nan=False),
                    }
                )

        self.context.trace.finish("round_limit")
        return AgentRunResult(
            final_answer="达到 Agent 循环轮数上限。",
            stop_reason="round_limit",
            rounds=self.max_rounds,
            tool_calls=total_calls,
            tool_results=tuple(collected),
            execution_trace=self.context.trace.to_dict(),
            llm=self._llm_summary(),
        )

