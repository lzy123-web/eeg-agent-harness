"""Last live-discovered defects: explicit locator replacement and artifact axes."""
from copy import deepcopy
import unittest
from eeg_harness.tooling import ToolRequest
from eeg_harness.scientific_request_binding import source_catalog
from test_issue59_history_index import exercise
from test_issue59_scientific_binding import chain


class LocatorAndAxesTest(unittest.TestCase):
    def test_locator_replacement_in_both_directions_uses_explicit_choice(self):
        a,first,second,c,_=exercise(span_initial=True);w=a.working_memory
        self.assertFalse(c.errors,c.errors);self.assertEqual((first.stop_reason,second.stop_reason),('completed','completed'))
        d=w.graph.nodes['a'].delivery('power')
        self.assertIn('range_ref',d.interpretation);self.assertNotIn('range_span',d.interpretation)
        w.begin_turn('记录A的SYNTH-C1改回0到2秒窗口计算alpha功率。')
        span=next(f['span'] for f in source_catalog(w.store) if f['source_ref'].startswith('u3:'))
        args={'task_id':'a','output_key':'power','revision':2,'reason':'Explicit return to original window',
            'changes':{'scope':{'start':0,'end':2},'interpretation':{'source_span':span,'range_span':'0到2秒'}}}
        r=w._dispatch(ToolRequest('revise_plan',args));self.assertEqual(r['status'],'revised',r)
        d=w.graph.nodes['a'].delivery('power')
        self.assertNotIn('source_ref',d.interpretation);self.assertNotIn('range_ref',d.interpretation)
        result=w._dispatch(ToolRequest('psd',{'task_id':'a','output_key':'power','revision':3}))
        self.assertEqual(result['status'],'reused');self.assertEqual(len(w.store.entries),2)

    def test_explicit_conflicting_locator_pair_is_not_silently_corrected(self):
        a,_,_,_,_=exercise(span_initial=True);w=a.working_memory;before=deepcopy(w.graph.to_dict())
        d=w.graph.nodes['a'].delivery('power')
        r=w._dispatch(ToolRequest('revise_plan',{'task_id':'a','output_key':'power','revision':2,'reason':'TEST conflict',
            'changes':{'interpretation':{'range_ref':d.interpretation['range_ref'],'range_span':'4到6秒'}}}))
        self.assertEqual(r['status'],'rejected');self.assertEqual(w.graph.to_dict(),before)

    def test_complete_actual_artifact_axes_are_facts_not_guessed_selections(self):
        a,_,second,c=chain(measurements=['SYNTH-C1','SYNTH-C2'])
        self.assertEqual(second.stop_reason,'completed',c.errors)
        actual=next(x['data']['observation'] for x in second.tool_results if x['tool_name']=='epoch_quality' and x['success'])
        self.assertEqual(actual['scientific_sources']['labels']['measurement_channel_basis'],'exact_artifact_axes')
        self.assertEqual(len(a.working_memory.store.entries),3)
        for measured in (['SYNTH-C1'],['SYNTH-C2'],['SYNTH-C3']):
            bad,_,result,_=chain(measurements=measured)
            self.assertNotEqual(result.stop_reason,'completed');self.assertEqual(len(bad.working_memory.store.entries),2)
        bad,_,result,_=chain(measurements=['SYNTH-C1','SYNTH-C2'],
            second_text='记录A沿用同一批stimulus试次追加SYNTH-C2通道的质量测量。')
        self.assertNotEqual(result.stop_reason,'completed');self.assertEqual(len(bad.working_memory.store.entries),2)
