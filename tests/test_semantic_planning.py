import json
import unittest

from eeg_harness.research.semantic_planning.contracts import build_contracts
from eeg_harness.research.semantic_planning.models import ScientificRequirement
from eeg_harness.research.semantic_planning.planner import (
    CandidateEEGSemanticPlanner, ExpertConditionalDAG, GenericSemanticPlanner,
)
from eeg_harness.research.semantic_planning.runtime import SemanticRuntime, build_semantic_registry
from eeg_harness.research.semantic_planning.synthetic import build_scene


class SemanticModelAndRuntimeTest(unittest.TestCase):
    def test_registry_discovery_is_metadata_only(self):
        registry = build_semantic_registry()
        self.assertEqual(8, len(registry.list_specs()))
        definitions = registry.public_definitions("semantic_research_synthetic")
        self.assertEqual(8, len(definitions))
        json.dumps(definitions, allow_nan=False)

    def test_raw_and_processed_branches_are_not_mixed(self):
        record, payloads, _ = build_scene("raw")
        requirements = [
            ScientificRequirement.from_dict({"kind": "line_noise", "frequency_hz": 50.0}, 0),
            ScientificRequirement.from_dict({
                "kind": "bandpower", "low_hz": 1.0, "high_hz": 40.0,
                "require_lowpass_hz": 40.0,
            }, 1),
        ]
        plan = CandidateEEGSemanticPlanner().plan(requirements, [item.semantic for item in payloads])
        self.assertEqual("planned", plan.status)
        self.assertNotEqual(plan.steps[0].input_artifact_id, plan.steps[-1].input_artifact_id)
        runtime = SemanticRuntime(record, payloads)
        results = runtime.execute_plan(plan)
        self.assertTrue(all(item.success for item in results))
        json.dumps([item.to_dict() for item in results], allow_nan=False)

    def test_filtered_only_raw_noise_is_rejected(self):
        _, payloads, _ = build_scene("lowpass40")
        requirement = ScientificRequirement.from_dict({"kind": "line_noise", "frequency_hz": 50.0})
        for planner in (ExpertConditionalDAG(), GenericSemanticPlanner(), CandidateEEGSemanticPlanner()):
            plan = planner.plan([requirement], [item.semantic for item in payloads])
            self.assertEqual("rejected", plan.status)
            self.assertEqual("RAW_SOURCE_UNAVAILABLE", plan.reason_code)

    def test_joint_resample_then_epochs_executes_through_shared_executor(self):
        record, payloads, truth = build_scene("raw_events_256")
        requirement = ScientificRequirement.from_dict({
            "kind": "epochs", "target_sfreq": 128.0, "labels": ["A"],
            "tmin": -0.1, "tmax": 0.4,
        })
        plan = CandidateEEGSemanticPlanner().plan([requirement], [item.semantic for item in payloads])
        self.assertEqual(["sp_resample_with_events", "sp_create_epochs"], [step.operation for step in plan.steps])
        runtime = SemanticRuntime(record, payloads)
        results = runtime.execute_plan(plan)
        self.assertTrue(all(item.success for item in results))
        epochs = runtime.artifact(plan.output_artifact_ids[0]).value
        expected_a = truth["event_onsets_seconds"][::2]
        self.assertLessEqual(max(abs(a - b) for a, b in zip(epochs.event_onsets_seconds, expected_a)), 0.5 / 128.0 + 1e-12)

    def test_selection_authority_and_minimum_counts_are_planning_constraints(self):
        _, payloads, _ = build_scene("epochs_with_bad")
        unauthorized = ScientificRequirement.from_dict({
            "kind": "condition_feature", "labels": ["A", "B"],
            "min_trials_per_label": 2,
            "selection": {"authorized": False, "exclude_indices": [1]},
        })
        insufficient = ScientificRequirement.from_dict({
            "kind": "condition_feature", "labels": ["A", "B"],
            "min_trials_per_label": 3,
            "selection": {"authorized": True, "exclude_indices": [1, 3]},
        })
        planner = CandidateEEGSemanticPlanner()
        self.assertEqual("SELECTION_NOT_AUTHORIZED", planner.plan([unauthorized], [item.semantic for item in payloads]).reason_code)
        self.assertEqual("INSUFFICIENT_TRIALS", planner.plan([insufficient], [item.semantic for item in payloads]).reason_code)

    def test_contracts_separate_generic_effect_and_scientific_semantics(self):
        for contract in build_contracts():
            self.assertTrue(contract.effect.consumes)
            self.assertTrue(contract.effect.produces)
            self.assertTrue(contract.effect.scientific_semantics)


if __name__ == "__main__":
    unittest.main()
