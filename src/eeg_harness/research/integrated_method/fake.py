"""Deterministic protocol double for the CCEP integration tests."""

import json
import re


class Point1FakeLLM:
    model = "point1-protocol-double"

    def __init__(self):
        self.calls = []
        self.request_count = 0
        self.total_usage = {}
        self.finish_reasons = []

    @staticmethod
    def _call(arguments):
        return {
            "role": "assistant", "content": None,
            "tool_calls": [{
                "id": "fake-intent", "type": "function",
                "function": {"name": "submit_eeg_intent", "arguments": json.dumps(arguments, ensure_ascii=False)},
            }],
        }

    def complete(self, messages, tools, tool_choice="auto"):
        self.calls.append({"messages": messages, "tools": tools, "tool_choice": tool_choice})
        self.request_count += 1
        self.finish_reasons.append("tool_calls" if tools else "stop")
        if not tools:
            return {"role": "assistant", "content": "已依据成功工具结果完成研究用途的 EEG 分析；不构成临床诊断。"}
        text = next(item["content"] for item in messages if item["role"] == "user")
        lowered = text.lower()
        if any(term in lowered for term in ("诊断", "erp", "erd/ers", "显著性检验")):
            return self._call({
                "analysis_type": "unsupported", "parameters": {},
                "explicit_evidence": {"analysis_type": text}, "unknown_slots": [],
                "forbidden_operations": [], "source_stage": "current",
                "output_boundary": "unsupported", "rationale": "unregistered analysis",
            })
        channel = next((name for name in ("SYNTH-C1", "SYNTH-C2") if name.lower() in lowered), None)
        numbers = [float(item) for item in re.findall(r"(?<![A-Za-z])(-?\d+(?:\.\d+)?)", text)]
        if "事件" in text or "event" in lowered:
            label = next((name for name in ("stimulus", "control") if name in lowered), None)
            parameters = {}
            evidence = {"analysis_type": "事件" if "事件" in text else "event"}
            unknown = []
            if label:
                parameters["labels"] = [label]
                evidence["labels"] = label
            else:
                unknown.append("labels")
            if len(numbers) >= 2:
                parameters.update({"tmin": numbers[-2], "tmax": numbers[-1]})
                quote = text
                evidence.update({"tmin": quote, "tmax": quote})
            else:
                unknown.extend(("tmin", "tmax"))
            return self._call({
                "analysis_type": "event_bandpower", "parameters": parameters,
                "explicit_evidence": evidence, "unknown_slots": unknown,
                "forbidden_operations": ["selection"] if "不要筛" in text else [],
                "source_stage": "current", "output_boundary": "absolute_bandpower_only",
                "rationale": "event request",
            })
        analysis = "psd" if any(term in lowered for term in ("频带", "功率", "psd", "band power")) else "amplitude"
        parameters = {}
        evidence = {"analysis_type": text}
        unknown = []
        if channel:
            parameters["channels"] = [channel]
            evidence["channels"] = channel
        else:
            unknown.append("channels")
        if len(numbers) >= 2:
            parameters.update({"start": numbers[-2], "end": numbers[-1]})
            evidence.update({"start": text, "end": text})
        else:
            unknown.extend(("start", "end"))
        return self._call({
            "analysis_type": analysis, "parameters": parameters,
            "explicit_evidence": evidence, "unknown_slots": unknown,
            "forbidden_operations": [], "source_stage": "current",
            "output_boundary": "research_only", "rationale": "continuous analysis",
        })
