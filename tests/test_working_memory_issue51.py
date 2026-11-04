"""Issue51 accounting uses a fresh ledger and protects whole phase/arm pools."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from eeg_harness.llm import LLMServiceError
from eeg_harness.research import working_memory_issue51 as stage
from eeg_harness.research.task_memory_issue39_budget import _append, _rows, ledger_totals, StageBudgetExhausted


class OfflineJournal:
    def __init__(self, *, failure=False, usage=True):
        self.client = SimpleNamespace(max_tokens=2200, max_retries=0, timeout=90,
            last_usage={"prompt_tokens":70,"completion_tokens":30,"total_tokens":100} if usage else {},
            last_response_model="offline", last_finish_reason="stop", thinking="disabled")
        self.model, self.request_count, self.total_usage = "offline", 0, {}
        self.failure = failure
    def complete(self, *args):
        self.request_count += 1
        if self.failure:
            raise RuntimeError("offline failure")
        return {"content":"offline"}


def charge(path, amount, *, phase="development", arm="scientific-working", ident="prior"):
    _append(path,{"event":"reserved","request_id":ident,"reserved_tokens":amount,
                  "context":{"phase":phase,"arm":arm}})


class Issue51BudgetTest(unittest.TestCase):
    def client(self, path, **kwargs):
        return stage.Issue51Client(OfflineJournal(), path, phase="development", arm="scientific-working", **kwargs)

    def test_new_stage_rejects_old_header_and_closed_stage(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"ledger.jsonl"
            _append(path,{"event":"opened","stage":"issue50","version":1,"max_requests":64,"max_tokens":400000})
            with self.assertRaises(StageBudgetExhausted):self.client(path)
            other=Path(d)/"independent.jsonl"
            self.client(other)
            _append(other,{"event":"stage_closed"})
            with self.assertRaises(StageBudgetExhausted):self.client(other)

    def test_exact_wire_output_and_usage_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            c=self.client(Path(d)/"ledger.jsonl")
            messages=[{"role":"user","content":"合成 EEG 记录"}]
            tools=[{"type":"function","function":{"name":"record_info"}}]
            wire={"model":"offline","messages":messages,"max_tokens":2200,"stream":False,
                  "thinking":{"type":"disabled"},"tools":tools,"tool_choice":"auto"}
            self.assertEqual(c.reservation(messages,tools),len(json.dumps(wire,ensure_ascii=False).encode("utf8"))+2200)
            c.complete(messages,tools)
            self.assertEqual(ledger_totals(c.ledger)["reported_tokens"],100)
            self.assertEqual(_rows(c.ledger)[0]["stage"],"issue51")

    def test_development_cannot_consume_confirmation_pool(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"ledger.jsonl"
            c=self.client(path)
            charge(path,149000)
            with self.assertRaises(LLMServiceError):c.complete([{"role":"user","content":"x"}],[])
            self.assertEqual(c.request_count,0)
            confirm=stage.Issue51Client(OfflineJournal(),path,phase="confirmation",arm="scientific-working")
            confirm.complete([{"role":"user","content":"x"}],[])
            self.assertEqual(confirm.request_count,1)

    def test_unapproved_comparison_cannot_spend_the_stage_budget(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"ledger.jsonl"
            c=stage.Issue51Client(OfflineJournal(),path,phase="comparison",arm="scientific-full")
            charge(path,89000,phase="comparison",arm="scientific-full")
            with self.assertRaises(LLMServiceError):c.complete([],[])
            summary=stage.Issue51Client(OfflineJournal(),path,phase="comparison",arm="scientific-summary")
            with self.assertRaises(LLMServiceError):summary.complete([],[])
            self.assertEqual(summary.request_count,0)

    def test_matched_arm_caps_and_global_ceiling_both_apply(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"ledger.jsonl"
            full=stage.Issue51Client(OfflineJournal(),path,phase="comparison",arm="scientific-full")
            _append(path,{"event":"arm_ended","phase":"confirmation","run_id":"offline-confirmed"})
            _append(path,{"event":"phase_frozen","phase":"comparison","scientific_audit_sha256":"offline-reviewed"})
            charge(path,99000,phase="comparison",arm="scientific-full")
            with self.assertRaises(LLMServiceError):full.complete([],[])
            summary=stage.Issue51Client(OfflineJournal(),path,phase="comparison",arm="scientific-summary")
            summary.complete([],[])
            self.assertEqual(summary.request_count,1)
            charge(path,550900,phase="confirmation",ident="other-pool-used")
            with self.assertRaises(LLMServiceError):summary.complete([],[])
            self.assertEqual(summary.request_count,1)

    def test_failures_and_unsettled_attempts_keep_reservations(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"ledger.jsonl"
            c=stage.Issue51Client(OfflineJournal(failure=True),path,phase="development",arm="scientific-working")
            reserve=c.reservation([],[])
            with self.assertRaises(RuntimeError):c.complete([],[])
            self.assertEqual(ledger_totals(path)["charged_tokens"],reserve)
            charge(path,150000-reserve)
            with self.assertRaises(LLMServiceError):c.complete([],[])
            self.assertEqual(c.request_count,1)

    def test_missing_usage_is_charged_not_free(self):
        with tempfile.TemporaryDirectory() as d:
            c=stage.Issue51Client(OfflineJournal(usage=False),Path(d)/"ledger.jsonl",
                phase="development",arm="scientific-working")
            expected=c.reservation([],[])
            c.complete([],[])
            self.assertEqual(ledger_totals(c.ledger)["charged_tokens"],expected)

    def test_actual_final_checkpoint_cannot_be_expanded(self):
        with tempfile.TemporaryDirectory() as d:
            c=self.client(Path(d)/"ledger.jsonl")
            final=[{"role":"user","content":"existing exact evidence"}]
            tools=[{"type":"function","function":{"name":"finish_task"}}]
            charge(c.ledger,150000-c.reservation(final,tools,stage.FINISH_CHOICE)-10)
            self.assertTrue(c.prepare_decision([{"role":"user","content":"large"*5000}],tools,final,tools))
            with self.assertRaises(LLMServiceError):c.complete(final+[{"role":"user","content":"extra"}],tools,stage.FINISH_CHOICE)
            c.complete(c.delivery_checkpoint["messages"],c.delivery_checkpoint["tools"],stage.FINISH_CHOICE)
            self.assertEqual(c.request_count,1)

    def test_automatic_retry_rejected_and_turn_resets_final_lease(self):
        with tempfile.TemporaryDirectory() as d:
            c=self.client(Path(d)/"ledger.jsonl")
            c.client.client.max_retries=1
            with self.assertRaises(LLMServiceError):c.complete([],[])
            self.assertEqual(c.request_count,0)
            c.final_only=True;c.delivery_checkpoint={"stale":True}
            c.set_context(turn=2)
            self.assertFalse(c.final_only)
            self.assertIsNone(c.delivery_checkpoint)


class Issue51ProtocolTest(unittest.TestCase):
    def test_phase_maxima_remain_subordinate_to_single_authorized_stage(self):
        spec=stage.protocol()
        self.assertEqual(sum(v["completions"] for v in spec["phase_limits"].values()),72)
        self.assertEqual(spec["limits"]["api_tokens"],650000)
        self.assertEqual(spec["phase_limits"]["confirmation"]["api_tokens"],500000)
        self.assertEqual(spec["phase_limits"]["comparison"]["api_tokens"],300000)
        self.assertEqual(set(spec["arms"][a]["context_mode"] for a in spec["arm_order"]["comparison"]),
                         {"full","summary","working"})
        self.assertTrue(spec["evaluation_only"]["never_send_to_agent"])

    def test_natural_requests_do_not_supply_tool_protocol_or_ids(self):
        for phase in ("development","confirmation","comparison"):
            for request in stage.requests_for(phase):
                for token in ("focus_task", "finish_task", "create_epochs", "task_id", "subgoal_id", "read_result", "restore_task"):
                    self.assertNotIn(token,request)

    def test_scientific_preflight_uses_real_tools_and_independent_numbers(self):
        data=stage.scientific_preflight()
        self.assertEqual(data["status"],"passed")
        self.assertEqual(len(data["oracle_checks"]),46)
        self.assertTrue(all(c["valid"] for c in data["oracle_checks"]))
        self.assertTrue(any(not r["result"]["success"] for r in data["operations"]))
        self.assertTrue(all("issue51" in r.source for r in stage.records_for().values()))

    def test_complete_natural_unit_has_real_scope_and_all_final_inputs(self):
        witness=stage.autonomous_unit_witness()
        self.assertTrue(witness["complete_unit_admissible"])
        self.assertEqual(witness["final_inputs_included"],3)
        self.assertEqual({r["turn"] for r in witness["by_turn"]},{1,2,3})
        observations=[a["result"]["data"].get("observation") for a in witness["actions"]]
        actual=[o for o in observations if o]
        self.assertTrue(any(o["record"] == "B" and o["scope"].get("start") == 2 and o["scope"].get("end") == 4 for o in actual))
        self.assertTrue(any(o["request"]["name"] == "epoch_quality" for o in actual))
        self.assertGreater(witness["bounded_witness_tokens"],witness["compact_final_lease_witness_tokens"])

    def test_minimal_comparison_preserves_shared_complete_history(self):
        result=stage.budget_preflight()
        self.assertTrue(result["comparison_complete_unit_admissible"])
        self.assertEqual(len({s["scientific_content_sha256"] for s in result["samples"]}),1)
        self.assertTrue(all(s["controlled_entry_count"] == 3 and s["full_native_final_input_included"] for s in result["samples"]))
        self.assertTrue(all(any(a["tool"] == "epoch_quality" and a["result"]["success"] for a in s["controlled_actions"]) for s in result["samples"]))
        full=next(s for s in result["samples"] if s["context_mode"] == "full")
        self.assertFalse(any(a["tool"] == "read_result" for a in full["controlled_actions"]))


if __name__ == "__main__":unittest.main()
