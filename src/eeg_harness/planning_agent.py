"""Optional natural-language to TaskSpec bridge for constrained execution."""

from dataclasses import dataclass
import json
from typing import Any, Mapping, Optional

from .planning import ConstrainedPlanRunner, TaskSpec


@dataclass(frozen=True)
class IntentParseResult:
    success: bool
    task: Optional[TaskSpec] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self):
        return {
            "success": self.success,
            "task": None if self.task is None else self.task.to_dict(),
            "error": None if self.success else {
                "code": self.error_code, "message": self.error_message,
            },
        }


@dataclass(frozen=True)
class PlanningAgentResult:
    interpretation: Mapping[str, Any]
    execution: Optional[Mapping[str, Any]]
    stop_reason: str

    def to_dict(self):
        payload = {
            "interpretation": dict(self.interpretation),
            "execution": None if self.execution is None else dict(self.execution),
            "stop_reason": self.stop_reason,
        }
        json.dumps(payload, ensure_ascii=False, allow_nan=False)
        return payload


def _task_from_payload(payload, task_id="nl-task", depth=0):
    if depth > 2 or not isinstance(payload, dict):
        raise ValueError("Task must be an object with at most two nested levels")
    goal = payload.get("goal")
    if not isinstance(goal, str) or not goal or len(goal) > 80:
        raise ValueError("Task goal must be a non-empty string")
    arguments = payload.get("arguments", {})
    subtasks = payload.get("subtasks", [])
    if not isinstance(arguments, dict) or not isinstance(subtasks, list) or len(subtasks) > 8:
        raise ValueError("Task arguments or subtasks are invalid")
    return TaskSpec(
        goal=goal,
        arguments=arguments,
        subtasks=tuple(
            _task_from_payload(item, f"{task_id}-sub{index}", depth + 1)
            for index, item in enumerate(subtasks, 1)
        ),
        task_id=task_id,
    )


class NaturalLanguageGoalInterpreter:
    def __init__(self, llm_client):
        self.llm_client = llm_client

    @staticmethod
    def _state(context):
        events = {}
        if context.record.events is not None:
            events = context.record.events.summary().get("labels", {})
        return {
            "profile_id": context.profile.profile_id,
            "sfreq": context.record.sfreq,
            "duration_seconds": context.record.duration_seconds,
            "channel_names": list(context.record.channel_names),
            "event_labels": events,
            "available_tools": [
                item.name for item in context.executor.registry.list_specs(
                    context.profile.profile_id
                )
            ],
        }

    def interpret(self, user_request, context):
        state = self._state(context)
        system = (
            "将用户 EEG 请求转换为一个 JSON TaskSpec，只返回 JSON。"
            "不得诊断、不得编造通道、事件、资源或数据转换。"
            "可用 goal 为 tool、sequence，以及声明 Artifact 输入的工具名。"
            "STATE=" + json.dumps(state, ensure_ascii=False, allow_nan=False)
        )
        try:
            response = self.llm_client.complete(
                [{"role": "system", "content": system},
                 {"role": "user", "content": user_request}],
                [],
            )
            payload = json.loads(response.get("content") or "")
            task = _task_from_payload(payload)
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return IntentParseResult(
                False, error_code="INTENT_PARSE_ERROR", error_message=str(exc)
            )
        except Exception:
            return IntentParseResult(
                False, error_code="LLM_ERROR",
                error_message="Intent model failed without exposing internal traceback",
            )
        return IntentParseResult(True, task=task)


class NaturalLanguagePlanningAgent:
    """Interpret once, then delegate validation and execution to the Planner."""

    def __init__(self, llm_client, context, max_replans=1):
        self.context = context
        self.interpreter = NaturalLanguageGoalInterpreter(llm_client)
        self.max_replans = max_replans

    def run(self, user_request):
        interpretation = self.interpreter.interpret(user_request, self.context)
        if not interpretation.success:
            self.context.trace.finish("intent_parse_error")
            return PlanningAgentResult(
                interpretation.to_dict(), None, "intent_parse_error"
            )
        execution = ConstrainedPlanRunner(
            self.context, max_replans=self.max_replans
        ).run(interpretation.task)
        return PlanningAgentResult(
            interpretation.to_dict(), execution.to_dict(), execution.status
        )
