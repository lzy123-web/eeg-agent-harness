"""Frozen CIEDG planning-layer adapter plus preregistered mechanism ablations."""

from copy import deepcopy

from ...planning import StateAwareConstrainedPlanner
from ..integrated_method.contracts import compile_intent, validate_plan_against_ledger
from ..integrated_method.intent import IntentSpec
from ..integrated_method.transfer import TransferContractGraphPlanner
from ..integrated_method.v11 import ContractGraphResidualPlanner


class NoSemanticCacheSelection(ContractGraphResidualPlanner):
    def _restore_cached_consumer(self, goal):
        return False


class NoSemanticCacheReference(TransferContractGraphPlanner):
    def _restore_cached_consumer(self, goal):
        return False


class NoDependencyPropagationMixin:
    def _reconcile(self):
        invalid = []
        for goal, token in self.evidence.items():
            if not self._binding_valid(token.input_binding) or not self._binding_valid(token.output_binding):
                invalid.append(goal)
        for goal in invalid:
            self.evidence.pop(goal, None)
        if invalid:
            self._record_transition("ablation_direct_binding_only", goals=sorted(invalid))


class NoDependencySelection(NoDependencyPropagationMixin, ContractGraphResidualPlanner):
    pass


class NoDependencyReference(NoDependencyPropagationMixin, TransferContractGraphPlanner):
    pass


class WholeReplayMixin:
    def apply_result(self, action, rendered):
        if (
            not rendered["success"]
            and rendered["error"]["code"] in self.STATE_CONFLICT_CODES
            and self.repairs < self.max_repairs
        ):
            self.repairs += 1
            self.evidence.clear()
            self.evidence_cache.clear()
            self._record_transition("ablation_whole_graph_replay", failed_goal=action.kind)
            return
        return super().apply_result(action, rendered)


class WholeReplaySelection(WholeReplayMixin, ContractGraphResidualPlanner):
    pass


class WholeReplayReference(WholeReplayMixin, TransferContractGraphPlanner):
    pass


def _intent_from_case(case, *, no_eeg_guard=False):
    task = deepcopy(case["task"])
    disposition = task["disposition"]
    if no_eeg_guard and disposition == "clarify":
        disposition = "execute"
        objectives = task.get("objectives", [])
        if "trial_selection" in objectives:
            task["parameters"]["selection_authorized"] = True
        if "epoch_rereference" in objectives:
            task["parameters"]["rereference_authorized"] = True
            task["parameters"].setdefault("reference_channels", ["SYNTH-C2"])
    if disposition != "execute":
        return disposition, None
    evidence = {key: case["request"] for key in task["parameters"]}
    evidence["analysis_type"] = case["request"]
    return disposition, IntentSpec(
        "event_workflow", tuple(task["objectives"]), dict(task["parameters"]),
        explicit_evidence=evidence,
        semantic_evidence={"event_locked": case["request"]},
        forbidden_operations=tuple(task.get("forbidden_operations", ())),
    )


def _planner_class(case, ablation):
    reference = case["family"] == "rereference"
    if ablation == "without_semantic_evidence_reuse":
        return NoSemanticCacheReference if reference else NoSemanticCacheSelection
    if ablation == "without_dependency_invalidation":
        return NoDependencyReference if reference else NoDependencySelection
    if ablation == "whole_plan_replay":
        return WholeReplayReference if reference else WholeReplaySelection
    return TransferContractGraphPlanner if reference else ContractGraphResidualPlanner


def run_ciedg(case, context, *, ablation=None):
    disposition, intent = _intent_from_case(
        case, no_eeg_guard=ablation == "without_eeg_scientific_guards",
    )
    if disposition != "execute":
        return {
            "method": ablation or "CIEDG", "status": "clarification_required",
            "tool_results": [], "release_results": [], "scientific_state": {},
            "evidence_check": {"closed": False, "violations": []},
            "planning_trace": [],
        }
    task, ledger = compile_intent(intent, context)
    plan = StateAwareConstrainedPlanner(context).plan(task)
    check = validate_plan_against_ledger(plan, ledger)
    planner = _planner_class(case, ablation)(
        context, task, ledger, max_retries=1, max_repairs=2, max_tool_calls=16,
    )
    result = planner.run(plan, check).to_dict()
    result["method"] = ablation or "CIEDG"
    return result
