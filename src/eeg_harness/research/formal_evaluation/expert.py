"""Strong procedural dynamic Expert with matched rules, feedback and budget."""

from copy import deepcopy
from hashlib import sha256
import json

from ...planning import StateAwareConstrainedPlanner
from ...tooling import ToolRequest
from ..integrated_method.contracts import compile_intent
from ..integrated_method.intent import IntentSpec


def _release_view(result, binding):
    released = deepcopy(result)
    old = released["request_id"]
    suffix = sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()[:12]
    released["request_id"] = f"expert-reuse-{suffix}"
    released["execution_kind"] = "semantic_evidence_reuse"
    released["reused_from_request_id"] = old
    released["data"]["artifact_id"] = binding["artifact_id"]
    released["data"]["artifact_fingerprint"] = binding["fingerprint"]
    released["data"]["evidence_reuse"] = {
        "source_request_id": old,
        "current_artifact_id": binding["artifact_id"],
        "current_artifact_fingerprint": binding["fingerprint"],
        "scientific_content_equivalent": True,
    }
    return released


def _parsed_intent(case):
    task = case["task"]
    evidence = {key: case["request"] for key in task.get("parameters", {})}
    evidence["analysis_type"] = case["request"]
    return IntentSpec(
        "event_workflow", tuple(task.get("objectives", ())),
        dict(task.get("parameters", {})), explicit_evidence=evidence,
        semantic_evidence={"event_locked": case["request"]},
        forbidden_operations=tuple(task.get("forbidden_operations", ())),
    )


def run_strong_expert(case, context, *, max_tool_calls=16, max_repairs=2):
    """Execute both frozen state families without offline gold access."""

    if case["task"]["disposition"] != "execute":
        return {
            "method": "strong_dynamic_expert", "status": "clarification_required",
            "tool_results": [], "release_results": [], "scientific_state": {},
            "planning_trace": [], "repairs": 0,
        }
    intent = _parsed_intent(case)
    task, _ = compile_intent(intent, context)
    preflight = StateAwareConstrainedPlanner(context).plan(task)
    if preflight.status != "ready":
        return {
            "method": "strong_dynamic_expert", "status": "rejected",
            "plan": preflight.to_dict(), "tool_results": [], "release_results": [],
            "scientific_state": {"blocked": {
                "code": preflight.error_code, "message": preflight.error_message,
            }}, "planning_trace": [], "repairs": 0,
        }

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
            name, arguments, request_id=f"expert-{calls}-{name}",
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

    def fail(status, code, message):
        return {
            "method": "strong_dynamic_expert", "status": status,
            "tool_results": results, "release_results": list(releases.values()),
            "scientific_state": {
                "blocked": {"code": code, "message": message},
                "repairs": repairs,
            }, "planning_trace": trace, "repairs": repairs,
        }

    observed = execute("list_events", {})
    if not observed or not observed["success"]:
        return fail("execution_failed", "ACTION_FAILED", "list_events failed")
    epoch_args = {
        "labels": list(params["labels"]), "tmin": params["tmin"], "tmax": params["tmax"],
    }
    created = execute("create_epochs", epoch_args)
    if not created or not created["success"]:
        return fail("execution_failed", "ACTION_FAILED", "create_epochs failed")
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
        return None if not result or not result["success"] else binding(result)

    def do_quality(bound):
        result = execute("epoch_quality", arguments(bound))
        if result and result["success"]:
            releases["epoch_quality"] = result
        return result

    def do_selection(bound, quality_result):
        usable = quality_result["data"]["condition_counts_quality_usable"]
        missing = [label for label in params["labels"] if usable.get(label, 0) < 1]
        if missing:
            return "blocked", missing
        if quality_result["data"]["epoch_counts"]["quality_flagged"] == 0:
            return bound, None
        result = execute("select_quality_epochs", {
            **arguments(bound),
            "expected_quality_evidence_id": quality_result["data"]["evidence_id"],
        })
        if not result or not result["success"]:
            return None, None
        releases["trial_selection"] = result
        return binding(result), None

    if "epoch_rereference" in objectives:
        effective = do_reference()
        transition = "epoch_rereference"
        if effective is None:
            return fail("execution_failed", "ACTION_FAILED", "rereference failed")
    if "epoch_quality" in objectives or "trial_selection" in objectives:
        quality = do_quality(effective if "epoch_rereference" in objectives else source)
        if not quality or not quality["success"]:
            return fail("execution_failed", "ACTION_FAILED", "quality failed")
    if "trial_selection" in objectives:
        effective, missing = do_selection(source, quality)
        if effective == "blocked":
            return fail(
                "scientifically_blocked", "NO_USABLE_EPOCHS_FOR_CONDITION",
                "No quality-usable Epoch for: " + ", ".join(missing),
            )
        if effective is None:
            return fail("execution_failed", "ACTION_FAILED", "selection failed")
        transition = "identity" if effective == source else "derived"

    summary = None
    if "epoch_summary" in objectives:
        summary = execute("epoch_summary", arguments(effective))
        if not summary or not summary["success"]:
            return fail("execution_failed", "ACTION_FAILED", "summary failed")
        releases["epoch_summary"] = summary

    if "event_bandpower" in objectives:
        power = execute("event_bandpower", arguments(effective))
        if not power or not power["success"]:
            code = None if not power else power["error"]["code"]
            if code == "INJECTED_TRANSIENT_FAILURE":
                power = execute("event_bandpower", arguments(effective))
            elif code in {"ARTIFACT_NOT_FOUND", "ARTIFACT_STATE_CONFLICT"} and repairs < max_repairs:
                repairs += 1
                old_fingerprint = effective["fingerprint"]
                if not source_valid():
                    created = execute("create_epochs", epoch_args)
                    if not created or not created["success"]:
                        return fail("execution_failed", "RECOVERY_FAILED", "source rebuild failed")
                    source = binding(created)
                    if "trial_selection" in objectives:
                        quality = do_quality(source)
                if "epoch_rereference" in objectives:
                    effective = do_reference()
                    quality = do_quality(effective) if "epoch_quality" in objectives else None
                elif "trial_selection" in objectives:
                    effective, missing = do_selection(source, quality)
                else:
                    effective = source
                if effective is None or effective == "blocked":
                    return fail("execution_failed", "RECOVERY_FAILED", "transition rebuild failed")
                if summary is not None:
                    if effective["fingerprint"] == old_fingerprint:
                        releases["epoch_summary"] = _release_view(summary, effective)
                    else:
                        summary = execute("epoch_summary", arguments(effective))
                        if not summary or not summary["success"]:
                            return fail("execution_failed", "RECOVERY_FAILED", "summary rebuild failed")
                        releases["epoch_summary"] = summary
                power = execute("event_bandpower", arguments(effective))
            if not power or not power["success"]:
                return fail("execution_failed", "ACTION_FAILED", "bandpower failed")
        releases["event_bandpower"] = power

    return {
        "method": "strong_dynamic_expert", "status": "completed",
        "tool_results": results, "release_results": list(releases.values()),
        "scientific_state": {
            "transition": transition,
            "artifacts": {
                "source": source["artifact_id"],
                "effective": effective["artifact_id"],
                "effective_fingerprint": effective["fingerprint"],
            },
            "repairs": repairs,
        },
        "planning_trace": trace, "repairs": repairs,
    }
