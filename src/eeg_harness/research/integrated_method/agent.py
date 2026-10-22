"""Integrated natural language → constrained plan → evidence answer Agent."""

from dataclasses import dataclass
import json
from typing import Any, Mapping, Optional

from ...planning import ConstrainedPlanRunner, StateAwareConstrainedPlanner
from .contracts import close_ledger, compile_intent, validate_plan_against_ledger
from .intent import EvidenceBoundIntentInterpreter


@dataclass(frozen=True)
class Point1RunResult:
    stop_reason: str
    interpretation: Mapping[str, Any]
    ledger: Optional[Mapping[str, Any]] = None
    plan_check: Optional[Mapping[str, Any]] = None
    execution: Optional[Mapping[str, Any]] = None
    evidence_check: Optional[Mapping[str, Any]] = None
    final_answer: str = ""
    llm: Mapping[str, Any] = None

    def to_dict(self):
        payload = {
            "method": "constraint_carrying_eeg_plan_v0",
            "stop_reason": self.stop_reason,
            "interpretation": dict(self.interpretation),
            "ledger": None if self.ledger is None else dict(self.ledger),
            "plan_check": None if self.plan_check is None else dict(self.plan_check),
            "execution": None if self.execution is None else dict(self.execution),
            "evidence_check": None if self.evidence_check is None else dict(self.evidence_check),
            "final_answer": self.final_answer,
            "llm": dict(self.llm or {}),
        }
        json.dumps(payload, ensure_ascii=False, allow_nan=False)
        return payload


class ConstraintCarryingEEGAgent:
    def __init__(self, llm_client, context, max_replans=1):
        self.llm_client = llm_client
        self.context = context
        self.interpreter = EvidenceBoundIntentInterpreter(llm_client)
        self.max_replans = max_replans

    def _llm_summary(self):
        return {
            "provider_model": getattr(self.llm_client, "model", None),
            "request_count": getattr(self.llm_client, "request_count", None),
            "usage": dict(getattr(self.llm_client, "total_usage", {})),
            "finish_reasons": list(getattr(self.llm_client, "finish_reasons", [])),
        }

    def _stop(self, reason, interpretation, message):
        self.context.trace.finish(reason)
        return Point1RunResult(
            reason, interpretation.to_dict(), final_answer=message,
            llm=self._llm_summary(),
        )

    def _answer(self, user_request, interpretation, ledger, execution, evidence):
        prompt = (
            "你是 EEG 证据回答器。只能依据给定的成功 ToolResult 和 evidence_check 回答；"
            "不得补充未执行分析、临床诊断、原始数组或未证实科学解释。若 evidence_check.closed"
            "为 false，明确报告未完成及原因。INPUT=" + json.dumps({
                "user_request": user_request,
                "intent": interpretation.intent.to_dict(),
                "ledger": ledger.to_dict(),
                "tool_results": list(execution.tool_results),
                "evidence_check": evidence,
            }, ensure_ascii=False, allow_nan=False)
        )
        try:
            response = self.llm_client.complete(
                [{"role": "system", "content": prompt},
                 {"role": "user", "content": "请给出简洁、证据受限的最终回答。"}],
                [],
            )
            return response.get("content") or ""
        except Exception:
            return "工具执行已记录，但最终回答模型调用失败；请查阅结构化 ToolResult。"

    def run(self, user_request):
        interpretation = self.interpreter.interpret(user_request, self.context)
        if not interpretation.success:
            return self._stop(
                "intent_error", interpretation,
                "无法可靠解析 EEG 分析意图；未执行任何工具。",
            )
        if interpretation.disposition == "clarify":
            slots = "、".join(interpretation.missing_slots)
            return self._stop(
                "clarification_required", interpretation,
                f"需要补充或明确以下科学参数：{slots}。在此之前不会猜测或执行分析。",
            )
        if interpretation.disposition == "reject":
            return self._stop(
                "unsupported_or_unobservable", interpretation,
                interpretation.error_message or "当前记录或工具不支持该请求。",
            )
        task, ledger = compile_intent(interpretation.intent, self.context)
        planner = StateAwareConstrainedPlanner(self.context)
        plan = planner.plan(task)
        plan_check = validate_plan_against_ledger(plan, ledger)
        if not plan_check["valid"]:
            self.context.trace.finish("plan_rejected")
            return Point1RunResult(
                "plan_rejected", interpretation.to_dict(), ledger.to_dict(),
                plan_check, final_answer="科学约束或当前 EEG 状态不允许执行该计划。",
                llm=self._llm_summary(),
            )
        execution = ConstrainedPlanRunner(
            self.context, max_replans=self.max_replans,
            plan_validator=lambda candidate: validate_plan_against_ledger(candidate, ledger),
        ).execute_plan(task, plan)
        evidence = close_ledger(ledger, execution)
        answer = self._answer(user_request, interpretation, ledger, execution, evidence)
        reason = "completed" if evidence["closed"] else "safe_stop_without_evidence"
        return Point1RunResult(
            reason, interpretation.to_dict(), ledger.to_dict(), plan_check,
            execution.to_dict(), evidence, answer, self._llm_summary(),
        )
