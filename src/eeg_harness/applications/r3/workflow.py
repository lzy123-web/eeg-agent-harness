"""R3 workflow that reuses the shared Registry, Executor and ExecutionContext."""

from ...context import ExecutionContext
from ...executor import Executor
from ...tooling import ToolRequest
from ...tools import build_default_registry
from .adapter import R3DatasetRules, R3_PROFILE, load_r3_edf


def run_r3_event_workflow(edf_path, config, rules=None, include_quality=False):
    rules = rules or R3DatasetRules()
    record = load_r3_edf(edf_path)
    context = ExecutionContext(
        record,
        R3_PROFILE,
        Executor(build_default_registry(), config),
        task_id="r3-event-workflow",
    )
    create_arguments = {
        "labels": list(rules.analysis_labels),
        "tmin": rules.epoch_window[0],
        "tmax": rules.epoch_window[1],
        "baseline": list(rules.baseline),
    }
    requests = [
        ToolRequest("list_events", {}, "list-events"),
        ToolRequest("create_epochs", create_arguments, "create-epochs"),
        ToolRequest(
            "epoch_summary",
            {"artifact_id": {"$result": "create-epochs", "path": ["artifact_id"]}},
            "epoch-summary",
        ),
    ]
    if include_quality:
        requests.extend([
            ToolRequest("record_quality", {}, "record-quality"),
            ToolRequest(
                "epoch_quality",
                {"artifact_id": {"$result": "create-epochs", "path": ["artifact_id"]}},
                "epoch-quality",
            ),
        ])
    requests.append(
        ToolRequest(
            "event_bandpower",
            {"artifact_id": {"$result": "create-epochs", "path": ["artifact_id"]}},
            "event-bandpower",
        )
    )
    context.execute_many(requests, continue_on_error=False)
    bundle = context.reproducibility_bundle()
    bundle["application"] = {
        "name": "r3",
        "analysis_labels": list(rules.analysis_labels),
        "excluded_boundary_labels": list(rules.boundary_labels),
        "boundary_rule_status": rules.boundary_rule_status,
        "scientific_interpretation": "unverified",
    }
    return bundle


def public_workflow_summary(bundle):
    """Strip record-level features and identifiers from a shareable summary."""

    create_result = next(
        item for item in bundle["results"] if item["tool_name"] == "create_epochs"
    )
    event_result = next(
        item for item in bundle["results"] if item["tool_name"] == "list_events"
    )
    return {
        "schema_version": bundle["schema_version"],
        "harness_version": bundle["harness_version"],
        "profile_id": bundle["record"]["profile_id"],
        "source": bundle["record"]["source"],
        "sfreq": bundle["record"]["sfreq"],
        "channel_count": len(bundle["record"]["channel_names"]),
        "event_count": event_result["data"]["event_count"],
        "valid_epoch_count": create_result["data"]["valid_epoch_count"],
        "rejected_epoch_count": create_result["data"]["rejected_epoch_count"],
        "termination_reason": bundle["trace"]["termination_reason"],
        "contains_record_level_features": False,
        "quality_tools_succeeded": all(
            item["success"] for item in bundle["results"]
            if item["tool_name"] in {"record_quality", "epoch_quality"}
        ) if any(
            item["tool_name"] in {"record_quality", "epoch_quality"}
            for item in bundle["results"]
        ) else None,
    }
