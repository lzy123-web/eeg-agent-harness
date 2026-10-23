"""Compile grounded IntentSpec values into plans and persistent obligations."""

from dataclasses import dataclass, field
import json
from typing import Any, Mapping

from ...planning import TaskSpec


FORBIDDEN_TOOL_MAP = {
    "selection": "select_quality_epochs",
    "epoch_selection": "select_quality_epochs",
    "event_analysis": "event_bandpower",
    "amplitude": "amplitude",
    "psd": "psd",
}


def _forbidden_tools(values):
    tools = []
    for value in values:
        normalized = value.casefold().replace("-", "_").replace(" ", "_")
        direct = FORBIDDEN_TOOL_MAP.get(normalized)
        if direct:
            tools.append(direct)
        if "selection" in normalized or "筛" in normalized:
            tools.append("select_quality_epochs")
    return tuple(dict.fromkeys(tools))


@dataclass(frozen=True)
class Obligation:
    obligation_id: str
    kind: str
    expected: Any
    source_quote: str = ""

    def to_dict(self):
        return {
            "obligation_id": self.obligation_id, "kind": self.kind,
            "expected": self.expected, "source_quote": self.source_quote,
        }


@dataclass(frozen=True)
class ObligationLedger:
    context_id: str
    analysis_type: str
    obligations: tuple[Obligation, ...]
    forbidden_tools: tuple[str, ...] = ()

    def to_dict(self):
        payload = {
            "context_id": self.context_id, "analysis_type": self.analysis_type,
            "obligations": [item.to_dict() for item in self.obligations],
            "forbidden_tools": list(self.forbidden_tools),
        }
        json.dumps(payload, ensure_ascii=False, allow_nan=False)
        return payload


def compile_intent(intent, context):
    params = dict(intent.parameters)
    analysis = intent.analysis_type
    if analysis in {"record_info", "record_quality", "amplitude", "psd", "seizure_detection"}:
        task = TaskSpec(
            "tool",
            {"tool_name": analysis, "parameters": params},
            task_id="point1-task",
        )
    elif analysis in {"event_bandpower", "epoch_quality", "select_quality_epochs"}:
        task = TaskSpec(analysis, params, task_id="point1-task")
    elif analysis == "quality_selection":
        task = TaskSpec("quality_selection", params, task_id="point1-task")
    elif analysis == "quality_selected_bandpower":
        task = TaskSpec("quality_selected_bandpower", params, task_id="point1-task")
    else:
        task = TaskSpec("unsupported", params, task_id="point1-task")
    obligations = [
        Obligation("analysis", "analysis_type", analysis, intent.explicit_evidence.get("analysis_type", "")),
        Obligation("source", "source_stage", intent.source_stage, intent.explicit_evidence.get("source_stage", "")),
    ]
    for key, value in params.items():
        obligations.append(Obligation(
            f"parameter:{key}", "parameter", {"name": key, "value": value},
            intent.explicit_evidence.get(key, ""),
        ))
    expected_tools = {
        "event_bandpower": ["list_events", "create_epochs", "event_bandpower"],
        "epoch_quality": ["list_events", "create_epochs", "epoch_quality"],
        "quality_selection": ["list_events", "create_epochs", "epoch_quality", "select_quality_epochs"],
        "quality_selected_bandpower": [
            "list_events", "create_epochs", "epoch_quality",
            "select_quality_epochs", "event_bandpower",
        ],
    }.get(analysis, [analysis])
    obligations.append(Obligation("evidence", "successful_tools", expected_tools))
    forbidden = _forbidden_tools(intent.forbidden_operations)
    return task, ObligationLedger(context.task_id, analysis, tuple(obligations), forbidden)


def validate_plan_against_ledger(plan, ledger):
    if plan.status != "ready":
        return {"valid": False, "code": plan.reason_code or "PLAN_REJECTED", "violations": []}
    names = [step.tool_name for step in plan.steps]
    violations = [f"forbidden_tool:{name}" for name in names if name in ledger.forbidden_tools]
    parameter_values = {
        item.expected["name"]: item.expected["value"]
        for item in ledger.obligations if item.kind == "parameter"
    }
    for key, expected in parameter_values.items():
        if key == "selection_authorized":
            continue
        relevant = [step for step in plan.steps if key in step.arguments]
        if not relevant:
            violations.append(f"parameter_missing_from_plan:{key}")
        elif any(step.arguments[key] != expected for step in relevant):
            violations.append(f"parameter_changed:{key}")
    return {
        "valid": not violations,
        "code": None if not violations else "OBLIGATION_VIOLATION",
        "violations": violations,
        "planned_tools": names,
    }


def close_ledger(ledger, execution):
    results = execution.tool_results
    successful = [item["tool_name"] for item in results if item["success"]]
    expected_tools = next(
        item.expected for item in ledger.obligations if item.kind == "successful_tools"
    )
    violations = []
    for tool in expected_tools:
        if tool not in successful:
            violations.append(f"missing_successful_tool:{tool}")
    for item in results:
        if item["success"] and item["tool_name"] in ledger.forbidden_tools:
            violations.append(f"forbidden_tool_executed:{item['tool_name']}")
    events = execution.execution_trace.get("events", [])
    parameter_values = {
        item.expected["name"]: item.expected["value"]
        for item in ledger.obligations if item.kind == "parameter"
    }
    for key, expected in parameter_values.items():
        if key == "selection_authorized":
            continue
        seen = [event["arguments"][key] for event in events if key in event.get("arguments", {})]
        if not seen:
            violations.append(f"executed_parameter_missing:{key}")
        elif any(value != expected for value in seen):
            violations.append(f"executed_parameter_changed:{key}")
    event_by_request = {event["request_id"]: event for event in events}
    produced_ids = set()
    for item in results:
        if not item["success"]:
            continue
        event = event_by_request.get(item["request_id"], {})
        if item["tool_name"] in {"event_bandpower", "epoch_quality", "select_quality_epochs"}:
            if event.get("arguments", {}).get("artifact_id") not in produced_ids:
                violations.append("artifact_lineage_mismatch")
        if item["tool_name"] in {"create_epochs", "select_quality_epochs"}:
            artifact_id = item.get("data", {}).get("artifact_id")
            if artifact_id:
                produced_ids.add(artifact_id)
    return {
        "closed": execution.status == "completed" and not violations,
        "violations": violations,
        "successful_tools": successful,
        "termination_status": execution.status,
    }
