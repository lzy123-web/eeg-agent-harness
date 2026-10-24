"""Synthetic application example consuming only the generic evidence bundle.

This is a research evidence note, not an ASD assessment or diagnostic report.
No EEG is reloaded or recomputed here.
"""

import json


def render_auxiliary_evidence_note(bundle):
    if not isinstance(bundle, dict) or bundle.get("status") != "completed":
        raise ValueError("Only a closed task evidence bundle can be rendered")
    goals = bundle.get("goals")
    if not isinstance(goals, list) or not goals:
        raise ValueError("Evidence bundle has no completed goals")
    if (bundle.get("publication") != "complete"
            or bundle.get("expected_goal_count") != len(goals)
            or bundle.get("published_goal_count") != len(goals)
            or bundle.get("unfulfilled_goals")):
        raise ValueError("Evidence bundle does not account for every requested goal")
    lines = ["# 辅助评估所需分析证据摘要（合成示例）", "",
             "本样张只整理通用 EEG Harness 已完成的测量；不构成 ASD 诊断、严重程度或能力评分。", "",
             f"任务上下文：`{bundle['context_id']}`", ""]
    for item in goals:
        if item.get("status") != "satisfied" or not item.get("request_id"):
            raise ValueError("Goal evidence is incomplete")
        lines.extend([
            f"## {item['instance_id']} · {item['capability']}", "",
            f"数据来源：`{item['source']}`；Profile：`{item['profile_id']}`。",
            f"参数：`{item['parameters']}`；单位/类型：`{item['unit_or_kind']}`。",
            f"采样率：`{item['sampling_rate_hz']}` Hz；数据阶段：`{item['source_stage']}`。",
            f"分析配置：`{json.dumps(item['analysis_configuration'], ensure_ascii=False, sort_keys=True)}`。",
            f"分析范围：`{item['analysis_scope']}`；方法：`{item['method']}`。",
            f"输入绑定：`{item['input_binding']}`；依赖证据：`{item['dependency_evidence']}`。",
            f"证据索引：`{item['evidence_token']}`；工具请求：`{item['request_id']}`。",
            f"实际结果：`{item['result']}`", "",
            f"限制：{item['limitation']}", "",
        ])
    lines.extend(["## 尚缺的应用证据", "",
                  "受试者授权、年龄/发育背景、任务范式、标签含义、规范对照、临床解释与外部验证均未由本合成示例提供。", ""])
    return "\n".join(lines)
