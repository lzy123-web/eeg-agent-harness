"""Versioned outcome and budget semantics for planning comparisons."""

from dataclasses import dataclass


COMPLETED = "completed"
REJECTED_PREFLIGHT = "rejected_preflight"
REJECTED_EXECUTOR = "rejected_executor"
RECOVERED_TRANSIENT = "recovered_transient"
FAILED = "failed"


@dataclass(frozen=True)
class EvaluationBudget:
    """Execution limits shared by compared planning policies."""

    max_tool_calls: int = 8
    max_state_checks: int = 8
    max_recoveries: int = 1


DEFAULT_BUDGET = EvaluationBudget()


def classify_outcome(expected, status, *, preflight_rejected=False, recoveries=0):
    """Classify an outcome without treating Executor rejection as unsafe execution."""

    if expected == "complete" and status == "completed":
        return RECOVERED_TRANSIENT if recoveries else COMPLETED
    if expected == "reject" and status == "rejected":
        return REJECTED_PREFLIGHT if preflight_rejected else REJECTED_EXECUTOR
    if expected == "reject" and status == "execution_failed":
        return REJECTED_EXECUTOR
    return FAILED
