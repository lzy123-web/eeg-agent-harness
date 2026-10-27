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
    working_memory: dict | None = None

    def to_dict(self):
        result = {
            "final_answer": self.final_answer,
            "stop_reason": self.stop_reason,
            "rounds": self.rounds,
            "tool_calls": self.tool_calls,
            "tool_results": list(self.tool_results),
            "execution_trace": self.execution_trace,
            "llm": self.llm,
        }
        if self.working_memory is not None:
            result["working_memory"] = self.working_memory
        return result


class EEGAgent:
    def __init__(self, llm_client, context, max_rounds=6, max_tool_calls=8,
                 working_memory=None):
        if max_rounds < 1 or max_tool_calls < 1:
            raise ValueError("Agent limits must be positive")
        self.llm_client = llm_client
        self.context = context
        self.max_rounds = max_rounds
        self.max_tool_calls = max_tool_calls
        self.working_memory = working_memory

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
            "并明确说明失败或不兼容。RECORD_METADATA 已是当前记录的可信元数据；除非用户询问"
            "记录信息，否则不要重复调用元数据工具，也不要调用与目标无关的附加工具。"
            "需要通道、时间窗、事件条件或科学假设而用户没有提供时，只查询解决该缺失项所必需"
            "的状态；仍不足则请求补充，不得静默猜测。"
            "任何 artifact 参数必须来自本会话中成功工具的实际返回，不得虚构。"
            "绝对事件窗频带功率不得解释为 ERD/ERS。工具不可用时不得自行模拟结果。"
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
        memory = self.working_memory
        if memory is not None:
            memory.begin_turn(user_request)
        messages = [
            {"role": "system", "content": self._system_message()},
            {"role": "user", "content": user_request},
        ]
        tools = self.context.executor.registry.public_definitions(
            self.context.profile.profile_id
        )
        if memory is not None:
            tools = memory.tool_definitions()
        collected = []
        total_calls = 0

        def finish(reason, answer, rounds, error=None):
            self.context.trace.finish(reason)
            if memory is not None:
                memory.on_stop(reason)
                if reason not in {"completed", "partial", "clarification_required"} and hasattr(memory, "progress_notice"):
                    answer = answer + memory.progress_notice()
            result = AgentRunResult(
                final_answer=answer, stop_reason=reason, rounds=rounds,
                tool_calls=total_calls, tool_results=tuple(collected),
                execution_trace=self.context.trace.to_dict(),
                llm=self._llm_summary(error),
                working_memory=memory.snapshot() if memory is not None else None,
            )
            json.dumps(result.to_dict(), ensure_ascii=False, allow_nan=False)
            return result

        for round_number in range(1, self.max_rounds + 1):
            if memory is not None:
                stop = memory.check_stop()
                if stop:
                    return finish(stop, memory.final_answer, round_number - 1)
                messages = memory.build_messages()
                if memory.stop_reason:
                    return finish(memory.stop_reason, memory.final_answer, round_number - 1)
            try:
                if memory is not None and getattr(memory, "request_closure", False):
                    tools = memory.tool_definitions()
                    if round_number == self.max_rounds or total_calls >= self.max_tool_calls - 1:
                        memory.prepare_finalization("bounded_action_limit")
                    elif hasattr(self.llm_client, "prepare_decision") and not memory.final_only:
                        final_messages, final_tools = memory.build_final_messages()
                        if self.llm_client.prepare_decision(messages, tools, final_messages, final_tools):
                            memory.prepare_finalization("budget_reserve")
                            checkpoint = getattr(self.llm_client, "delivery_checkpoint", None)
                            if checkpoint is not None:
                                memory.use_delivery_checkpoint(checkpoint)
                    if memory.final_only:
                        messages, tools = memory.build_messages(), memory.final_tools()
                        if memory.stop_reason:
                            return finish(memory.stop_reason, memory.final_answer, round_number - 1)
                        assistant = self.llm_client.complete(messages, tools, tool_choice={
                            "type": "function", "function": {"name": "finish_task"}})
                    else:
                        assistant = self.llm_client.complete(messages, tools)
                else:
                    assistant = self.llm_client.complete(messages, tools)
            except Exception as exc:
                error = (
                    exc.to_dict() if isinstance(exc, LLMServiceError)
                    else {"code": "LLM_ERROR", "message": "LLM call failed."}
                )
                reason = "budget_exhausted" if error["code"] == "STAGE_BUDGET_EXHAUSTED" else "llm_error"
                return finish(reason, f"LLM 调用停止（{error['code']}）。",
                              round_number, error)
            tool_calls = assistant.get("tool_calls") or []
            if not tool_calls:
                if memory is not None:
                    memory.on_unstructured_answer(assistant.get("content") or "")
                    continue
                return finish("completed", assistant.get("content") or "", round_number)

            messages.append(
                {
                    "role": "assistant",
                    "content": assistant.get("content"),
                    "tool_calls": tool_calls,
                }
            )
            exchange = []
            batch_stop = None
            for call in tool_calls:
                function = call.get("function", {})
                # Complete every native call/result pair, even when the batch
                # is interrupted. Never execute later actions after a stop.
                if total_calls >= self.max_tool_calls and batch_stop is None:
                    batch_stop = "tool_call_limit"
                if memory is not None and batch_stop is None:
                    batch_stop = memory.check_stop()
                if batch_stop:
                    rendered = {"request_id": call.get("id"), "tool_name": function.get("name"),
                                "success": False, "data": {"executed": False},
                                "error": {"code": "NOT_EXECUTED", "message": batch_stop}, "duration_ms": 0.0}
                else:
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
                        tool_result = (memory.execute(request, batch_size=len(tool_calls))
                                       if memory is not None else self.context.execute(request))
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
                tool_message = {
                        "role": "tool",
                        "tool_call_id": call.get("id"),
                        "name": function.get("name"),
                        "content": json.dumps(rendered, ensure_ascii=False, allow_nan=False),
                    }
                messages.append(tool_message)
                exchange.append(tool_message)
            if memory is not None:
                memory.observe_exchange(assistant, exchange)
                if memory.stop_reason:
                    return finish(memory.stop_reason, memory.final_answer, round_number)
            if batch_stop:
                return finish(batch_stop, "达到工具调用次数上限。" if batch_stop == "tool_call_limit" else "本批剩余动作未执行。", round_number)

        return finish("round_limit", "达到 Agent 循环轮数上限。", self.max_rounds)

