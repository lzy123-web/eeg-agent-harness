"""Bounded synthetic-only natural-language validation for the opt-in multi-task method."""

import argparse
import json
from pathlib import Path
import time

from ...context import ExecutionContext
from ...demo import build_synthetic_event_record, build_synthetic_no_event_record
from ...executor import Executor
from ...llm import OpenAICompatibleClient
from ...pipeline import load_config
from ...profiles import EDF_NATIVE
from ...tools import build_default_registry
from .fake import Point1FakeLLM
from .v2 import ConstraintCarryingEEGAgentV2


PROJECT_ROOT = Path(__file__).resolve().parents[4]
PRIVATE_ROOT = PROJECT_ROOT / "artifacts"
CASES = (
    (
        "continuous_no_events",
        "请对 SYNTH-C1 通道 0 秒到 2 秒的 EEG 计算绝对频带功率，说明结果只适用于该窗口。",
        build_synthetic_no_event_record,
    ),
    (
        "event_quality_power",
        "请分析 stimulus 事件后 0 秒到 1 秒的试次，先测量质量但不要筛除试次，再计算各条件绝对频带功率。",
        build_synthetic_event_record,
    ),
)


def _inside_private_root(value):
    path = Path(value).expanduser().resolve()
    if not path.is_relative_to(PRIVATE_ROOT.resolve()):
        raise ValueError("Validation outputs must stay inside ignored artifacts directory")
    return path


def _append_jsonl(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, allow_nan=False) + "\n")
        stream.flush()


class JournaledBudgetClient:
    """Save each synthetic response before scoring; bound paid requests/tokens."""

    def __init__(self, client, journal, *, max_requests=8, max_total_tokens=24000):
        self.client = client
        self.journal = journal
        self.max_requests = int(max_requests)
        self.max_total_tokens = int(max_total_tokens)

    @property
    def model(self):
        return self.client.model

    @property
    def request_count(self):
        return self.client.request_count

    @property
    def total_usage(self):
        return self.client.total_usage

    @property
    def finish_reasons(self):
        return self.client.finish_reasons

    def complete(self, messages, tools, tool_choice="auto"):
        used = int(self.total_usage.get("total_tokens", 0))
        if self.request_count >= self.max_requests or used + self.client.max_tokens >= self.max_total_tokens:
            raise RuntimeError("Bounded LLM request/token budget reached")
        before = self.request_count
        try:
            response = self.client.complete(messages, tools, tool_choice)
        except Exception as exc:
            _append_jsonl(self.journal, {
                "request_index": before + 1,
                "status": "failed",
                "error_type": type(exc).__name__,
                "error_code": getattr(exc, "code", "CLIENT_ERROR"),
                "timestamp_utc": time.time(),
            })
            raise
        _append_jsonl(self.journal, {
            "request_index": self.request_count,
            "status": "received",
            "response_model_requested": self.model,
            "finish_reason": self.client.last_finish_reason,
            "usage": dict(self.client.last_usage),
            "raw_assistant_message": response,
            "timestamp_utc": time.time(),
        })
        return response


def run_suite(*, real=False, journal=None, max_requests=8, max_total_tokens=24000):
    if real and journal is None:
        raise ValueError("Real LLM suite requires a private response journal")
    client = (
        JournaledBudgetClient(
            OpenAICompatibleClient.from_env(), journal,
            max_requests=max_requests, max_total_tokens=max_total_tokens,
        ) if real else Point1FakeLLM()
    )
    if real:
        # A retry would consume an extra paid request outside the per-call guard.
        client.client.max_retries = 0
    config = load_config(PROJECT_ROOT / "config" / "baseline.json")
    records = []
    for case_id, request, factory in CASES:
        context = ExecutionContext(
            factory(), EDF_NATIVE, Executor(build_default_registry(), config),
            task_id=f"v2-{case_id}",
        )
        result = ConstraintCarryingEEGAgentV2(client, context).run(request).to_dict()
        records.append({"case_id": case_id, "request": request, "result": result})
    return {
        "synthetic_only": True, "real_llm": bool(real), "requested_model": getattr(client, "model", None),
        "request_count": getattr(client, "request_count", len(getattr(client, "calls", []))),
        "usage": dict(getattr(client, "total_usage", {})),
        "finish_reasons": list(getattr(client, "finish_reasons", [])),
        "records": records,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real", action="store_true")
    parser.add_argument("--max-requests", type=int, default=8)
    parser.add_argument("--max-total-tokens", type=int, default=24000)
    parser.add_argument("--output", default=str(PRIVATE_ROOT / "point1_v2_validation.json"))
    args = parser.parse_args(argv)
    output = _inside_private_root(args.output)
    journal = _inside_private_root(output.with_suffix(".responses.jsonl")) if args.real else None
    payload = run_suite(real=args.real, journal=journal,
                        max_requests=args.max_requests, max_total_tokens=args.max_total_tokens)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                      encoding="utf-8")
    print(json.dumps({
        "synthetic_only": True, "real_llm": args.real,
        "completed": sum(item["result"]["stop_reason"] == "completed" for item in payload["records"]),
        "cases": len(payload["records"]), "requests": payload["request_count"],
        "total_tokens": payload["usage"].get("total_tokens"),
        "details_private": True,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
