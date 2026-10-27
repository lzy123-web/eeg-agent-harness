"""Controlled contract tests; not a substitute for real LLM or EEG tool integration."""
import unittest
from eeg_harness.applications.report_evidence_graph import (
    Claim, EvidenceClaimGraph, EvidenceUnavailable, Fact, ResultRef, _hash
)


def ref(task="a", key="alpha", revision=None):
    return ResultRef(task, key, ("C1", "alpha"), revision)


class StubResolver:
    """Only a stand-in for P1; actual tool integration needs its own tests."""
    def __init__(self):
        self.data = {
            ("a", "alpha", None): (2e-10, "V²", "A", {"window": [0, 2]}, "r1", 1),
            ("a", "alpha", 1): (2e-10, "V²", "A", {"window": [0, 2]}, "r1", 1),
            ("b", "beta", None): (4e-10, "V²", "B", {"window": [0, 2]}, "r2", 1),
            ("late", "alpha", None): (6e-10, "V²", "A", {"window": [4, 6]}, "r3", 1),
            ("other", "hz", None): (2.0, "Hz", "A", {"window": [0, 2]}, "r4", 1)
        }
        self.status = {("a","alpha"):("DELIVERY_SATISFIED",[]),
                       ("b","beta"):("DELIVERY_SATISFIED",[]),
                       ("epochs","quality"):("UNDELIVERED",["missing event window"])}
        self.authorized = set()

    def resolve(self, r):
        row = self.data.get((r.task_id, r.key, r.revision))
        if row is None:
            raise EvidenceUnavailable("Output is not delivered")
        v, unit, record, scope, result_id, revision = row
        return Fact(r, v, unit, record, scope, result_id,
                    "synthetic://test", revision, {},
                    _hash({"value":v,"scope":scope,"result":result_id,"version":revision}))

    def delivery_status(self, task_id, key):
        if (task_id, key) not in self.status:
            raise EvidenceUnavailable("Unknown delivery")
        return self.status[task_id, key]

    def comparison_authorized(self, refs):
        return tuple((r.task_id,r.key,r.revision) for r in refs) in self.authorized


class ReportEvidenceGraphTest(unittest.TestCase):
    def setUp(self):
        self.r = StubResolver()
        self.g = EvidenceClaimGraph(self.r)

    def test_real_numeric_and_unit_are_required(self):
        self.assertEqual(self.g.add(Claim("ok","measurement",(ref(),),2e-10,"V²")).status,"VERIFIED_FACT")
        self.assertEqual(self.g.add(Claim("wrong","measurement",(ref(),),2e-9,"V²")).status,"UNSUPPORTED")
        self.assertEqual(self.g.add(Claim("unit","measurement",(ref(),),2e-10,"mV²")).status,"UNSUPPORTED")
        self.assertEqual(self.g.add(Claim("missing","measurement",(ref("n","x"),),2e-10,"V²")).status,"BLOCKED")

    def test_comparison_must_be_authorized_by_actual_p1_work(self):
        second=ResultRef("b","beta",("C1","beta"))
        diff=Claim("d","difference",(ref(),second),2e-10,"V²")
        self.assertEqual(self.g.add(diff).status,"REVIEW_REQUIRED")
        self.r.authorized.add((("a","alpha",None),("b","beta",None)))
        self.assertEqual(self.g.add(Claim("allowed","difference",(ref(),second),2e-10,"V²")).status,"VERIFIED_FACT")
        self.assertEqual(self.g.add(Claim("ratio","ratio",(ref(),second),2.0,"1")).status,"VERIFIED_FACT")

    def test_incompatible_units_are_rejected(self):
        self.r.authorized.add((("a","alpha",None),("other","hz",None)))
        other=ResultRef("other","hz",("frequency",))
        self.assertEqual(self.g.add(Claim("d","difference",(ref(),other),0,"V²")).status,"UNSUPPORTED")

    def test_source_rewrite_invalidates_dependent_interpretation(self):
        self.g.add(Claim("cur","measurement",(ref(),),2e-10,"V²"))
        self.g.add(Claim("hist","measurement",(ref(revision=1),),2e-10,"V²"))
        self.g.add(Claim("exp","interpretation",depends_on_claims=("cur",),literature_ids=("paper-pending",)))
        del self.r.data[("a","alpha",None)]
        changed=self.g.refresh([("a","alpha")])
        self.assertEqual(changed["affected_claims"],["cur","exp"])
        self.assertEqual(self.g.assessments["cur"].status,"STALE")
        self.assertEqual(self.g.assessments["exp"].status,"STALE")
        self.assertEqual(self.g.assessments["hist"].status,"VERIFIED_FACT")

    def test_unchanged_record_remains_valid_under_other_record_revision(self):
        self.g.add(Claim("b","measurement",(ResultRef("b","beta",("C1","beta")),),4e-10,"V²"))
        self.g.add(Claim("a","measurement",(ref(),),2e-10,"V²"))
        self.r.data[("a","alpha",None)]=(3e-10,"V²","A",{"window":[4,6]},"r-new",2)
        self.g.refresh([("a","alpha")])
        self.assertEqual(self.g.assessments["a"].status,"STALE")
        self.assertEqual(self.g.assessments["b"].status,"VERIFIED_FACT")
        self.assertEqual(self.g.add(Claim("a-new","measurement",(ref(),),3e-10,"V²")).status,"VERIFIED_FACT")

    def test_limitation_specific_to_unfulfilled_delivery(self):
        self.assertEqual(self.g.add(Claim("pending","limitation",limitation_task="epochs",
                                          limitation_key="quality")).status,"VERIFIED_FACT")
        self.assertTrue(self.g.release([("epochs","quality")])["ready_for_factual_release"])
        self.assertFalse(self.g.release([("epochs","quality"),("a","alpha")])["ready_for_factual_release"])
        self.assertEqual(self.g.add(Claim("false","limitation",limitation_task="a",
                                          limitation_key="alpha")).status,"UNSUPPORTED")

    def test_historical_claim_does_not_satisfy_current_report_coverage(self):
        self.g.add(Claim("old","measurement",(ref(revision=1),),2e-10,"V²"))
        self.assertFalse(self.g.release([("a","alpha")])["ready_for_factual_release"])

    def test_medical_explanation_cannot_pass_on_a_citation_id(self):
        self.g.add(Claim("fact","measurement",(ref(),),2e-10,"V²"))
        state=self.g.add(Claim("medical","interpretation",depends_on_claims=("fact",),
                               literature_ids=("existing-article",),text="ASD diagnosis"))
        self.assertEqual(state.status,"REVIEW_REQUIRED")
        self.assertEqual(len(self.g.release([("a","alpha")])["released_facts"]),1)


if __name__ == "__main__":
    unittest.main()
