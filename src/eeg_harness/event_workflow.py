"""Deterministic event-related workflow on the shared Harness runtime."""

from .context import ExecutionContext
from .executor import Executor
from .tooling import ToolRequest
from .tools import build_default_registry


def run_event_workflow(record, profile, config, labels, tmin, tmax, baseline=None):
    context = ExecutionContext(
        record,
        profile,
        Executor(build_default_registry(), config),
        task_id="deterministic-event-workflow",
    )
    create_arguments = {"labels": list(labels), "tmin": tmin, "tmax": tmax}
    if baseline is not None:
        create_arguments["baseline"] = list(baseline)
    requests = [
        ToolRequest("list_events", {}, request_id="list-events"),
        ToolRequest("create_epochs", create_arguments, request_id="create-epochs"),
        ToolRequest(
            "epoch_summary",
            {"artifact_id": {"$result": "create-epochs", "path": ["artifact_id"]}},
            request_id="epoch-summary",
        ),
        ToolRequest(
            "event_bandpower",
            {"artifact_id": {"$result": "create-epochs", "path": ["artifact_id"]}},
            request_id="event-bandpower",
        ),
    ]
    context.execute_many(requests, continue_on_error=False)
    return context.reproducibility_bundle()

