"""Fair expert, generic semantic and candidate EEG semantic planners."""

from collections import deque
import time

from .contracts import build_contracts
from .models import PlanStep, ScientificRequirement, SemanticPlan


GOAL_OPERATION = {
    "line_noise": "sp_line_noise",
    "bandpower": "sp_bandpower",
    "epochs": "sp_create_epochs",
    "condition_feature": "sp_condition_feature",
    "epoch_variance": "sp_epoch_variance",
}

ERROR_PRIORITY = (
    "SELECTION_NOT_AUTHORIZED", "INSUFFICIENT_TRIALS", "RAW_SOURCE_UNAVAILABLE",
    "EVENTS_UNAVAILABLE", "EVENT_LABEL_UNAVAILABLE", "INVALID_REQUIREMENT",
    "FREQUENCY_NOT_OBSERVABLE", "REQUIRED_PROCESSING_MISSING", "REQUIRED_SFREQ_MISSING",
)


def _reason(errors):
    for item in ERROR_PRIORITY:
        if item in errors:
            return item
    return next(iter(errors), "NO_LEGAL_PLAN")


def _step(contract, source, output, requirement, evidence):
    return PlanStep(
        operation=contract.name,
        input_artifact_id=source.artifact_id,
        output_artifact_id=output.artifact_id,
        arguments={"goal_kind": requirement.kind, "parameters": dict(requirement.parameters)},
        validity_evidence=evidence,
    )


class GenericSemanticPlanner:
    """Domain-neutral breadth-first composition over supplied typed contracts."""

    planner_name = "generic_semantic"

    def __init__(self, contracts=None, max_steps=8):
        self.contracts = tuple(contracts or build_contracts())
        self.max_steps = max_steps

    def _rank(self, contract, requirement):
        return 0

    def _one(self, requirement, available):
        queue = deque((artifact, ()) for artifact in available.values())
        seen = {artifact.artifact_id for artifact in available.values()}
        errors = set()
        contracts = sorted(self.contracts, key=lambda item: (self._rank(item, requirement), item.name))
        while queue:
            artifact, steps = queue.popleft()
            for contract in contracts:
                if requirement.kind not in contract.goal_kinds:
                    continue
                output, evidence, error = contract.apply(artifact, requirement)
                if output is None:
                    if error != "INPUT_KIND_MISMATCH":
                        errors.add(error)
                    continue
                if output.artifact_id == artifact.artifact_id:
                    next_steps = steps
                else:
                    next_steps = steps + (_step(contract, artifact, output, requirement, evidence),)
                if contract.name == GOAL_OPERATION.get(requirement.kind):
                    return output, next_steps, errors
                if len(next_steps) < self.max_steps and output.artifact_id not in seen:
                    seen.add(output.artifact_id)
                    queue.append((output, next_steps))
        return None, (), errors

    def plan(self, requirements, initial_artifacts):
        started = time.perf_counter()
        available = {item.artifact_id: item for item in initial_artifacts}
        all_steps, outputs = [], []
        queries = 0
        for requirement in requirements:
            queries += 1
            output, steps, errors = self._one(requirement, available)
            if output is None:
                return SemanticPlan(
                    self.planner_name, "rejected", tuple(all_steps), tuple(outputs),
                    _reason(errors), queries,
                    round((time.perf_counter() - started) * 1000, 3),
                )
            for step in steps:
                if step.output_artifact_id not in available:
                    all_steps.append(step)
                # Reproduce the symbolic state from the shared contract.
                source = available[step.input_artifact_id]
                contract = next(item for item in self.contracts if item.name == step.operation)
                produced, _, _ = contract.apply(source, requirement)
                available[produced.artifact_id] = produced
            available[output.artifact_id] = output
            outputs.append(output.artifact_id)
        status = "planned" if len(all_steps) <= self.max_steps else "budget_exhausted"
        return SemanticPlan(
            self.planner_name, status, tuple(all_steps[:self.max_steps]), tuple(outputs),
            None if status == "planned" else "TOOL_BUDGET_EXCEEDED", queries,
            round((time.perf_counter() - started) * 1000, 3),
        )


