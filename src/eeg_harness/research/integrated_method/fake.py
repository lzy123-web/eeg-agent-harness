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

    @staticmethod
    def _answer_call(messages):
        payload = json.loads(messages[0]["content"].split("INPUT=", 1)[1])
        references = []

        def leaves(value, path=()):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key.endswith("_id") or key == "artifact_id":
                        continue
                    yield from leaves(item, path + (key,))
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    yield from leaves(item, path + (index,))
            elif isinstance(value, (str, int, float)) and not isinstance(value, bool):
                yield path, value

        for tool_name in payload["required_answer_tools"]:
            result = next(
                item for item in payload["tool_results"]
                if item["success"] and item["tool_name"] == tool_name
            )
            path, _ = next(leaves(result["data"]))
            references.append({
                "request_id": result["request_id"],
                "path": [str(component) for component in path],
            })
        return {
            "role": "assistant", "content": None,
            "tool_calls": [{
                "id": "fake-answer", "type": "function",
                "function": {
                    "name": "submit_evidence_answer",
                    "arguments": json.dumps({"evidence_references": references}, ensure_ascii=False),
                },
            }],
        }

    def complete(self, messages, tools, tool_choice="auto"):
        self.calls.append({"messages": messages, "tools": tools, "tool_choice": tool_choice})
        self.request_count += 1
        self.finish_reasons.append("tool_calls" if tools else "stop")
        if tools and tools[0]["function"]["name"] == "submit_evidence_answer":
            return self._answer_call(messages)
        if not tools:
            return {"role": "assistant", "content": "未请求工具调用。"}
        text = next(item["content"] for item in messages if item["role"] == "user")
        lowered = text.lower()
        if any(term in lowered for term in ("诊断", "erp", "erd/ers", "显著性检验")):
            return self._call({
                "analysis_type": "unsupported", "parameters": {},
                "explicit_evidence": {"analysis_type": text}, "semantic_evidence": {},
                "unknown_slots": [],
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
            selection = any(term in text for term in ("筛选", "筛除"))
            if selection and any(term in text for term in ("允许", "请筛", "生成筛选")):
                parameters["selection_authorized"] = True
                evidence["selection_authorized"] = text
            quality = any(term in text for term in ("质量", "伪迹"))
            selected_analysis = (
                "quality_selected_bandpower"
                if selection and quality and any(term in lowered for term in ("频带", "功率", "psd", "band power"))
                else "quality_selection"
            )
            return self._call({
                "analysis_type": selected_analysis if selection else "event_bandpower", "parameters": parameters,
                "explicit_evidence": evidence, "unknown_slots": unknown,
                "semantic_evidence": (
                    {
                        "event_locked": text, "quality_measurement": text, "trial_selection": text,
                        **({"spectral_power": text} if selected_analysis == "quality_selected_bandpower" else {}),
                    }
                    if selection else {"event_locked": text, "spectral_power": text}
                ),
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
            "semantic_evidence": {
                "spectral_power" if analysis == "psd" else "time_domain_amplitude": text
            },
            "forbidden_operations": [], "source_stage": "current",
            "output_boundary": "research_only", "rationale": "continuous analysis",
        })
