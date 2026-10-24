"""Evidence-constrained goal/state relation graph for EEG intent safety."""

from dataclasses import dataclass
import json

from ..integrated_method.intent import IntentInterpretation, IntentSpec
from .compiler import IntentCompilerV1Interpreter, _exact_span


GOALS = frozenset({
    "epoch_quality", "trial_selection", "epoch_summary",
    "event_bandpower", "epoch_rereference",
})
TRANSITIONS = frozenset({"trial_selection", "epoch_rereference"})
STATES = frozenset({"source_epochs", "effective_epochs", "unknown"})


@dataclass(frozen=True)
class GoalScope:
    goal: str
    input_state: str
    evidence_quote: str

    def to_dict(self):
        return {
            "goal": self.goal,
            "input_state": self.input_state,
            "evidence_quote": self.evidence_quote,
        }


@dataclass(frozen=True)
class ScopeRelation:
    predecessor: str
    successor: str
    evidence_quote: str

    def to_dict(self):
        return {
            "predecessor": self.predecessor,
            "successor": self.successor,
            "evidence_quote": self.evidence_quote,
        }


@dataclass(frozen=True)
class GoalScopeGraph:
    scopes: tuple[GoalScope, ...]
    relations: tuple[ScopeRelation, ...]
    unknown_scopes: tuple[str, ...] = ()

    def to_dict(self):
        return {
            "scopes": [scope.to_dict() for scope in self.scopes],
            "relations": [relation.to_dict() for relation in self.relations],
            "unknown_scopes": list(self.unknown_scopes),
        }


SCOPE_TOOL = [{
    "type": "function",
    "function": {
        "name": "submit_eeg_goal_scope_graph",
        "description": (
            "Submit the data-stage and precedence graph literally requested by the user. "
            "Do not optimize it to match runtime capability and do not invent authorization."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "scopes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "goal": {"type": "string", "enum": sorted(GOALS)},
                            "input_state": {"type": "string", "enum": sorted(STATES)},
                            "evidence_quote": {"type": "string"},
                        },
                        "required": ["goal", "input_state", "evidence_quote"],
                        "additionalProperties": False,
                    },
                },
                "relations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "predecessor": {"type": "string", "enum": sorted(GOALS)},
                            "successor": {"type": "string", "enum": sorted(GOALS)},
                            "evidence_quote": {"type": "string"},
                        },
                        "required": ["predecessor", "successor", "evidence_quote"],
                        "additionalProperties": False,
                    },
                },
                "unknown_scopes": {
                    "type": "array", "items": {"type": "string", "enum": sorted(GOALS)},
                },
            },
            "required": ["scopes", "relations", "unknown_scopes"],
            "additionalProperties": False,
        },
    },
}]


def parse_scope_message(message):
    calls = message.get("tool_calls") or []
    if len(calls) != 1 or calls[0].get("function", {}).get("name") != SCOPE_TOOL[0]["function"]["name"]:
        raise ValueError("Scope model must submit exactly one goal-scope graph")
    raw = calls[0]["function"].get("arguments", "{}")
    payload = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(payload, dict):
        raise ValueError("Scope payload must be an object")
    scopes = payload.get("scopes")
    relations = payload.get("relations")
    unknown = payload.get("unknown_scopes")
    if not isinstance(scopes, list) or not isinstance(relations, list) or not isinstance(unknown, list):
        raise ValueError("Scope fields must be arrays")
    parsed_scopes = []
    for item in scopes:
        if not isinstance(item, dict) or item.get("goal") not in GOALS or item.get("input_state") not in STATES:
            raise ValueError("Scope node is invalid")
        parsed_scopes.append(GoalScope(
            item["goal"], item["input_state"], item.get("evidence_quote", "")))
    parsed_relations = []
    for item in relations:
        if not isinstance(item, dict) or item.get("predecessor") not in GOALS or item.get("successor") not in GOALS:
            raise ValueError("Scope relation is invalid")
        parsed_relations.append(ScopeRelation(
            item["predecessor"], item["successor"], item.get("evidence_quote", "")))
    if not all(goal in GOALS for goal in unknown):
        raise ValueError("Unknown scope goal is invalid")
    return GoalScopeGraph(tuple(parsed_scopes), tuple(parsed_relations), tuple(unknown))


