"""Strong procedural Expert extension with matched tool, evidence and budgets."""

from copy import deepcopy
from hashlib import sha256
import json

from ...tooling import ToolRequest


def _release_view(result, bound):
    released = deepcopy(result)
    old = released["request_id"]
    suffix = sha256(json.dumps(bound, sort_keys=True).encode()).hexdigest()[:12]
    released["request_id"] = f"expert-ext-reuse-{suffix}"
    released["execution_kind"] = "semantic_evidence_reuse"
    released["reused_from_request_id"] = old
    released["data"]["artifact_id"] = bound["artifact_id"]
    released["data"]["artifact_fingerprint"] = bound["fingerprint"]
    released["data"]["evidence_reuse"] = {
        "source_request_id": old,
        "current_artifact_id": bound["artifact_id"],
        "current_artifact_fingerprint": bound["fingerprint"],
        "scientific_content_equivalent": True,
    }
    return released


def run_expert_extension(case, context, *, max_tool_calls=16, max_repairs=2):
    """Execute the frozen workflow with a table-driven read-only consumer set."""

    params = case["task"]["parameters"]
    objectives = tuple(case["task"]["objectives"])
    results, releases, trace = [], {}, []
    calls = 0
    repairs = 0

    def execute(name, arguments):
        nonlocal calls
        if calls >= max_tool_calls:
            return None
        calls += 1
        result = context.execute(ToolRequest(
            name, arguments, request_id=f"expert-ext-{calls}-{name}",
        )).to_dict()
        results.append(result)
        trace.append({
            "event": "expert_action", "tool": name, "success": result["success"],
            "error_code": None if result["success"] else result["error"]["code"],
        })
        return result

    def binding(result):
        return {
            "artifact_id": result["data"]["artifact_id"],
            "fingerprint": result["data"]["artifact_fingerprint"],
        }

    def arguments(bound):
        return {
            "artifact_id": bound["artifact_id"],
            "expected_artifact_fingerprint": bound["fingerprint"],
        }

    def fail(code, message):
        return {
            "method": "strong_dynamic_expert+extension", "status": "execution_failed",
            "tool_results": results, "release_results": list(releases.values()),
            "scientific_state": {"blocked": {"code": code, "message": message}},
            "planning_trace": trace, "repairs": repairs,
        }

    observed = execute("list_events", {})
    if not observed or not observed["success"]:
        return fail("ACTION_FAILED", "list_events failed")
    epoch_args = {
        "labels": list(params["labels"]), "tmin": params["tmin"], "tmax": params["tmax"],
    }
    created = execute("create_epochs", epoch_args)
    if not created or not created["success"]:
        return fail("ACTION_FAILED", "create_epochs failed")
    source = binding(created)
    effective = dict(source)
    quality = None
    transition = "none"

    def source_valid():
        artifact = context.artifacts.get(source["artifact_id"])
        return artifact is not None and artifact.content_fingerprint() == source["fingerprint"]

    def do_reference():
        result = execute("rereference_epochs", {
            **arguments(source), "reference_channels": list(params["reference_channels"]),
        })
        if result and result["success"]:
            releases["epoch_rereference"] = result
            return binding(result)
        return None

    def do_quality(bound):
        result = execute("epoch_quality", arguments(bound))
        if result and result["success"]:
            releases["epoch_quality"] = result
        return result

    def do_selection(bound, quality_result):
        usable = quality_result["data"]["condition_counts_quality_usable"]
        if any(usable.get(label, 0) < 1 for label in params["labels"]):
            return None
        if quality_result["data"]["epoch_counts"]["quality_flagged"] == 0:
            return bound
        result = execute("select_quality_epochs", {
            **arguments(bound),
            "expected_quality_evidence_id": quality_result["data"]["evidence_id"],
        })
        if result and result["success"]:
            releases["trial_selection"] = result
            return binding(result)
        return None

    if "epoch_rereference" in objectives:
        effective = do_reference()
        transition = "epoch_rereference"
        if effective is None:
            return fail("ACTION_FAILED", "rereference failed")
    if "epoch_quality" in objectives or "trial_selection" in objectives:
        quality = do_quality(effective if "epoch_rereference" in objectives else source)
        if not quality or not quality["success"]:
            return fail("ACTION_FAILED", "quality failed")
    if "trial_selection" in objectives:
        if params.get("selection_authorized") is not True:
            return fail("SELECTION_NOT_AUTHORIZED", "selection authorization absent")
        effective = do_selection(source, quality)
        if effective is None:
            return fail("ACTION_FAILED", "selection failed")
        transition = "identity" if effective == source else "derived"

    # EXTENSION_DELTA_START
    consumer_tools = tuple(
        name for name in ("epoch_variance", "event_bandpower") if name in objectives
    )
    completed_consumers = {}
    for tool_name in consumer_tools:
        result = execute(tool_name, arguments(effective))
        if result and not result["success"] and result["error"]["code"] == "INJECTED_TRANSIENT_FAILURE":
            result = execute(tool_name, arguments(effective))
        if result and not result["success"] and result["error"]["code"] in {
            "ARTIFACT_NOT_FOUND", "ARTIFACT_STATE_CONFLICT",
        } and repairs < max_repairs:
            repairs += 1
            old_fingerprint = effective["fingerprint"]
            if not source_valid():
                created = execute("create_epochs", epoch_args)
                if not created or not created["success"]:
                    return fail("RECOVERY_FAILED", "source rebuild failed")
                source = binding(created)
            if "epoch_rereference" in objectives:
                effective = do_reference()
            elif "trial_selection" in objectives:
                if source["fingerprint"] != quality["data"]["artifact_fingerprint"]:
                    quality = do_quality(source)
                effective = do_selection(source, quality)
            else:
                effective = source
            if effective is None:
                return fail("RECOVERY_FAILED", "effective artifact rebuild failed")
            for prior_name, prior_result in tuple(completed_consumers.items()):
                if effective["fingerprint"] == old_fingerprint:
                    completed_consumers[prior_name] = _release_view(prior_result, effective)
                else:
                    recomputed = execute(prior_name, arguments(effective))
                    if not recomputed or not recomputed["success"]:
                        return fail("RECOVERY_FAILED", f"{prior_name} recompute failed")
                    completed_consumers[prior_name] = recomputed
            result = execute(tool_name, arguments(effective))
        if not result or not result["success"]:
            return fail("ACTION_FAILED", f"{tool_name} failed")
        completed_consumers[tool_name] = result

    releases.update(completed_consumers)
    # EXTENSION_DELTA_END
    return {
        "method": "strong_dynamic_expert+extension", "status": "completed",
        "tool_results": results, "release_results": list(releases.values()),
        "scientific_state": {
            "transition": transition,
            "artifacts": {
                "source": source["artifact_id"], "effective": effective["artifact_id"],
                "effective_fingerprint": effective["fingerprint"],
            },
            "repairs": repairs,
        },
        "planning_trace": trace, "repairs": repairs,
    }
