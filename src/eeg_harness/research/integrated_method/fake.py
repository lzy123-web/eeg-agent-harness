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
                "analysis_type": "unsupported", "objectives": [], "parameters": {},
                "explicit_evidence": {"analysis_type": text}, "semantic_evidence": {},
                "unknown_slots": [],
                "forbidden_operations": [], "source_stage": "current",
                "output_boundary": "unsupported", "rationale": "unregistered analysis",
            })
        channel = next((name for name in ("SYNTH-C1", "SYNTH-C2") if name.lower() in lowered), None)
        numbers = [float(item) for item in re.findall(r"(?<![A-Za-z])(-?\d+(?:\.\d+)?)", text)]
        if any(term in lowered for term in ("事件", "试次", "event", "epoch")):
            labels = [
                name for name in ("stimulus", "control", "target")
                if name in lowered
            ]
            parameters = {}
            evidence = {"analysis_type": "事件" if "事件" in text else "event"}
            unknown = []
            if labels:
                parameters["labels"] = labels
                evidence["labels"] = text
            else:
                unknown.append("labels")
            if len(numbers) >= 2:
                parameters.update({"tmin": numbers[-2], "tmax": numbers[-1]})
                quote = text
                evidence.update({"tmin": quote, "tmax": quote})
            else:
                unknown.extend(("tmin", "tmax"))
            selection = any(term in text for term in ("筛选", "筛除", "剔除"))
            forbidden_selection = any(term in text for term in ("不要筛", "禁止筛", "不要剔除"))
            selection_authorized = selection and not forbidden_selection and any(
                term in text for term in ("允许", "请筛", "筛除异常", "剔除异常", "生成筛选")
            )
            if selection_authorized:
                parameters["selection_authorized"] = True
                evidence["selection_authorized"] = text
            quality = any(term in text for term in ("质量", "伪迹"))
            power = any(term in lowered for term in ("频带", "功率", "psd", "band power"))
            summary = any(term in lowered for term in (
                "epoch 汇总", "epoch 概要", "试次汇总", "试次数", "epoch summary", "trial count",
            ))
            objectives = []
            if quality:
                objectives.append("epoch_quality")
            if selection_authorized:
                objectives.append("trial_selection")
            if summary:
                objectives.append("epoch_summary")
            if power:
                objectives.append("event_bandpower")
            semantic = {"event_locked": text}
            if quality:
                semantic["quality_measurement"] = text
            if selection:
                semantic["trial_selection"] = text
            if summary:
                semantic["epoch_summary"] = text
            if power:
                semantic["spectral_power"] = text
            return self._call({
                "analysis_type": "event_workflow", "objectives": objectives,
                "parameters": parameters,
                "explicit_evidence": evidence, "unknown_slots": unknown,
                "semantic_evidence": semantic,
                "forbidden_operations": ["selection"] if forbidden_selection else [],
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
            "analysis_type": analysis, "objectives": [], "parameters": parameters,
            "explicit_evidence": evidence, "unknown_slots": unknown,
            "semantic_evidence": {
                "spectral_power" if analysis == "psd" else "time_domain_amplitude": text
            },
            "forbidden_operations": [], "source_stage": "current",
            "output_boundary": "research_only", "rationale": "continuous analysis",
        })