def _capability_certificate(objectives):
    objectives = set(objectives)
    transitions = objectives & TRANSITIONS
    if len(transitions) > 1:
        return None, "unsupported_transition_composition"
    expected = {goal: "source_epochs" for goal in objectives}
    required_edges = set()
    if "trial_selection" in transitions:
        expected["epoch_quality"] = "source_epochs"
        expected["trial_selection"] = "source_epochs"
        required_edges.add(("epoch_quality", "trial_selection"))
        for goal in objectives & {"epoch_summary", "event_bandpower"}:
            expected[goal] = "effective_epochs"
            required_edges.add(("trial_selection", goal))
    elif "epoch_rereference" in transitions:
        expected["epoch_rereference"] = "source_epochs"
        for goal in objectives - {"epoch_rereference"}:
            expected[goal] = "effective_epochs"
            required_edges.add(("epoch_rereference", goal))
    return {"input_states": expected, "required_edges": sorted(required_edges)}, None


def _has_cycle(nodes, edges):
    adjacency = {node: set() for node in nodes}
    indegree = {node: 0 for node in nodes}
    for left, right in edges:
        if right not in adjacency[left]:
            adjacency[left].add(right)
            indegree[right] += 1
    frontier = [node for node, degree in indegree.items() if degree == 0]
    visited = 0
    while frontier:
        node = frontier.pop()
        visited += 1
        for successor in adjacency[node]:
            indegree[successor] -= 1
            if indegree[successor] == 0:
                frontier.append(successor)
    return visited != len(nodes)


def _reachable(edges, start, target):
    """Return whether a precedence path exists, not merely a direct edge."""
    adjacency = {}
    for left, right in edges:
        adjacency.setdefault(left, set()).add(right)
    frontier = [start]
    visited = set()
    while frontier:
        node = frontier.pop()
        if node == target:
            return True
        if node in visited:
            continue
        visited.add(node)
        frontier.extend(adjacency.get(node, ()))
    return False


def validate_scope_graph(intent: IntentSpec, graph: GoalScopeGraph, user_request):
    """Validate a proposed graph against frozen runtime capabilities."""
    diagnostics = {
        "compiler": "typed_goal_state_relation_graph_v2",
        "graph": graph.to_dict(),
        "capability_certificate": None,
        "violations": [],
    }
    expected_goals = set(intent.objectives)
    seen_goals = [scope.goal for scope in graph.scopes]
    if len(seen_goals) != len(set(seen_goals)) or set(seen_goals) != expected_goals:
        diagnostics["violations"].append("goal_scope_not_bijective")
    if set(graph.unknown_scopes) - expected_goals:
        diagnostics["violations"].append("unknown_scope_goal_not_requested")
    if graph.unknown_scopes:
        diagnostics["violations"].append("scope_unknown")
    for scope in graph.scopes:
        if not _exact_span(user_request, scope.evidence_quote):
            diagnostics["violations"].append(f"non_exact_scope_evidence:{scope.goal}")
    edges = set()
    for relation in graph.relations:
        edge = (relation.predecessor, relation.successor)
        if relation.predecessor == relation.successor:
            diagnostics["violations"].append("self_relation")
        if relation.predecessor not in expected_goals or relation.successor not in expected_goals:
            diagnostics["violations"].append("relation_goal_not_requested")
        if not _exact_span(user_request, relation.evidence_quote):
            diagnostics["violations"].append(
                f"non_exact_relation_evidence:{relation.predecessor}:{relation.successor}")
        edges.add(edge)
    if expected_goals and _has_cycle(expected_goals, {
        edge for edge in edges if edge[0] in expected_goals and edge[1] in expected_goals
    }):
        diagnostics["violations"].append("cyclic_scope_relations")

    certificate, unsupported = _capability_certificate(intent.objectives)
    diagnostics["capability_certificate"] = certificate
    if unsupported:
        diagnostics["violations"].append(unsupported)
    elif certificate is not None:
        actual_states = {scope.goal: scope.input_state for scope in graph.scopes}
        for goal, expected_state in certificate["input_states"].items():
            if actual_states.get(goal) != expected_state:
                diagnostics["violations"].append(
                    f"unsupported_input_state:{goal}:{actual_states.get(goal)}:{expected_state}")
        for edge in certificate["required_edges"]:
            if not _reachable(edges, edge[0], edge[1]):
                diagnostics["violations"].append(
                    f"missing_capability_relation:{edge[0]}:{edge[1]}")

    if diagnostics["violations"]:
        return IntentInterpretation(
            True, intent, "clarify", ("analysis_stage",),
            "UNSUPPORTED_OR_UNVERIFIED_GOAL_SCOPE",
            "Requested EEG goal stages cannot be verified against the current single-branch runtime.",
        ), diagnostics
    return IntentInterpretation(True, intent, "execute"), diagnostics


