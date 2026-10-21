"""Deterministic multi-tool workflow entry point."""

from .context import ExecutionContext
from .edf import load_edf
from .executor import Executor
from .tooling import ToolRequest
from .tools import build_default_registry


def run_workflow(
    edf_path,
    profile,
    config,
    channel,
    start=0,
    end=1,
    model_path=None,
    native_channels=None,
):
    record = load_edf(edf_path, profile, selected_channels=native_channels)
    resources = {"seizure_model": model_path} if model_path else {}
    context = ExecutionContext(
        record,
        profile,
        Executor(build_default_registry(), config, resources=resources),
        task_id="deterministic-eeg-workflow",
    )
    requests = [
        ToolRequest("record_info", {}, request_id="record-info"),
        ToolRequest(
            "psd",
            {"channels": [channel], "start": start, "end": end},
            request_id="band-power",
        ),
    ]
    if profile.supports_tool("seizure_detection"):
        requests.append(
            ToolRequest(
                "seizure_detection",
                {"channels": [channel], "start": start, "end": end},
                request_id="seizure-model",
            )
        )
    context.execute_many(requests, continue_on_error=True)
    return context.reproducibility_bundle()

