"""Frozen, method-independent fault injection at the real Executor boundary."""

import numpy as np

from ...tooling import ToolResult


class FormalFaultExecutor:
    def __init__(self, base, kind):
        self.base = base
        self.kind = kind
        self.registry = base.registry
        self.config = base.config
        self.resources = base.resources
        self.applied = False

    def execute(self, record, profile, request, session_resources=None):
        if request.name == "event_bandpower" and not self.applied:
            self.applied = True
            store = (session_resources or {}).get("artifact_store", {})
            if self.kind == "effective_artifact_expiry":
                store.pop(request.arguments["artifact_id"], None)
            elif self.kind == "same_id_changed_content":
                record.data[0] += np.float32(1e-6)
                store.clear()
            elif self.kind == "different_id_equal_content":
                store.clear()
            elif self.kind == "one_shot_bandpower_failure":
                return ToolResult(
                    request.request_id, request.name, False,
                    error_code="INJECTED_TRANSIENT_FAILURE",
                    error_message="Frozen one-shot formal evaluation failure",
                )
        return self.base.execute(record, profile, request, session_resources)


def apply_fault(context, case):
    kind = case["fault"]["kind"]
    if kind != "none":
        context.executor = FormalFaultExecutor(context.executor, kind)
    return context
