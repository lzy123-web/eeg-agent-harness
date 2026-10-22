"""Pilot evidence-driven policy over explicitly legal EEG analysis choices."""

from dataclasses import dataclass, field
import json
import time
from typing import Any, Mapping

from .tooling import ToolRequest


@dataclass(frozen=True)
class EvidenceRequirement:
    min_usable_epochs_per_condition: int = 1
    require_unflagged_channels: bool = True
    max_tool_calls: int = 6


@dataclass(frozen=True)
class EvidenceGoal:
    kind: str
    arguments: Mapping[str, Any]
    legal_alternatives: tuple[Mapping[str, Any], ...] = ()
    requirement: EvidenceRequirement = field(default_factory=EvidenceRequirement)
    goal_id: str = "evidence-goal"


@dataclass(frozen=True)
class EvidencePolicyResult:
    status: str
    evidence_satisfied: bool
    tool_results: tuple[Mapping[str, Any], ...]
    decision_trace: tuple[Mapping[str, Any], ...]
    reason_code: str | None
    duration_ms: float

    def to_dict(self):
        payload = {
            "status": self.status,
            "evidence_satisfied": self.evidence_satisfied,
            "tool_results": list(self.tool_results),
            "decision_trace": list(self.decision_trace),
            "reason_code": self.reason_code,
            "duration_ms": self.duration_ms,
        }
        json.dumps(payload, ensure_ascii=False, allow_nan=False)
        return payload


class EvidencePolicy:
    def __init__(self, context, mode="candidate"):
        if mode not in ("fixed", "expert", "candidate"):
            raise ValueError(f"Unknown evidence policy mode: {mode}")
        self.context = context
        self.mode = mode

    def _execute(self, name, arguments, results, requirement):
        if len(results) >= requirement.max_tool_calls:
            return None
        result = self.context.execute(ToolRequest(name, arguments))
        results.append(result.to_dict())
        return result

    @staticmethod
    def _window_flag_count(evidence, channels):
        return sum(
            any(metric.get("flagged") is True for metric in evidence["channel_metrics"][name].values())
            for name in channels
        )

    def _window(self, goal, results, trace):
        requirement = goal.requirement
        candidates = [dict(goal.arguments), *map(dict, goal.legal_alternatives)]
        all_channels = list(dict.fromkeys(
            channel for candidate in candidates for channel in candidate["channels"]
        ))
        starts = {float(item["start"]) for item in candidates}
        ends = {float(item["end"]) for item in candidates}
        if len(starts) != 1 or len(ends) != 1:
            evidence_by_candidate = []
            for candidate in candidates:
                measured = self._execute("record_quality", candidate, results, requirement)
                if measured is None or not measured.success:
                    return "failed", False, "QUALITY_EVIDENCE_FAILED"
                evidence_by_candidate.append(measured.data)
        else:
            quality_args = {
                "channels": all_channels,
                "start": next(iter(starts)), "end": next(iter(ends)),
            }
            measured = self._execute("record_quality", quality_args, results, requirement)
            if measured is None or not measured.success:
                return "failed", False, "QUALITY_EVIDENCE_FAILED"
            evidence_by_candidate = [measured.data] * len(candidates)
        scored = [
            (self._window_flag_count(evidence, candidate["channels"]), index, candidate, evidence)
            for index, (candidate, evidence) in enumerate(zip(candidates, evidence_by_candidate))
        ]
        requested_score = scored[0][0]
        if self.mode == "fixed":
            selected = scored[0]
        elif self.mode == "expert":
            selected = next((item for item in scored if item[0] == 0), scored[0])
        else:
            selected = min(scored, key=lambda item: (item[0], item[1]))
        trace.append({
            "decision": "select_window_or_channels",
            "evidence_id": selected[3]["evidence_id"],
            "candidate_flag_counts": [item[0] for item in scored],
            "selected_candidate_index": selected[1],
            "selection_basis": "quality flags then declared order; never feature value",
        })
        if requirement.require_unflagged_channels and selected[0] > 0:
            return "insufficient_evidence", False, "INSUFFICIENT_EVIDENCE"
        analysis = self._execute("psd", selected[2], results, requirement)
        if analysis is None:
            return "budget_exhausted", False, "BUDGET_EXHAUSTED"
        if not analysis.success:
            return "failed", False, analysis.error_code
        satisfied = requested_score == 0 or self.mode != "fixed"
        return "completed", satisfied, None if satisfied else "QUALITY_REQUIREMENT_NOT_MET"

    def _event(self, goal, results, trace):
        requirement = goal.requirement
        created = self._execute("create_epochs", dict(goal.arguments), results, requirement)
        if created is None or not created.success:
            return "insufficient_evidence", False, "INSUFFICIENT_EVENT_COVERAGE"
        artifact_id = created.data["artifact_id"]
        quality = self._execute("epoch_quality", {"artifact_id": artifact_id}, results, requirement)
        if quality is None or not quality.success:
            return "failed", False, "QUALITY_EVIDENCE_FAILED"
        counts = quality.data["condition_counts_quality_usable"]
        requested = tuple(goal.arguments["labels"])
        sufficient = all(
            counts.get(label, 0) >= requirement.min_usable_epochs_per_condition
            for label in requested
        )
        trace.append({
            "decision": "evaluate_epoch_coverage",
            "evidence_id": quality.data["evidence_id"],
            "usable_counts": counts,
            "required_per_condition": requirement.min_usable_epochs_per_condition,
        })
        if not sufficient:
            return "insufficient_evidence", False, "INSUFFICIENT_EVIDENCE"
        selected_id = artifact_id
        if quality.data["epoch_counts"]["quality_flagged"] and self.mode != "fixed":
            selected = self._execute(
                "select_quality_epochs", {"artifact_id": artifact_id}, results, requirement
            )
            if selected is None or not selected.success:
                return "failed", False, "QUALITY_SELECTION_FAILED"
            selected_id = selected.data["artifact_id"]
        analysis = self._execute("event_bandpower", {"artifact_id": selected_id}, results, requirement)
        if analysis is None:
            return "budget_exhausted", False, "BUDGET_EXHAUSTED"
        if not analysis.success:
            return "failed", False, analysis.error_code
        satisfied = not quality.data["epoch_counts"]["quality_flagged"] or self.mode != "fixed"
        return "completed", satisfied, None if satisfied else "QUALITY_REQUIREMENT_NOT_MET"

    def run(self, goal):
        started = time.perf_counter()
        results, trace = [], [{
            "decision": "start",
            "mode": self.mode,
            "goal_id": goal.goal_id,
            "max_tool_calls": goal.requirement.max_tool_calls,
        }]
        if goal.kind == "window_psd":
            status, satisfied, reason = self._window(goal, results, trace)
        elif goal.kind == "event_bandpower":
            status, satisfied, reason = self._event(goal, results, trace)
        else:
            status, satisfied, reason = "rejected", False, "UNSUPPORTED_EVIDENCE_GOAL"
        trace.append({"decision": "stop", "status": status, "reason_code": reason})
        return EvidencePolicyResult(
            status, satisfied, tuple(results), tuple(trace), reason,
            round((time.perf_counter() - started) * 1000, 3),
        )
