"""Isolated CIEDG+extension adapter; no frozen candidate source is changed."""

from ..integrated_method.transfer import TRANSFER_CONTRACTS
from ..integrated_method.v11 import (
    GOAL_CONTRACTS, ContractGraphResidualPlanner, GoalContract,
)
from ..integrated_method.transfer import TransferContractGraphPlanner


# EXTENSION_DELTA_START
VARIANCE_CONTRACT = GoalContract(
    "epoch_variance", "epoch_variance", "consumer", "effective_epochs",
    ("create_epochs",), 55, True,
)
SELECTION_CONTRACTS = {**GOAL_CONTRACTS, "epoch_variance": VARIANCE_CONTRACT}
REFERENCE_CONTRACTS = {**TRANSFER_CONTRACTS, "epoch_variance": VARIANCE_CONTRACT}


class ContractRequiredToolsMixin:
    def _required_answer_tools(self):
        required = []
        for goal in self.active_goals:
            token = self.evidence.get(goal)
            contract = self.contracts[goal]
            if contract.answer_required and token is not None and token.result is not None:
                if contract.tool_name not in required:
                    required.append(contract.tool_name)
        return tuple(required)


class SelectionExtensionPlanner(ContractRequiredToolsMixin, ContractGraphResidualPlanner):
    def __init__(self, context, task, ledger, **kwargs):
        super().__init__(context, task, ledger, contracts=SELECTION_CONTRACTS, **kwargs)


class ReferenceExtensionPlanner(ContractRequiredToolsMixin, TransferContractGraphPlanner):
    def __init__(self, context, task, ledger, **kwargs):
        objectives = tuple(task.arguments.get("objectives", ()))
        if "trial_selection" in objectives and "epoch_rereference" in objectives:
            raise ValueError("Selection and re-reference composition is not validated")
        ContractGraphResidualPlanner.__init__(
            self, context, task, ledger, contracts=REFERENCE_CONTRACTS, **kwargs,
        )
        self.reference_channels = tuple(task.arguments.get("reference_channels", ()))
        self.rereference_authorized = task.arguments.get("rereference_authorized") is True
        if "epoch_rereference" in self.requested_goals:
            if not self.rereference_authorized or not self.reference_channels:
                raise ValueError("Epoch re-reference requires authorization and channels")


def run_ciedg_extension(case, context, task, ledger, plan, check):
    planner_class = (
        ReferenceExtensionPlanner if case["family"] == "rereference"
        else SelectionExtensionPlanner
    )
    result = planner_class(
        context, task, ledger, max_retries=1, max_repairs=2, max_tool_calls=16,
    ).run(plan, check).to_dict()
    result["method"] = "CIEDG+extension"
    return result
# EXTENSION_DELTA_END
