import json
import unittest

from eeg_harness.research.intent_compiler.evaluation import (
    BudgetedClient, SharedBudget, evaluate_cases, select_cases, summarize,
)
from eeg_harness.research.intent_compiler.scoring import intent_from_dict, score_raw_fields


class _OneIntentClient:
    def __init__(self, payload):
        self.payload = payload
        self.request_count = 0
        self.last_usage = {}
        self.total_usage = {}
        self.last_response_model = None

    def complete(self, messages, tools, tool_choice="auto"):
        self.request_count += 1
        self.last_usage = {"total_tokens": 17}
        self.total_usage["total_tokens"] = self.total_usage.get("total_tokens", 0) + 17
        self.last_response_model = "test-resolved-model"
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "intent-1",
                "type": "function",
                "function": {
                    "name": "submit_eeg_intent",
                    "arguments": json.dumps(self.payload, ensure_ascii=False),
                },
            }],
        }


def _payload():
    return {
        "analysis_type": "psd",
        "objectives": [],
        "parameters": {"channels": ["SYNTH-C1"], "start": 0.0, "end": 2.0},
        "explicit_evidence": {
            "channels": "SYNTH-C1", "start": "0", "end": "2",
        },
        "semantic_evidence": {"spectral_power": "PSD band power"},
        "unknown_slots": [],
        "forbidden_operations": [],
        "source_stage": "current",
        "output_boundary": "research_only",
        "rationale": "test",
    }


class IntentEvaluationTest(unittest.TestCase):
    def test_same_payload_is_scored_for_v0_and_v1(self):
        cases, _ = select_cases("development", ("I10",))
        client = _OneIntentClient(_payload())
        rows = evaluate_cases(client, cases, requested_model="test")
        self.assertEqual(1, client.request_count)
        self.assertTrue(rows[0]["raw_score"]["all_fields_correct"])
        self.assertTrue(rows[0]["v0_decision"]["correct"])
        self.assertTrue(rows[0]["v1_decision"]["correct"])
        self.assertEqual("test-resolved-model", rows[0]["response_model"])
        self.assertEqual(1, summarize(rows)["cases"])

    def test_shared_budget_charges_actual_usage_and_stops(self):
        delegate = _OneIntentClient(_payload())
        budget = SharedBudget(max_requests=1, max_tokens=20)
        client = BudgetedClient(delegate, budget)
        client.complete([], [])
        self.assertEqual(1, budget.request_count)
        self.assertEqual(17, budget.total_tokens)
        with self.assertRaisesRegex(RuntimeError, "request budget"):
            client.complete([], [])

    def test_development_nominalized_prohibition_is_canonical(self):
        cases, _ = select_cases("development", ("I13",))
        from eeg_harness.research.intent_compiler.compiler import _canonical_forbidden
        self.assertEqual(("trial_selection",), _canonical_forbidden(cases[0]["request"]))

    def test_model_schema_errors_are_not_attributed_to_validator(self):
        cases, _ = select_cases("development", ("I14",))
        payload = {
            "analysis_type": "event_workflow",
            "objectives": ["epoch_quality"],
            "parameters": {"labels": ["target"], "tmin": 0.0, "tmax": 1.0},
            "explicit_evidence": {},
            "semantic_evidence": {
                "epoch_quality": "Check target epoch quality",
                "event_locked": "target epoch",
            },
            "unknown_slots": [],
            "forbidden_operations": ["trial_selection", "epoch_rereference"],
            "source_stage": "current",
            "output_boundary": "research_only",
            "rationale": "test",
        }
        score = score_raw_fields(cases[0], intent_from_dict(payload))
        self.assertFalse(score["all_fields_correct"])
        self.assertFalse(score["checks"]["semantic_concepts"])
        self.assertFalse(score["checks"]["forbidden_operations"])


if __name__ == "__main__":
    unittest.main()
