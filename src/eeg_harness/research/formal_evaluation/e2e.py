"""Bounded natural-language evaluation on frozen synthetic formal cases."""

from datetime import datetime, timezone
import json
import re

from ...agent import EEGAgent
from ...llm import LLMServiceError
from ..integrated_method.transfer import ConstraintCarryingEEGAgentTransfer
from ..integrated_method.v11 import ConstraintCarryingEEGAgentV11
from .faults import apply_fault
from .fixtures import build_fixture
from .protocol import FROZEN_CANDIDATE_SHA, load_cases
from .scoring import score_case


class BoundedClient:
    """Share a hard external-call and token budget across all compared methods."""

    def __init__(self, client, max_requests=40, max_total_tokens=140_000):
        self.client = client
        self.max_requests = max_requests
        self.max_total_tokens = max_total_tokens
        self.request_count = 0
        self.total_usage = {}
        self.finish_reasons = []
        self.model = client.model
        self.thinking = client.thinking

    def complete(self, messages, tools, tool_choice="auto"):
        if self.request_count >= self.max_requests:
            raise LLMServiceError("EVAL_REQUEST_BUDGET", "Evaluation request budget exhausted.")
        if self.total_usage.get("total_tokens", 0) >= self.max_total_tokens:
            raise LLMServiceError("EVAL_TOKEN_BUDGET", "Evaluation token budget exhausted.")
        response = self.client.complete(messages, tools, tool_choice=tool_choice)
        self.request_count += 1
        self.finish_reasons.append(self.client.last_finish_reason)
        for key, value in self.client.last_usage.items():
            self.total_usage[key] = self.total_usage.get(key, 0) + value
        return response


def _ciedg_result(raw):
    payload = raw.to_dict()
    execution = payload.get("execution") or {}
    status = execution.get("status")
    if payload["stop_reason"] == "clarification_required":
        status = "clarification_required"
    elif payload["stop_reason"] in {"unsupported_or_unobservable", "plan_rejected"}:
        status = "rejected"
    elif status is None:
        status = "completed" if payload["stop_reason"] == "completed" else payload["stop_reason"]
    normalized = dict(execution)
    normalized["status"] = status
    normalized.setdefault("tool_results", [])
    normalized.setdefault("release_results", [])
    normalized.setdefault("scientific_state", {})
    normalized["final_answer"] = payload.get("final_answer", "")
    normalized["answer_check"] = payload.get("answer_check")
    normalized["interpretation"] = payload.get("interpretation")
    return normalized, payload


def _native_terminal(payload):
    failures = [row.get("error") or {} for row in payload.get("tool_results", ()) if not row.get("success")]
    codes = {item.get("code") for item in failures}
    if codes & {"NO_USABLE_EPOCHS_FOR_CONDITION", "EMPTY_EPOCH_SELECTION"}:
        return "scientifically_blocked"
    answer = (payload.get("final_answer") or "").casefold()
    successful = [row for row in payload.get("tool_results", ()) if row.get("success")]
    clarification_markers = (
        "请提供", "请明确", "需要提供", "需要明确", "未指定", "缺少",
        "which reference", "reference channel", "please specify", "please provide",
    )
    substantive = {
        "create_epochs", "select_quality_epochs", "rereference_epochs",
        "epoch_quality", "epoch_summary", "event_bandpower",
    }
    completed_substantive = any(row.get("tool_name") in substantive for row in successful)
    if not completed_substantive and any(marker in answer for marker in clarification_markers):
        return "clarification_required"
    rejection_markers = ("不支持", "无法执行", "incompatible", "not supported")
    if not successful and any(marker in answer for marker in rejection_markers):
        return "rejected"
    return "completed" if payload.get("stop_reason") == "completed" else payload.get("stop_reason")


def _native_result(raw, context):
    payload = raw.to_dict()
    successful = [row for row in payload["tool_results"] if row.get("success")]
    effective = None
    for row in reversed(successful):
        if row["tool_name"] in {"event_bandpower", "epoch_summary", "epoch_quality",
                               "select_quality_epochs", "rereference_epochs"}:
            effective = (row.get("data") or {}).get("artifact_id")
            if effective:
                break
    transition_calls = sum(row["tool_name"] in {"create_epochs", "select_quality_epochs",
                                                 "rereference_epochs"}
                           for row in payload["tool_results"])
    expected_initial = len({row["tool_name"] for row in payload["tool_results"]
                            if row["tool_name"] in {"create_epochs", "select_quality_epochs",
                                                    "rereference_epochs"}})
    normalized = {
        "status": _native_terminal(payload),
        "tool_results": payload["tool_results"],
        "release_results": successful,
        "scientific_state": {"artifacts": {"effective": effective}},
        "repairs": max(0, transition_calls - expected_initial),
        "final_answer": payload.get("final_answer", ""),
    }
    return normalized, payload


