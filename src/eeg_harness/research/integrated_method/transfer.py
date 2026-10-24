"""CIEDG transfer gate: explicit Epoch re-reference as a second state family."""

from .v11 import (
    GOAL_CONTRACTS,
    ConstraintCarryingEEGAgentV11,
    ContractGraphResidualPlanner,
    GoalContract,
)


TRANSFER_CONTRACTS = dict(GOAL_CONTRACTS)
TRANSFER_CONTRACTS.update({
    "epoch_quality": GoalContract(
        "epoch_quality", "epoch_quality", "evidence", "effective_epochs",
        ("create_epochs",), 30, True,
    ),
    "epoch_rereference": GoalContract(
        "epoch_rereference", "rereference_epochs", "transition", "source_epochs",
        ("create_epochs",), 25, True,
    ),
})


class TransferContractGraphPlanner(ContractGraphResidualPlanner):
    """Bind reference-sensitive goals to an explicitly transformed Epoch state."""

    def __init__(self, context, task, ledger, **kwargs):
        objectives = tuple(task.arguments.get("objectives", ()))
        if "trial_selection" in objectives and "epoch_rereference" in objectives:
            raise ValueError("Selection and re-reference composition is not validated")
        super().__init__(context, task, ledger, contracts=TRANSFER_CONTRACTS, **kwargs)
        self.reference_channels = tuple(task.arguments.get("reference_channels", ()))
        self.rereference_authorized = task.arguments.get("rereference_authorized") is True
        if "epoch_rereference" in self.requested_goals:
            if not self.rereference_authorized:
                raise ValueError("Epoch re-reference requires explicit authorization")
            if not self.reference_channels:
                raise ValueError("Epoch re-reference requires explicit reference channels")

    def _compile_dependencies(self):
        dependencies = super()._compile_dependencies()
        if "epoch_rereference" not in self.requested_goals:
            return dependencies
        for goal in tuple(dependencies):
            if (
                goal != "epoch_rereference"
                and self.contracts[goal].input_policy == "effective_epochs"
            ):
                current = [item for item in dependencies[goal] if item != "create_epochs"]
                current.append("epoch_rereference")
                dependencies[goal] = tuple(dict.fromkeys(current))
        return dependencies

    def _effective_binding(self):
        token = self.evidence.get("epoch_rereference")
        if token is not None:
            return token.output_binding
        return super()._effective_binding()

    def _action_arguments(self, goal):
        arguments = super()._action_arguments(goal)
        if goal == "epoch_rereference":
            arguments["reference_channels"] = list(self.reference_channels)
        return arguments

    def _required_answer_tools(self):
        required = []
        for goal in self.active_goals:
            token = self.evidence.get(goal)
            contract = self.contracts[goal]
            if not contract.answer_required or token is None or token.result is None:
                continue
            if contract.tool_name not in required:
                required.append(contract.tool_name)
        return tuple(required)

    def state_dict(self):
        state = super().state_dict()
        token = self.evidence.get("epoch_rereference")
        output = None if token is None else token.output_binding
        state["reference_transition"] = {
            "requested": "epoch_rereference" in self.requested_goals,
            "authorized": self.rereference_authorized,
            "reference_channels": list(self.reference_channels),
            "mode": None if token is None else token.mode,
            "effective_reference": (
                None if output is None or output.artifact_id not in self.context.artifacts
                else self.context.artifacts[output.artifact_id].reference
            ),
        }
        return state


class ConstraintCarryingEEGAgentTransfer(ConstraintCarryingEEGAgentV11):
    """Opt-in final transfer gate without replacing LRSP v1.1."""

    runner_class = TransferContractGraphPlanner
    method_name = "constraint_carrying_eeg_plan_transfer_ciedg"
