"""Small deterministic evidence-to-statement example, not a report model.

No diagnostic mapping, knowledge-base inference or private model is performed.
Only this structured claim and its fixed rendering can be verified here; this
does not validate arbitrary natural-language medical statements.
"""
from ..working_memory import clone, encoded
from ..research.task_memory_evidence import _entry_meta


def _render(claim):
    scope = encoded(claim["parameters"]).decode("utf-8")
    path = "/".join(map(str, claim["field_path"]))
    return (f"合成记录 {claim['record']}，范围 {scope}，{claim['capability']} 的 {path} = "
            f"{claim['value']} {claim['unit_or_kind']}；证据 {claim['task_id']}，"
            f"修订自 {claim['revision_of'] or '无'}。此为研究计算描述，不支持诊断或能力等级。")


def make_statement(store, task_id, field_path, *, use="historical"):
    if use not in {"historical", "current"}:
        raise ValueError("Choose historical or current evidence use")
    entry = store.find_entry(task_id)
    if entry is None:
        raise ValueError("No actual result")
    read = store.read_evidence(task_id, entry.record, entry.parameters, field_paths=[field_path])
    if read["status"] != "read":
        raise ValueError("No readable exact scalar")
    claim = {**clone(_entry_meta(entry)), "field_path": clone(field_path),
             "value": read["evidence"]["fields"][0]["value"], "use": use,
             "generation": "deterministic_template", "interpretation_sources": []}
    goal = store.find_subgoal(entry.evidence["subgoal_id"])
    claim["subgoal_status"] = goal.status
    claim["limitations"] = ["仅合成数据接口验证；未验证报告模型效果；不提供临床解释"]
    if goal.status != "completed":
        claim["limitations"].append("该子目标整体未完成；此项成功结果不能替代缺失交付")
    claim["text"] = _render(claim)
    return claim


def verify_statement(store, claim):
    """Check actual result, provenance, state and template; fail closed."""
    checks = {}
    try:
        entry = store.find_entry(claim["task_id"])
        if entry is None:
            return {"valid": False, "checks": {"result_exists": False}}
        expected = make_statement(store, entry.task_id, claim["field_path"], use=claim["use"])
        for key, value in expected.items():
            checks[key] = encoded(claim.get(key)) == encoded(value)
        checks["no_unverified_fields"] = set(claim) == set(expected)
        if claim["use"] == "current":
            checks["current_data_binding"] = store._binding_valid(entry)
            checks["not_superseded"] = not any(e.revision_of == entry.task_id for e in store.entries)
    except (ValueError, TypeError, KeyError, IndexError):
        checks["readable_claim"] = False
    return {"valid": all(checks.values()), "checks": checks,
            "scope": "structured scalar claim and deterministic wording only"}
