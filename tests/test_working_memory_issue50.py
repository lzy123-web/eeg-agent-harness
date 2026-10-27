"""Issue50 offline science, truthful reservations and immutable checkpoints."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from eeg_harness.llm import LLMServiceError
from eeg_harness.research import working_memory_issue50 as stage
from eeg_harness.research.task_memory_issue39_budget import _append, _rows, ledger_totals, StageBudgetExhausted


class FakeJournal:
    def __init__(self, failure=False, usage=True):
        self.client = SimpleNamespace(max_tokens=1800, max_retries=0, timeout=60,
            last_usage={"prompt_tokens":70, "completion_tokens":30, "total_tokens":100} if usage else {},
            last_response_model="offline", last_finish_reason="stop", thinking="disabled")
        self.model, self.request_count, self.total_usage = "offline", 0, {}
        self.failure = failure
    def complete(self, *args):
        self.request_count += 1
        if self.failure:
            raise RuntimeError("Synthetic failure")
        return {"content":"offline"}


def charged(path, value, ident="synthetic-used"):
    _append(path, {"event":"reserved", "request_id":ident, "reserved_tokens":value})


class Issue50BudgetTest(unittest.TestCase):
    def test_exact_wire_uses_actual_model_settings_and_full_output_reserve(self):
        with tempfile.TemporaryDirectory() as d:
            raw=FakeJournal()
            client=stage.Issue50Client(raw, Path(d)/"b.jsonl", phase="development", arm="development")
            messages=[{"role":"user", "content":"必要合成信息"}]
            tools=[{"type":"function", "function":{"name":"record_info"}}]
            wire={"model":"offline", "messages":messages, "max_tokens":1800,
                "stream":False,"thinking":{"type":"disabled"},"tools":tools,"tool_choice":"auto"}
            expected=len(json.dumps(wire, ensure_ascii=False).encode("utf8"))+1800
            self.assertEqual(client.reservation(messages, tools), expected)
            client.complete(messages, tools)
            rows=_rows(client.ledger)
            self.assertEqual(next(r for r in rows if r["event"]=="reserved")["reserved_tokens"], expected)
            self.assertEqual(ledger_totals(client.ledger)["charged_tokens"],100)

    def test_new_stage_never_reuses_or_resizes_old_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"b.jsonl"
            _append(path,{"event":"opened","stage":"issue49","version":1,"max_requests":80,"max_tokens":500000})
            with self.assertRaises(StageBudgetExhausted):
                stage.Issue50Client(FakeJournal(),path,phase="development",arm="development")
            spec=stage.protocol();spec["limits"]["completions"]=65
            with self.assertRaises(StageBudgetExhausted):
                stage.Issue50Client(FakeJournal(),Path(d)/"new.jsonl",phase="development",arm="development",spec=spec)

    def test_failure_missing_usage_and_cross_run_share_charged_budget(self):
        for failure in (False, True):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as d:
                path=Path(d)/"b.jsonl"
                raw=FakeJournal(failure=failure,usage=False)
                client=stage.Issue50Client(raw,path,phase="development",arm="development")
                reserve=client.reservation([],[])
                if failure:
                    with self.assertRaises(RuntimeError): client.complete([],[])
                else: client.complete([],[])
                self.assertEqual(ledger_totals(path)["charged_tokens"], reserve)
                second=stage.Issue50Client(FakeJournal(),path,phase="layer1",arm="old-full")
                second.complete([],[])
                self.assertEqual(ledger_totals(path)["attempts"],2)
                self.assertEqual(ledger_totals(path)["charged_tokens"],reserve+100)

    def test_each_limit_blocks_before_network_and_retry_is_forbidden(self):
        for boundary in ("calls","tokens","retry"):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as d:
                path=Path(d)/"b.jsonl";raw=FakeJournal()
                client=stage.Issue50Client(raw,path,phase="development",arm="development")
                if boundary=="calls":
                    for i in range(64):charged(path,1,str(i))
                elif boundary=="tokens":charged(path,400000)
                else:raw.client.max_retries=1
                with self.assertRaises(LLMServiceError):client.complete([],[])
                self.assertEqual(raw.request_count,0)

    def test_current_checkpoint_can_finish_without_false_partial(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"b.jsonl"
            client=stage.Issue50Client(FakeJournal(),path,phase="development",arm="development")
            final=[{"role":"system","content":"Actual settled result"}]
            charged(path,400000-client.reservation(final,[],stage.FINISH_CHOICE))
            self.assertTrue(client.prepare_decision([{"role":"user","content":"continue"}],[],final,[]))
            self.assertFalse(client.delivery_checkpoint["stale"])
            self.assertFalse(client.delivery_checkpoint["checkpoint_only"])
            self.assertEqual(client.delivery_checkpoint["messages"],final)

    def test_stale_checkpoint_is_immutable_budgeted_and_explicitly_partial(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"b.jsonl"
            client=stage.Issue50Client(FakeJournal(),path,phase="development",arm="development")
            final=[{"role":"system","content":"old exact evidence"}]
            self.assertFalse(client.prepare_decision([],[],final,[]))
            lease=client._lease["reserved_tokens"]
            charged(path,400000-lease)
            final[0]["content"]="new much larger evidence"*1000
            self.assertTrue(client.prepare_decision([],[],final,[]))
            checkpoint=client.delivery_checkpoint
            self.assertTrue(checkpoint["stale"])
            self.assertTrue(checkpoint["checkpoint_only"])
            self.assertEqual(checkpoint["messages"][0]["content"],"old exact evidence")
            self.assertIn("partial status",checkpoint["messages"][-1]["content"])
            self.assertEqual(client.reservation(checkpoint["messages"],checkpoint["tools"],stage.FINISH_CHOICE),lease)
            client.complete(checkpoint["messages"],checkpoint["tools"],stage.FINISH_CHOICE)

    def test_new_user_turn_cannot_receive_last_turn_checkpoint(self):
        with tempfile.TemporaryDirectory() as d:
            client=stage.Issue50Client(FakeJournal(),Path(d)/"b.jsonl",phase="development",arm="development")
            client.set_context(turn=1)
            client.prepare_decision([],[],[{"role":"user","content":"old request"}],[])
            self.assertIsNotNone(client._lease)
            client.set_context(turn=2)
            self.assertIsNone(client._lease)
            self.assertIsNone(client.delivery_checkpoint)
            self.assertFalse(client.final_only)

    def test_forced_checkpoint_cannot_be_silently_enlarged(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"b.jsonl";raw=FakeJournal()
            client=stage.Issue50Client(raw,path,phase="development",arm="development")
            final=[{"role":"system","content":"settled exact evidence"}]
            charged(path,400000-client.reservation(final,[],stage.FINISH_CHOICE))
            client.prepare_decision([],[],final,[])
            with self.assertRaises(LLMServiceError):
                client.complete(final+[{"role":"user","content":"unreserved"}],[],stage.FINISH_CHOICE)
            self.assertEqual(raw.request_count,0)


class Issue50ProtocolTest(unittest.TestCase):
    def test_all_context_modes_receive_same_actual_controlled_evidence(self):
        hashes=[]
        for arm in ("managed-full","managed-summary","managed-working"):
            agent=stage.build_agent(None,arm,"offline-paired-"+arm)
            seeded=stage.seed_controlled_history(agent)
            self.assertEqual(seeded["entry_count"],5)
            self.assertEqual(len(agent.working_memory.store.subgoals),3)
            self.assertTrue(all(e.status=="completed" for e in agent.working_memory.store.entries))
            self.assertTrue(all(g.status=="completed" for g in agent.working_memory.store.subgoals))
            hashes.append(seeded["scientific_content_sha256"])
        self.assertEqual(len(set(hashes)),1)

    def test_actual_public_views_and_final_snapshots_are_measured(self):
        data=stage.budget_preflight()
        self.assertEqual(len(data["samples"]),5)
        self.assertTrue(all(r["fallback_lease_reserve"]>r["current_final_reserve"] for r in data["samples"]))
        self.assertTrue(all(r["real_seed_entries"]==5 for r in data["samples"] if r["layer"]=="layer2"))

    def test_public_gate_accepts_scientific_partial_not_guessed_event_execution(self):
        result={"stop_reason":"partial","final_answer":"连续结果已经交付；请补充事件窗口。","tool_results":[]}
        self.assertTrue(stage._relevant_window_clarification(result))
        result["tool_results"]=[{"tool_name":"create_epochs","success":True}]
        self.assertFalse(stage._relevant_window_clarification(result))
        result["tool_results"]=[]; result["final_answer"]="parameter_sources无效，请重试。"
        self.assertFalse(stage._relevant_window_clarification(result))

    def test_paired_freeze_cannot_change_candidate_or_repeat_arm(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"b.jsonl"
            stage.Issue50Client(FakeJournal(),path,phase="layer1",arm="old-full")
            manifest={"candidate_commit":"frozen","protocol_sha256":"protocol","model_settings":{"max_retries":0},"model_requested":"same-model"}
            stage._start_arm(path,"layer1","old-full","first",manifest)
            with self.assertRaises(StageBudgetExhausted): stage._start_arm(path,"layer1","old-full","retry",manifest)
            _append(path,{"event":"arm_ended","phase":"layer1","arm":"old-full"})
            changed={**manifest,"candidate_commit":"changed"}
            with self.assertRaises(StageBudgetExhausted): stage._start_arm(path,"layer1","managed-full","next",changed)
            stage._start_arm(path,"layer1","managed-full","next",manifest)

    def test_layer2_requires_real_new_path_and_complete_unit_admission_margin(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"b.jsonl"
            stage.Issue50Client(FakeJournal(),path,phase="layer2",arm="managed-full")
            manifest={"candidate_commit":"frozen","protocol_sha256":"protocol","model_settings":{},"model_requested":"same"}
            with self.assertRaises(StageBudgetExhausted):stage._start_arm(path,"layer2","managed-full","third",manifest)
            _append(path,{"event":"managed_basic_path_observed"})
            charged(path,320000)
            with self.assertRaises(StageBudgetExhausted):stage._start_arm(path,"layer2","managed-full","third",manifest)

    def test_science_preflight_is_real_tools_with_independent_oracle(self):
        data=stage.scientific_preflight()
        self.assertEqual(data["status"],"passed")
        self.assertTrue(all(c["valid"] for c in data["oracle_checks"]))
        self.assertEqual(len([o for o in data["operations"] if not o["result"]["success"]]),1)
        results={o["tool"]:o["result"]["data"] for o in data["operations"] if o["result"]["success"]}
        self.assertEqual(results["event_bandpower"]["artifact_id"],results["epoch_quality"]["artifact_id"])

    def test_protocol_keeps_one_same_natural_case_and_all_context_controls(self):
        spec=stage.protocol()
        self.assertEqual(spec["limits"],{"completions":64,"api_tokens":400000})
        self.assertEqual(spec["layer_order"]["layer1"],["old-full","managed-full"])
        self.assertEqual(len(spec["layer1"]["requests"]),3)
        self.assertEqual({spec["arms"][a]["context_mode"] for a in spec["layer_order"]["layer2"]}, {"full","summary","working"})
        self.assertTrue(spec["evaluation_only"]["never_send_to_agent"])


if __name__=="__main__":unittest.main()