class CandidateEEGSemanticPlanner(GenericSemanticPlanner):
    """EEG-aware search ordering; scientific truth remains in shared contracts."""

    planner_name = "candidate_eeg_semantic"

    def _rank(self, contract, requirement):
        preferred = {
            "line_noise": ("sp_line_noise",),
            "bandpower": ("sp_bandpower", "sp_lowpass"),
            "epochs": ("sp_create_epochs", "sp_resample_with_events"),
            "condition_feature": (
                "sp_condition_feature", "sp_select_epochs", "sp_create_epochs",
                "sp_resample_with_events", "sp_lowpass",
            ),
            "epoch_variance": (
                "sp_epoch_variance", "sp_select_epochs", "sp_create_epochs",
                "sp_resample_with_events", "sp_lowpass",
            ),
        }.get(requirement.kind, ())
        return preferred.index(contract.name) if contract.name in preferred else len(preferred) + 1


class ExpertConditionalDAG:
    """Strong procedural baseline with complete rules and the same contracts/budget."""

    planner_name = "expert_dag"

    def __init__(self, contracts=None, max_steps=8):
        self.contracts = {item.name: item for item in (contracts or build_contracts())}
        self.max_steps = max_steps

    def _apply(self, name, source, requirement, steps, available, errors):
        contract = self.contracts[name]
        output, evidence, error = contract.apply(source, requirement)
        if output is None:
            if error != "INPUT_KIND_MISMATCH":
                errors.add(error)
            return None
        if output.artifact_id != source.artifact_id and output.artifact_id not in available:
            steps.append(_step(contract, source, output, requirement, evidence))
            available[output.artifact_id] = output
        return output

    def _record_goal(self, requirement, available, steps, errors):
        records = [item for item in available.values() if item.kind == "record"]
        if requirement.kind == "line_noise":
            for source in records:
                output = self._apply("sp_line_noise", source, requirement, steps, available, errors)
                if output:
                    return output
            return None
        for source in records:
            output = self._apply("sp_bandpower", source, requirement, steps, available, errors)
            if output:
                return output
        for source in records:
            derived = self._apply("sp_lowpass", source, requirement, steps, available, errors)
            if derived:
                output = self._apply("sp_bandpower", derived, requirement, steps, available, errors)
                if output:
                    return output
        return None

    def _epoch_goal(self, requirement, available, steps, errors):
        final_name = GOAL_OPERATION[requirement.kind]
        epochs = [item for item in available.values() if item.kind == "epochs"]
        for source in epochs:
            selected = self._apply("sp_select_epochs", source, requirement, steps, available, errors)
            if selected:
                output = self._apply(final_name, selected, requirement, steps, available, errors)
                if output:
                    return output
        records = [item for item in available.values() if item.kind == "record"]
        for source in records:
            current = source
            if requirement.parameters.get("require_lowpass_hz") is not None:
                current = self._apply("sp_lowpass", current, requirement, steps, available, errors)
                if current is None:
                    continue
            target = requirement.parameters.get("target_sfreq")
            if target is not None and abs(float(target) - float(current.sfreq)) > 1e-9:
                current = self._apply("sp_resample_with_events", current, requirement, steps, available, errors)
                if current is None:
                    continue
            epoch_artifact = self._apply("sp_create_epochs", current, requirement, steps, available, errors)
            if epoch_artifact is None:
                continue
            if requirement.kind == "epochs":
                return epoch_artifact
            selected = self._apply("sp_select_epochs", epoch_artifact, requirement, steps, available, errors)
            if selected:
                output = self._apply(final_name, selected, requirement, steps, available, errors)
                if output:
                    return output
        return None

    def plan(self, requirements, initial_artifacts):
        started = time.perf_counter()
        available = {item.artifact_id: item for item in initial_artifacts}
        steps, outputs, queries = [], [], 0
        for requirement in requirements:
            queries += 1
            errors = set()
            if requirement.kind in ("line_noise", "bandpower"):
                output = self._record_goal(requirement, available, steps, errors)
            elif requirement.kind in ("epochs", "condition_feature", "epoch_variance"):
                output = self._epoch_goal(requirement, available, steps, errors)
            else:
                output, errors = None, {"UNSUPPORTED_REQUIREMENT"}
            if output is None:
                return SemanticPlan(
                    self.planner_name, "rejected", tuple(steps), tuple(outputs), _reason(errors),
                    queries, round((time.perf_counter() - started) * 1000, 3),
                )
            outputs.append(output.artifact_id)
        status = "planned" if len(steps) <= self.max_steps else "budget_exhausted"
        return SemanticPlan(
            self.planner_name, status, tuple(steps[:self.max_steps]), tuple(outputs),
            None if status == "planned" else "TOOL_BUDGET_EXCEEDED", queries,
            round((time.perf_counter() - started) * 1000, 3),
        )
