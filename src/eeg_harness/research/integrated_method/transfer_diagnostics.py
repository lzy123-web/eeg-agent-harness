"""Matched-information diagnostics for the CIEDG reference transfer gate."""

from copy import deepcopy
from hashlib import sha256
import json

from ...tooling import ToolRequest


class ExpireRereferencedArtifactBeforeBandpower:
    """One-shot, method-independent controlled artifact-loss fault."""

    def __init__(self, base):
        self.base = base
        self.registry = base.registry
        self.config = base.config
        self.resources = base.resources
        self.applied = False

    def execute(self, record, profile, request, session_resources=None):
        if request.name == "event_bandpower" and not self.applied:
            self.applied = True
            (session_resources or {}).get("artifact_store", {}).pop(
                request.arguments["artifact_id"], None,
            )
        return self.base.execute(record, profile, request, session_resources)


def _semantic_release_view(result, effective):
    """Release cached content under a new identity without rewriting history."""

    released = deepcopy(result)
    old_request_id = released["request_id"]
    identity = {
        "tool_name": released["tool_name"],
        "old_request_id": old_request_id,
        "artifact_id": effective["artifact_id"],
        "artifact_fingerprint": effective["expected_artifact_fingerprint"],
    }
    suffix = sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:12]
    released["request_id"] = f"expert-reuse-{suffix}"
    released["execution_kind"] = "semantic_evidence_reuse"
    released["reused_from_request_id"] = old_request_id
    released["data"]["artifact_id"] = effective["artifact_id"]
    released["data"]["artifact_fingerprint"] = effective[
        "expected_artifact_fingerprint"
    ]
    released["data"]["evidence_reuse"] = {
        "equivalent_content": True,
        "reused_from_request_id": old_request_id,
        "current_artifact_id": effective["artifact_id"],
        "current_artifact_fingerprint": effective[
            "expected_artifact_fingerprint"
        ],
    }
    return released


def run_guarded_transfer_expert(
    context, *, labels, tmin, tmax, reference_channels,
    rereference_authorized=False,
    objectives=("epoch_quality", "epoch_summary", "event_bandpower"),
    max_repairs=2, max_tool_calls=16,
):
    """Run a procedural Expert with the candidate's tools, rules and feedback."""

    results = []
    release_by_goal = {}
    sequence = 0
    repairs = 0

    def execute(name, arguments):
        nonlocal sequence
        if sequence >= max_tool_calls:
            return None
        sequence += 1
        rendered = context.execute(ToolRequest(
            name, arguments, request_id=f"transfer-expert-{sequence}-{name}",
        )).to_dict()
        results.append(rendered)
        return rendered

    def fail(code, message):
        return {
            "status": "blocked", "reason": {"code": code, "message": message},
            "tool_results": results,
            "release_results": list(release_by_goal.values()),
            "repair_count": repairs,
        }

    if not rereference_authorized:
        return fail("REREFERENCE_NOT_AUTHORIZED", "explicit authorization is absent")
    if not reference_channels:
        return fail("REFERENCE_CHANNELS_REQUIRED", "reference channels are absent")

    observed = execute("list_events", {})
    if not observed or not observed["success"]:
        return fail("ACTION_FAILED", "list_events failed")
    created = execute("create_epochs", {
        "labels": list(labels), "tmin": tmin, "tmax": tmax,
    })
    if not created or not created["success"]:
        return fail("ACTION_FAILED", "create_epochs failed")
    source = {
        "artifact_id": created["data"]["artifact_id"],
        "expected_artifact_fingerprint": created["data"]["artifact_fingerprint"],
    }

    def transition():
        result = execute("rereference_epochs", {
            **source, "reference_channels": list(reference_channels),
        })
        if not result or not result["success"]:
            return None
        return {
            "artifact_id": result["data"]["artifact_id"],
            "expected_artifact_fingerprint": result["data"]["artifact_fingerprint"],
        }

    effective = transition()
    if effective is None:
        return fail("ACTION_FAILED", "rereference_epochs failed")

    def consume(goal, tool):
        result = execute(tool, effective)
        if result and result["success"]:
            release_by_goal[goal] = result
        return result

    quality = None
    if "epoch_quality" in objectives:
        quality = consume("epoch_quality", "epoch_quality")
        if not quality or not quality["success"]:
            return fail("ACTION_FAILED", "epoch_quality failed")
    summary = None
    if "epoch_summary" in objectives:
        summary = consume("epoch_summary", "epoch_summary")
        if not summary or not summary["success"]:
            return fail("ACTION_FAILED", "epoch_summary failed")
    if "event_bandpower" in objectives:
        power = consume("event_bandpower", "event_bandpower")
        if not power or not power["success"]:
            error_code = (power.get("error") or {}).get("code") if power else None
            recoverable = error_code in {
                "ARTIFACT_NOT_FOUND", "ARTIFACT_STATE_CONFLICT",
            }
            if not recoverable or repairs >= max_repairs:
                return fail("ACTION_FAILED", "event_bandpower failed")
            repairs += 1
            old_fingerprint = effective["expected_artifact_fingerprint"]
            effective = transition()
            if effective is None:
                return fail("RECOVERY_FAILED", "rereference recovery failed")
            content_equivalent = (
                effective["expected_artifact_fingerprint"] == old_fingerprint
            )
            if "epoch_quality" in objectives:
                quality = consume("epoch_quality", "epoch_quality")
                if not quality or not quality["success"]:
                    return fail("RECOVERY_FAILED", "quality recovery failed")
            if summary is not None and content_equivalent:
                release_by_goal["epoch_summary"] = _semantic_release_view(
                    summary, effective,
                )
            elif summary is not None:
                summary = consume("epoch_summary", "epoch_summary")
                if not summary or not summary["success"]:
                    return fail("RECOVERY_FAILED", "summary recovery failed")
            power = consume("event_bandpower", "event_bandpower")
            if not power or not power["success"]:
                return fail("RECOVERY_FAILED", "bandpower recovery failed")

    return {
        "status": "completed", "reason": None, "tool_results": results,
        "release_results": list(release_by_goal.values()),
        "effective_artifact_id": effective["artifact_id"],
        "effective_artifact_fingerprint": effective[
            "expected_artifact_fingerprint"
        ],
        "repair_count": repairs,
    }
