"""Actual creation is independent of goal creation, read time and acceptance."""
from copy import deepcopy
from dataclasses import replace
import unittest
from test_issue59_scientific_binding import chain
from eeg_harness.task_plan_agent import ARMS


class ResultOriginTest(unittest.TestCase):
    def test_created_turn_survives_six_arm_reads_sync_and_reuse(self):
        for arm in ARMS:
            with self.subTest(arm=arm):
                a,first,second,c=chain(arm);w=a.working_memory
                self.assertEqual((first.stop_reason,second.stop_reason),('completed','completed'))
                self.assertEqual([e.evidence['created_user_turn'] for e in w.store.entries],[1,1,2])
                old=w.graph.nodes['source'];new=w.graph.nodes['target'];saved=deepcopy(new.outputs)
                w._read('target','quality','result');w._read('source','power','result')
                self.assertEqual(w._evidence(w.store.entries[0])['created_user_turn'],1)
                self.assertEqual(w._evidence(w.store.entries[-1])['created_user_turn'],2)
                w.begin_turn('记录A保留上述结果，不重复计算。')
                w._sync_outputs(old);w._sync_outputs(new)
                self.assertEqual(new.outputs,saved);self.assertEqual(old.outputs['epochs']['created_user_turn'],1)
                self.assertEqual(new.outputs['quality']['created_user_turn'],2)
                self.assertEqual(len(w.store.entries),3)

    def test_unknown_historical_origin_is_not_guessed_from_goal_or_read(self):
        a,_,_,_=chain();w=a.working_memory
        evidence=deepcopy(w.store.entries[0].evidence);evidence.pop('created_user_turn')
        legacy=replace(w.store.entries[0],evidence=evidence)
        self.assertNotIn('created_user_turn',w._evidence(legacy))
        from test_task_plan_agent import node,delivery,InspectableScriptedClient
        from test_working_memory import finish
        from eeg_harness.research.task_memory import synthetic_records
        from eeg_harness.task_plan_agent import TaskPlanEEGAgent
        client=InspectableScriptedClient([('plan_tasks',{'nodes':[node('deferred',[delivery('out','amplitude')])]}),
            finish('partial',unresolved=['TEST deferred execution']),
            ('amplitude',{'task_id':'deferred','output_key':'out'}),finish()])
        resumed=TaskPlanEEGAgent(client,synthetic_records())
        resumed.run('记录A的SYNTH-C1在0到2秒计算RMS。')
        result=resumed.continue_run('请完成记录A的SYNTH-C1在0到2秒的RMS。')
        self.assertEqual(result.stop_reason,'completed',client.errors)
        entry=resumed.working_memory.store.entries[0]
        self.assertEqual(entry.evidence['created_user_turn'],2)
        goal=resumed.working_memory.store.find_subgoal(entry.evidence['subgoal_id'])
        self.assertEqual(goal.turn,1)
