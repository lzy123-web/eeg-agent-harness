"""Issue52 offline runner guardrails, real tools and honest measurement."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from eeg_harness.research.working_memory_issue52 import (
    ControlledPlanClient, IMPLEMENTED_CASES, main, offline_report, preflight,
    protocol, records_for, run_case, write_new,
)


class Issue52OfflineRunnerTest(unittest.TestCase):
    def test_protocol_authorizes_zero_and_keeps_evaluation_out_of_requests(self):
        spec = protocol()
        self.assertEqual(spec["authorized_limits"], {"external_completions": 0, "api_tokens": 0})
        self.assertEqual({c["id"] for c in spec["cases"]}, set(IMPLEMENTED_CASES))
        for case in spec["cases"]:
            self.assertTrue(case["evaluation_only"]["never_send_to_agent"])
            text = "\n".join(case["requests"])
            for control in ("plan_tasks", "restore_task", "task_id", "check_deliveries"):
                self.assertNotIn(control, text)

    def test_real_cli_rejects_before_any_run_or_file_write(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/"not-created.json"
            with patch("eeg_harness.research.working_memory_issue52.offline_report") as run:
                with self.assertRaises(SystemExit) as error:
                    main(["--real", "--output", str(output)])
                self.assertEqual(error.exception.code, 2)
                run.assert_not_called()
                self.assertFalse(output.exists())

    def test_replay_cannot_consume_next_user_turn_when_previous_finish_fails(self):
        client = ControlledPlanClient([[('first', {})], [('later', {})]])
        client.begin_controlled_turn(0)
        first = client.complete([], [])
        self.assertEqual(first['tool_calls'][0]['function']['name'], 'first')
        with self.assertRaises(RuntimeError):
            client.complete([], [])
        self.assertEqual(client.request_count, 1)
        client.begin_controlled_turn(1)
        later = client.complete([], [])
        self.assertEqual(later['tool_calls'][0]['function']['name'], 'later')

    def test_three_arms_normal_short_real_tools_have_identical_numeric_values(self):
        report = offline_report(["T01"])
        self.assertEqual(report["external_completions"], 0)
        self.assertEqual(report["actual_api_tokens"], 0)
        expected = None
        for row in report['results']:
            self.assertEqual(row['metrics']['stop_reasons'], ['completed'])
            self.assertEqual(row['metrics']['numeric_executions'], 2)
            self.assertEqual(row['metrics']['oracle_count'], 3)
            self.assertTrue(all(o['passed'] for o in row['oracle']))
            self.assertIsNone(row['metrics']['request_success_rate'])
            numbers = [(r['field'], r['actual']) for r in row['oracle']]
            expected = numbers if expected is None else expected
            self.assertEqual(numbers, expected)
            self.assertTrue(row['decisions'])
            self.assertTrue(all(d['wire_bytes'] > 0 for d in row['decisions']))
        json.dumps(report, allow_nan=False)

    def test_mixed_missing_window_is_offline_clarification_then_real_event_work(self):
        for arm in ('A','B','C'):
            row = run_case('T03', arm)
            self.assertEqual(row['metrics']['stop_reasons'], ['clarification_required','completed'])
            self.assertEqual(row['metrics']['numeric_executions'], 3)
            self.assertTrue(all(o['passed'] for o in row['oracle']))
            first_entries = row['raw_agent_results'][0]['working_memory']['record_traces']
            self.assertEqual(len(first_entries['A']['events']), 0)
            self.assertEqual(len(first_entries['B']['events']), 1)

    def test_revision_uses_real_old_and_new_evidence_without_recomputing_other_record(self):
        for arm in ('A', 'B', 'C'):
            row = run_case('T05', arm)
            self.assertEqual(row['metrics']['stop_reasons'], ['completed', 'completed'])
            self.assertEqual(row['metrics']['numeric_executions'], 3)
            self.assertTrue(all(o['passed'] for o in row['oracle']))
            snapshot = row['raw_agent_results'][-1]['working_memory']
            a = next(n for n in snapshot['plan'] if n['task_id'] == 'alpha')
            self.assertEqual(a['revision'], 2)
            old = a['revision_history'][0]['snapshot']['outputs']['alpha']['result_id']
            new = a['outputs']['alpha']['result_id']
            comparison = snapshot['verified_comparisons'][-1]
            self.assertEqual([v['result_id'] for v in comparison['operands']], [old, new])
            self.assertEqual(len(snapshot['record_traces']['B']['events']), 1)

    def test_shared_literal_binding_failures_remain_visible_and_stop_replay(self):
        # Frozen known development limitations, not a candidate failure rate.
        for case in ('T04', 'T07'):
            for arm in ('A', 'B', 'C'):
                row = run_case(case, arm)
                self.assertEqual(row['metrics']['stop_reasons'], ['partial'])
                self.assertEqual(row['metrics']['numeric_executions'], 1)
                self.assertEqual(row['metrics']['controlled_errors'][0]['code'], 'SCIENTIFIC_SCOPE_UNGROUNDED')
                self.assertEqual(len(row['user_requests_sent']), 1)
                self.assertIsNone(row['metrics']['request_success_rate'])

    def test_preflight_is_wire_witness_not_invented_api_usage(self):
        report = preflight(['T01'])
        self.assertEqual(report['actual_api_tokens'], 0)
        self.assertEqual(report['external_completions'], 0)
        unit = report['paired_units'][0]
        self.assertEqual(unit['matched_unit_reserve'], unit['same_per_arm_witness_reserve']*3)
        self.assertGreaterEqual(unit['matched_unit_reserve'], unit['all_arm_witness'])
        self.assertIn('NONE', report['authorization'])

    def test_confirmation_values_differ_but_scientific_structure_does_not(self):
        a, b = records_for(), records_for('confirmation')
        for key in a:
            self.assertFalse((a[key].data == b[key].data).all())
            self.assertEqual(a[key].channel_names, b[key].channel_names)
            self.assertEqual(a[key].events, b[key].events)
            self.assertEqual(a[key].sfreq, b[key].sfreq)

    def test_outputs_are_json_and_cannot_overwrite_historical_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'new.json'
            write_new(path, {'stage':'issue52','external_completions':0})
            with self.assertRaises(FileExistsError):
                write_new(path, {'wrong':'replacement'})
            self.assertEqual(json.loads(path.read_text())['stage'], 'issue52')


if __name__ == '__main__':
    unittest.main()
