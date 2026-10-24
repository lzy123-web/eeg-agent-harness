"""Run and score the frozen small extensibility experiment."""

import ast
import json
from pathlib import Path
import textwrap

import numpy as np

from .candidate import run_ciedg_extension
from .common import build_context, compile_case, load_cases, oracle_effective
from .expert import run_expert_extension


PACKAGE = Path(__file__).parent


def _source_metrics(path):
    text = Path(path).read_text(encoding="utf-8")
    tree = ast.parse(text)
    logical = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    branches = sum(isinstance(node, (ast.If, ast.IfExp, ast.Match)) for node in ast.walk(tree))
    delta = textwrap.dedent(
        text.split("# EXTENSION_DELTA_START", 1)[1].split("# EXTENSION_DELTA_END", 1)[0]
    )
    delta_tree = ast.parse(delta)
    delta_logical = [
        line for line in delta.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    return {
        "file": "src/eeg_harness/research/extensibility/" + Path(path).name,
        "adapter_nonblank_noncomment_loc": len(logical),
        "conditional_nodes": branches, "objective_literal_mentions": text.count("epoch_variance"),
        "extension_delta_nonblank_noncomment_loc": len(delta_logical),
        "extension_delta_conditional_nodes": sum(
            isinstance(node, (ast.If, ast.IfExp, ast.Match)) for node in ast.walk(delta_tree)
        ),
    }


def _variance_release(result):
    matches = [item for item in result["release_results"] if item["tool_name"] == "epoch_variance"]
    return matches[-1] if matches else None


def _score(case, context, result):
    release = _variance_release(result)
    violations = []
    if result["status"] != "completed":
        violations.append(f"terminal:{result['status']}")
    if release is None or not release["success"]:
        violations.append("missing_variance_release")
        actual = {}
    else:
        actual = release["data"]["conditions"]
    expected = oracle_effective(case, context.record)
    if set(actual) != set(expected):
        violations.append("condition_set_mismatch")
    for label in set(actual) & set(expected):
        if actual[label]["epoch_count"] != expected[label]["epoch_count"]:
            violations.append(f"epoch_count:{label}")
        for channel, expected_value in expected[label]["channels"].items():
            value = actual[label]["channels"].get(channel)
            if value is None or not np.isclose(value, expected_value, rtol=1e-6, atol=1e-15):
                violations.append(f"variance:{label}:{channel}")
    successful = [item["tool_name"] for item in result["tool_results"] if item["success"]]
    for forbidden in case["forbidden_tools"]:
        if forbidden in successful:
            violations.append(f"forbidden:{forbidden}")
    if release is not None:
        effective = result["scientific_state"]["artifacts"]["effective"]
        if release["data"]["artifact_id"] != effective:
            violations.append("release_lineage_mismatch")
    counts = {name: successful.count(name) for name in sorted(set(successful))}
    return {
        "passed": not violations, "violations": violations,
        "tool_calls": len(result["tool_results"]),
        "successful_tool_calls": len(successful), "successful_tool_counts": counts,
        "variance_execution_kind": None if release is None else release.get("execution_kind", "tool_execution"),
    }


def run_experiment(output_path=None):
    payload = load_cases()
    rows = []
    methods = (
        ("CIEDG+extension", run_ciedg_extension),
        ("strong_dynamic_expert+extension", run_expert_extension),
    )
    for case in payload["cases"]:
        for method_name, runner in methods:
            context, _ = build_context(case)
            task, ledger, plan, check = compile_case(case, context)
            if method_name == "CIEDG+extension":
                result = runner(case, context, task, ledger, plan, check)
            else:
                result = runner(case, context, max_tool_calls=16, max_repairs=2)
            rows.append({
                "case_id": case["id"], "method": method_name,
                "score": _score(case, context, result), "result": result,
            })
    summary = {}
    for method_name, _ in methods:
        selected = [row for row in rows if row["method"] == method_name]
        summary[method_name] = {
            "passed": sum(row["score"]["passed"] for row in selected),
            "total": len(selected),
            "tool_calls": sum(row["score"]["tool_calls"] for row in selected),
            "successful_tool_calls": sum(row["score"]["successful_tool_calls"] for row in selected),
        }
    report = {
        "protocol_id": payload["protocol_id"], "summary": summary,
        "method_specific_source_metrics": {
            "CIEDG+extension": _source_metrics(PACKAGE / "candidate.py"),
            "strong_dynamic_expert+extension": _source_metrics(PACKAGE / "expert.py"),
        },
        "cases": rows,
    }
    json.dumps(report, ensure_ascii=False, allow_nan=False)
    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