class IntentScopeCompilerV2Interpreter:
    """Keep v1 extraction/validation, add an opt-in scope certificate."""

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.v1 = IntentCompilerV1Interpreter(llm_client)
        self.last_v1_interpretation = None
        self.last_raw_intent = None
        self.last_raw_scope = None
        self.last_scope_diagnostics = None

    def interpret(self, user_request, context):
        self.last_v1_interpretation = self.v1.interpret(user_request, context)
        self.last_raw_intent = self.v1.last_raw_intent
        if (
            self.last_v1_interpretation.disposition != "execute"
            or self.last_v1_interpretation.intent is None
        ):
            return self.last_v1_interpretation
        intent = self.last_v1_interpretation.intent
        if not (set(intent.objectives) & TRANSITIONS):
            return self.last_v1_interpretation
        prompt = (
            "你是 EEG 科学目标作用域提取器，不是规划器。只调用 submit_eeg_goal_scope_graph。"
            "按用户原意给每个 objective 标注读取 source_epochs（任何本请求转换前）或 "
            "effective_epochs（相关转换后）；不明确时用 unknown 并列入 unknown_scopes。"
            "trial_selection 和 epoch_rereference 是 transition，其输入为 source_epochs。"
            "relations 只记录用户表达或科学目标直接要求的先后边，不能为了匹配系统能力重排。"
            "每个 scope 和 relation 都必须引用用户原文精确连续片段；不得产生授权。INPUT="
            + json.dumps({
                "request": user_request,
                "analysis_type": intent.analysis_type,
                "objectives": list(intent.objectives),
            }, ensure_ascii=False, allow_nan=False)
        )
        try:
            message = self.llm_client.complete(
                [{"role": "system", "content": prompt},
                 {"role": "user", "content": user_request}],
                SCOPE_TOOL,
                tool_choice={"type": "function", "function": {
                    "name": "submit_eeg_goal_scope_graph"}},
            )
            self.last_raw_scope = parse_scope_message(message)
            decision, diagnostics = validate_scope_graph(
                intent, self.last_raw_scope, user_request)
            self.last_scope_diagnostics = diagnostics
            return decision
        except (TypeError, ValueError, json.JSONDecodeError):
            return IntentInterpretation(
                True, intent, "clarify", ("analysis_stage",),
                "SCOPE_GRAPH_PARSE_ERROR",
                "Goal-stage relations could not be parsed safely.",
            )
        except Exception:
            return IntentInterpretation(
                True, intent, "clarify", ("analysis_stage",),
                "SCOPE_MODEL_ERROR",
                "Goal-stage extraction failed; no EEG tools were executed.",
            )
