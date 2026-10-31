"""Append-only, cross-process Issue #39 external-call budget.

Every attempted call is reserved before network I/O. An interrupted call keeps
its conservative reservation until manually audited; no process may silently
restart with a fresh quota. The ledger belongs only in ignored artifacts/.
"""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import time
import uuid


class StageBudgetExhausted(RuntimeError):
    pass


@contextmanager
def _ledger_lock(path):
    lock = Path(str(path) + ".lock")
    deadline = time.monotonic() + 5.0
    while True:
        try:
            handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(handle)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise StageBudgetExhausted("Issue39 ledger is locked; inspect before retry")
            time.sleep(0.1)
    try:
        yield
    finally:
        lock.unlink()


def _append(path, row):
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _rows(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def ledger_totals(path):
    rows = _rows(path)
    starts = {row["request_id"]: row for row in rows if row["event"] == "reserved"}
    finishes = {row["request_id"]: row for row in rows
                if row["event"] in {"received", "failed"}}
    charged = sum((finishes[ident].get("total_tokens")
                   if ident in finishes and finishes[ident].get("total_tokens") is not None
                   else start["reserved_tokens"])
                  for ident, start in starts.items())
    actual = sum(row.get("total_tokens") or 0 for row in finishes.values())
    return {"attempts": len(starts), "charged_tokens": charged,
            "reported_tokens": actual,
            "unresolved_attempts": sum(ident not in finishes for ident in starts)}


class Issue39BudgetClient:
    """Wrap a journaled LLM client without changing the common action protocol."""

    def __init__(self, client, ledger, *, max_requests=160, max_tokens=300000,
                 model_label=None, phase=None, phase_request_cap=None):
        self.client = client
        self.ledger = Path(ledger)
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        self.max_requests = int(max_requests)
        self.max_tokens = int(max_tokens)
        self.context = {"phase": phase} if phase else {}
        self.phase_request_cap = phase_request_cap
        if self.max_requests < 1 or self.max_tokens < 1:
            raise ValueError("Issue39 limits must be positive")
        with _ledger_lock(self.ledger):
            rows = _rows(self.ledger)
            if not rows:
                _append(self.ledger, {"event": "opened", "version": 1,
                                      "max_requests": self.max_requests,
                                      "max_tokens": self.max_tokens,
                                      "model_requested": model_label})
            elif (rows[0].get("event") != "opened"
                  or rows[0].get("max_requests") != self.max_requests
                  or rows[0].get("max_tokens") != self.max_tokens):
                raise StageBudgetExhausted("Issue39 ledger limits differ; do not reset")

    @property
    def request_count(self):
        return self.client.request_count

    @property
    def total_usage(self):
        return self.client.total_usage

    @property
    def model(self):
        return self.client.model

    def set_context(self, **context):
        self.context = {**self.context, **context}

    def complete(self, messages, tools, tool_choice="auto"):
        # UTF-8 byte count is a deliberately conservative input-token ceiling
        # for byte-level tokenizers; output cap comes from the real client.
        payload = json.dumps({"messages": messages, "tools": tools,
                              "tool_choice": tool_choice},
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
        output_cap = self.client.client.max_tokens
        reserve = len(payload) + output_cap
        ident = uuid.uuid4().hex
        with _ledger_lock(self.ledger):
            totals = ledger_totals(self.ledger)
            phase_attempts = sum(row.get("event") == "reserved"
                                 and row.get("context", {}).get("phase") ==
                                 self.context.get("phase") for row in _rows(self.ledger))
            if (totals["attempts"] >= self.max_requests
                    or totals["charged_tokens"] + reserve > self.max_tokens
                    or self.phase_request_cap is not None
                    and phase_attempts >= self.phase_request_cap):
                raise StageBudgetExhausted("Issue39 cumulative budget reached")
            _append(self.ledger, {"event": "reserved", "request_id": ident,
                                  "context": self.context, "input_bytes": len(payload),
                                  "output_cap": output_cap,
                                  "reserved_tokens": reserve,
                                  "timestamp_utc": time.time()})
        try:
            response = self.client.complete(messages, tools, tool_choice)
        except Exception as exc:
            with _ledger_lock(self.ledger):
                _append(self.ledger, {"event": "failed", "request_id": ident,
                                      "error_type": type(exc).__name__,
                                      "timestamp_utc": time.time()})
            raise
        raw = self.client.client
        usage = dict(raw.last_usage)
        with _ledger_lock(self.ledger):
            _append(self.ledger, {"event": "received", "request_id": ident,
                                  "response_model_reported": raw.last_response_model,
                                  "finish_reason": raw.last_finish_reason,
                                  "usage": usage,
                                  "total_tokens": usage.get("total_tokens"),
                                  "timestamp_utc": time.time()})
        return response