def _numeric_leaves(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _numeric_leaves(item)
    elif isinstance(value, list):
        for item in value:
            yield from _numeric_leaves(item)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        yield float(value)


def audit_answer(answer, request_text, tool_results):
    """Conservative evidence audit; it never judges prose style or diagnosis."""
    scrubbed = re.sub(r"`[^`]+`", "", answer)
    scrubbed = re.sub(r"(?:sha256:)?[0-9a-f]{8,}", "", scrubbed, flags=re.IGNORECASE)
    answer_numbers = [float(item) for item in re.findall(
        r"(?<![\w.])-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", scrubbed)]
    support = list(_numeric_leaves([row.get("data") for row in tool_results if row.get("success")]))
    support.extend(float(item) for item in re.findall(r"-?\d+(?:\.\d+)?", request_text))

    def supported(value):
        candidates = (value, value / 100.0, value * 100.0)
        return any(abs(candidate - known) <= max(1e-9, abs(known) * 0.02)
                   for candidate in candidates for known in support)

    unsupported = [value for value in answer_numbers if not supported(value)]
    forbidden_claim = any(marker in answer.casefold() for marker in (
        "临床诊断为", "确诊", "clinical diagnosis is", "diagnosed with",
    ))
    unresolved = []
    for index, row in enumerate(tool_results):
        if row.get("success"):
            continue
        if not any(later.get("success") and later.get("tool_name") == row.get("tool_name")
                   for later in tool_results[index + 1:]):
            unresolved.append(row.get("tool_name"))
    failure_disclosed = not unresolved or any(marker in answer.casefold() for marker in (
        "失败", "未完成", "无法", "error", "failed", "not completed", "could not",
    ))
    return {
        "valid": bool(answer.strip()) and not unsupported and not forbidden_claim and failure_disclosed,
        "unsupported_numeric_claims": unsupported,
        "forbidden_clinical_claim": forbidden_claim,
        "unresolved_failed_tools": unresolved,
        "unresolved_failure_disclosed": failure_disclosed,
    }


def run_e2e_suite(client, case_ids, *, methods=("CIEDG", "native_agent"),
                  cases_path="config/point1_formal_eval_cases_v1.json",
                  config_path="config/baseline.json"):
    protocol, digest = load_cases(cases_path)
    by_id = {case["id"]: case for case in protocol["cases"]}
    rows = []
    for case_id in case_ids:
        case = by_id[case_id]
        for method in methods:
            before_requests = client.request_count
            before_tokens = client.total_usage.get("total_tokens", 0)
            context, _, config = build_fixture(case, config_path)
            apply_fault(context, case)
            if method == "CIEDG":
                agent_class = (ConstraintCarryingEEGAgentTransfer
                               if case["family"] == "rereference"
                               else ConstraintCarryingEEGAgentV11)
                normalized, raw = _ciedg_result(agent_class(client, context).run(case["request"]))
            elif method == "native_agent":
                normalized, raw = _native_result(
                    EEGAgent(client, context, max_rounds=10, max_tool_calls=16).run(case["request"]),
                    context,
                )
            else:
                raise ValueError(f"Unknown E2E method: {method}")
            score = score_case(case, normalized, context, config)
            answer_audit = audit_answer(
                normalized.get("final_answer", ""), case["request"], normalized["tool_results"])
            pipeline_answer_valid = not (
                method == "CIEDG" and raw.get("answer_check") is not None
                and not raw["answer_check"].get("valid", False)
            )
            rows.append({
                "case_id": case_id, "family": case["family"], "method": method,
                "request": case["request"], "fault": case["fault"],
                "score": score, "answer_audit": answer_audit,
                "pipeline_answer_valid": pipeline_answer_valid,
                "accepted": score["passed"] and answer_audit["valid"] and pipeline_answer_valid,
                "llm_delta": {
                    "requests": client.request_count - before_requests,
                    "total_tokens": client.total_usage.get("total_tokens", 0) - before_tokens,
                },
                "result": raw,
            })
    return {
        "experiment_id": "ciedg-formal-natural-language-bounded-v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "candidate_sha": FROZEN_CANDIDATE_SHA,
        "supplement_sha256": digest,
        "case_ids": list(case_ids), "methods": list(methods),
        "privacy": {"synthetic_only": True, "raw_eeg_sent_to_llm": False,
                    "contains_api_key_or_headers": False},
        "limits": {"max_requests": client.max_requests,
                   "max_total_tokens": client.max_total_tokens,
                   "max_rounds_per_native_case": 10, "max_tool_calls_per_case": 16},
        "provider": {"model": client.model, "thinking": client.thinking},
        "rows": rows,
        "summary": {
            "rows": len(rows), "accepted": sum(row["accepted"] for row in rows),
            "requests": client.request_count,
            "total_tokens": client.total_usage.get("total_tokens", 0),
        },
    }
