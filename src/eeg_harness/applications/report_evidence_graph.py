"""Evidence-bound report claim prototype for the multi-task EEG Harness.

One end-to-end line of provenance: PlanGraph output -> actual TaskEntry ->
field-level claim -> downstream claim/report. This module NEVER asserts that an
arbitrary LLM sentence or biomedical interpretation is verified. Real text
needs a separate structured extraction / expert-reviewed entailment layer.

The P1-to-P2 resolver works with the existing PlanGraph and TaskStore without
copying values into a second factual database. No TC model or private data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
from typing import Any, Iterable, Protocol


class EvidenceUnavailable(ValueError):
    """The requested scientific field does not have a currently eligible result."""


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True))


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class ResultRef:
    task_id: str
    key: str
    field_path: tuple[str | int, ...]
    revision: int | None = None

    def __post_init__(self):
        if not self.task_id or not self.key or not self.field_path:
            raise ValueError("A result reference needs a task, delivery key and exact field path")
        if self.revision is not None and (type(self.revision) is not int or self.revision < 1):
            raise ValueError("Revision must be a positive integer or omitted for current")
        if any(not ((type(x) is str and x) or (type(x) is int and x >= 0)) for x in self.field_path):
            raise ValueError("Invalid result field path")

    def to_dict(self) -> dict:
        row = {"task_id": self.task_id, "key": self.key, "field_path": list(self.field_path)}
        if self.revision is not None:
            row["revision"] = self.revision
        return row


@dataclass(frozen=True)
class Fact:
    ref: ResultRef
    value: float | int | str | bool
    unit: str
    record: str
    actual_scope: dict
    result_id: str
    source: Any
    resolved_revision: int
    processing_version: Any
    signature: str


class EvidenceResolver(Protocol):
    def resolve(self, ref: ResultRef) -> Fact: ...
    def delivery_status(self, task_id: str, key: str) -> tuple[str, list]: ...
    def comparison_authorized(self, refs: tuple[ResultRef, ...]) -> bool: ...


class TaskPlanEvidenceResolver:
    """Read-only bridge into actual P1 PlanGraph + TaskStore.

    No gold plan, no synthetic oracle and no repeated EEG computation.
    """

    def __init__(self, graph, store):
        self.graph, self.store = graph, store

    def resolve(self, ref: ResultRef) -> Fact:
        from ..result_semantics import read_scalar, result_field_semantics

        lookup = {"task_id": ref.task_id, "key": ref.key}
        if ref.revision is not None:
            lookup["revision"] = ref.revision
        try:
            resolved = self.graph.resolve_ref(lookup)
        except (KeyError, ValueError, TypeError) as exc:
            raise EvidenceUnavailable("Unknown task/output/revision") from exc
        if resolved["output_status"] not in {"DELIVERY_SATISFIED", "TASK_COMPLETED"}:
            raise EvidenceUnavailable("Result has not passed its P1 delivery checks")
        output = resolved["output"]
        if not output or not output.get("result_id"):
            raise EvidenceUnavailable("No original EEG tool result available")
        entry = self.store.find_entry(output["result_id"])
        if entry is None or not self.store._binding_valid(entry):
            raise EvidenceUnavailable("Original result binding no longer valid")
        try:
            value = read_scalar(entry.result, list(ref.field_path))
            semantics = result_field_semantics(
                entry.capability, list(ref.field_path), entry.result,
                parameters=entry.parameters,
                analysis_configuration=entry.evidence["analysis_configuration"])
            actual_scope = _json_copy(output.get("actual_scope", entry.parameters))
            source = _json_copy(output.get("source", entry.evidence["source"]))
            version = _json_copy(output.get("processing_version", entry.evidence["binding"]))
            copied_value = _json_copy(value)
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise EvidenceUnavailable("No valid registered scalar field") from exc
        signature = _hash({"result_id": entry.task_id, "field_path": list(ref.field_path),
                           "value": copied_value, "unit": semantics["unit_or_kind"],
                           "record": entry.record, "scope": actual_scope, "source": source,
                           "processing_version": version, "revision": resolved["revision"]})
        return Fact(ref, copied_value, semantics["unit_or_kind"], entry.record,
                    actual_scope, entry.task_id, source, resolved["revision"], version, signature)

    def delivery_status(self, task_id: str, key: str) -> tuple[str, list]:
        try:
            node = self.graph.nodes[task_id]
            if node.delivery(key) is None:
                raise KeyError(key)
        except KeyError as exc:
            raise EvidenceUnavailable("Unknown scientific task/output") from exc
        return node.output_status.get(key, "UNDELIVERED"), _json_copy(node.unresolved)

    def comparison_authorized(self, refs: tuple[ResultRef, ...]) -> bool:
        """Only a *delivered* P1 compare_results node authorizes mixed scopes.

        An LLM-written text string cannot grant authority to compare unrelated
        studies/windows/subjects. Scientific comparability beyond scope/units
        still needs an explicit upstream method and independent review.
        """
        for node in self.graph.nodes.values():
            for delivery in node.required_outputs:
                if delivery.capability != "compare_results" or len(delivery.input_refs) != 2:
                    continue
                actual = [(r.task_id, r.key, r.revision, tuple(r.fields[0]) if len(r.fields) == 1 else None)
                          for r in delivery.input_refs]
                requested = [(r.task_id, r.key, r.revision, tuple(r.field_path)) for r in refs]
                if (actual == requested and
                        node.output_status.get(delivery.key) in {"DELIVERY_SATISFIED", "TASK_COMPLETED"} and
                        node.outputs.get(delivery.key, {}).get("comparison_id")):
                    return True
        return False


@dataclass
class Claim:
    claim_id: str
    kind: str  # measurement | difference | ratio | limitation | interpretation
    refs: tuple[ResultRef, ...] = ()
    proposed_value: float | int | str | bool | None = None
    proposed_unit: str | None = None
    depends_on_claims: tuple[str, ...] = ()
    limitation_task: str | None = None
    limitation_key: str | None = None
    literature_ids: tuple[str, ...] = ()
    text: str = ""   # Not treated as verified; only deterministic renderer is releasable.

    def __post_init__(self):
        if not self.claim_id or self.kind not in {
                "measurement", "difference", "ratio", "limitation", "interpretation"}:
            raise ValueError("Invalid claim identity or type")
        if self.kind == "measurement" and len(self.refs) != 1:
            raise ValueError("Measurement needs exactly one actual result field")
        if self.kind in {"difference", "ratio"} and len(self.refs) != 2:
            raise ValueError("Comparison needs exactly two actual fields")
        if self.kind in {"measurement", "difference", "ratio"} and (
                self.proposed_value is None or not self.proposed_unit):
            raise ValueError("Numerical claims need explicit proposed value and unit")
        if self.kind == "limitation" and (not self.limitation_task or not self.limitation_key):
            raise ValueError("Limitation must point to a real P1 task and unfulfilled output key")
        if self.kind == "interpretation" and not self.depends_on_claims:
            raise ValueError("Scientific interpretation must depend on factual claims")


@dataclass
class ClaimAssessment:
    claim_id: str
    status: str
    reasons: list[str] = field(default_factory=list)
    signatures: dict[str, str] = field(default_factory=dict)
    factual_text: str | None = None


class EvidenceClaimGraph:
    """Evidence-backed claim lifecycle, with minimal incremental rechecks.

    Scientific/medical interpretations never auto-pass: a verified citation ID
    is not proof of entailment or population applicability.
    """

    def __init__(self, resolver: EvidenceResolver):
        self.resolver = resolver
        self.claims: dict[str, Claim] = {}
        self.assessments: dict[str, ClaimAssessment] = {}
        self.audit: list[dict] = []

    def add(self, claim: Claim) -> ClaimAssessment:
        if claim.claim_id in self.claims:
            raise ValueError("Claim already exists; use a new claim revision ID")
        if len(set(claim.depends_on_claims)) != len(claim.depends_on_claims):
            raise ValueError("Duplicate claim dependency")
        if any(parent not in self.claims for parent in claim.depends_on_claims):
            raise ValueError("Interpretation references an unknown or future claim")
        self.claims[claim.claim_id] = claim
        assessment = self._verify(claim)
        self.assessments[claim.claim_id] = assessment
        self.audit.append({"event": "claim_added", "claim_id": claim.claim_id, "status": assessment.status})
        return assessment

    def _verify(self, claim: Claim) -> ClaimAssessment:
        if claim.kind == "limitation":
            try:
                status, unresolved = self.resolver.delivery_status(claim.limitation_task, claim.limitation_key)
            except EvidenceUnavailable as exc:
                return ClaimAssessment(claim.claim_id, "BLOCKED", [str(exc)])
            if status in {"DELIVERY_SATISFIED", "TASK_COMPLETED"}:
                return ClaimAssessment(claim.claim_id, "UNSUPPORTED", ["This required result is already delivered"] )
            text = f"任务 {claim.limitation_task} 的结果 {claim.limitation_key} 未交付（{status}），未决事项：{unresolved}。"
            return ClaimAssessment(claim.claim_id, "VERIFIED_FACT", factual_text=text)

        if claim.kind == "interpretation":
            for dep in claim.depends_on_claims:
                parent = self.assessments[dep]
                if parent.status != "VERIFIED_FACT":
                    return ClaimAssessment(claim.claim_id, "BLOCKED", ["Underlying factual claim is not currently verified"])
            if not claim.literature_ids:
                return ClaimAssessment(claim.claim_id, "BLOCKED", ["No reviewed source passage identified"])
            return ClaimAssessment(claim.claim_id, "REVIEW_REQUIRED",
                                   ["Citation presence alone does not verify meaning, population or study applicability"])

        try:
            facts = [self.resolver.resolve(ref) for ref in claim.refs]
        except EvidenceUnavailable as exc:
            return ClaimAssessment(claim.claim_id, "BLOCKED", [str(exc)])
        signatures = {_hash(ref.to_dict()): fact.signature for ref, fact in zip(claim.refs, facts)}
        if not all(type(f.value) in {int, float} and math.isfinite(f.value) for f in facts):
            return ClaimAssessment(claim.claim_id, "UNSUPPORTED", ["A numerical assertion requires numeric fields"], signatures)
        if type(claim.proposed_value) not in {int, float} or not math.isfinite(claim.proposed_value):
            return ClaimAssessment(claim.claim_id, "UNSUPPORTED", ["Proposed numerical value is invalid"], signatures)
        if len(facts) == 2 and facts[0].unit != facts[1].unit:
            return ClaimAssessment(claim.claim_id, "UNSUPPORTED", ["Incompatible numerical field units"], signatures)
        if len(facts) == 2 and not self.resolver.comparison_authorized(claim.refs):
            # The LLM cannot invent comparisons even when two fields have the
            # same dimension: a delivered P1 comparison must authorize them.
            return ClaimAssessment(claim.claim_id, "REVIEW_REQUIRED",
                                   ["No delivered P1 comparison authorizes these exact operands"], signatures)
        if claim.kind == "measurement":
            actual, unit = float(facts[0].value), facts[0].unit
        elif claim.kind == "difference":
            actual, unit = float(facts[1].value) - float(facts[0].value), facts[0].unit
        else:
            if float(facts[0].value) == 0:
                return ClaimAssessment(claim.claim_id, "UNSUPPORTED", ["Ratio denominator is zero"], signatures)
            actual, unit = float(facts[1].value) / float(facts[0].value), "1"
        if claim.proposed_unit != unit:
            return ClaimAssessment(claim.claim_id, "UNSUPPORTED", ["Asserted unit differs from real field semantics"], signatures)
        if not math.isclose(actual, float(claim.proposed_value), rel_tol=1e-9, abs_tol=1e-18):
            return ClaimAssessment(claim.claim_id, "UNSUPPORTED", ["Asserted number does not match actual evidence"], signatures)
        if len(facts) == 1:
            fact = facts[0]
            text = (f"记录{fact.record}、条件{json.dumps(fact.actual_scope, ensure_ascii=False,sort_keys=True)}下"
                    f"的{list(fact.ref.field_path)}为{actual:.12g} {unit}（证据{fact.result_id}）。")
        else:
            text = (f"证据{facts[1].result_id}与{facts[0].result_id}的"
                    f"{claim.kind}为{actual:.12g} {unit}；两项原始分析条件须随报告展示。")
        return ClaimAssessment(claim.claim_id, "VERIFIED_FACT", signatures=signatures, factual_text=text)

    def affected_by(self, changed: Iterable[tuple[str, str]]) -> list[str]:
        """Find current-version consumers and all their downstream claims.

        Explicit historical revision refs are pinned and not invalidated only
        because a later revision is created. If their source is actually
        withdrawn, separately revalidate via refresh_all().
        """
        changed = set(changed)
        impacted = {cid for cid, c in self.claims.items()
                    if any((r.task_id, r.key) in changed and r.revision is None for r in c.refs)
                    or (c.limitation_task, c.limitation_key) in changed}
        todo = list(impacted)
        while todo:
            cid = todo.pop()
            for dependent_id, claim in self.claims.items():
                if cid in claim.depends_on_claims and dependent_id not in impacted:
                    impacted.add(dependent_id)
                    todo.append(dependent_id)
        return [cid for cid in self.claims if cid in impacted]

    def refresh(self, changed: Iterable[tuple[str, str]]) -> dict:
        """Revisit only affected claims; changed inputs don't silently rewrite text."""
        impacted = self.affected_by(changed)
        for cid in impacted:
            previous = self.assessments[cid]
            current = self._verify(self.claims[cid])
            if previous.signatures and current.signatures and previous.signatures != current.signatures:
                current.status = "STALE"
                current.reasons.append("Source evidence version/scope/number has changed; re-draft this claim")
            elif previous.status == "VERIFIED_FACT" and current.status == "BLOCKED":
                current.status = "STALE"
                current.reasons.append("A previously available source result is no longer eligible")
            elif self.claims[cid].kind == "interpretation" and any(
                    self.assessments[dep].status != "VERIFIED_FACT"
                    for dep in self.claims[cid].depends_on_claims):
                current.status = "STALE"
                current.reasons.append("Dependent scientific fact is stale")
            self.assessments[cid] = current
            self.audit.append({"event": "claim_refreshed", "claim_id": cid, "status": current.status})
        return {"affected_claims": impacted,
                "assessments": {cid: self.assessments[cid].status for cid in impacted}}

    def refresh_all(self) -> dict:
        return self.refresh({(r.task_id, r.key) for c in self.claims.values() for r in c.refs} |
                            {(c.limitation_task, c.limitation_key) for c in self.claims.values() if c.limitation_task})

    def release(self, required_outputs: Iterable[tuple[str, str]]) -> dict:
        """Only verified structured facts; interpretations need separate audit.

        Explicit uncovered outputs are returned to a reporting agent to
        acknowledge; they are never silently considered satisfied.
        """
        required = list(required_outputs)
        covered = {(r.task_id, r.key) for c in self.claims.values()
                   if self.assessments[c.claim_id].status == "VERIFIED_FACT"
                   for r in c.refs if r.revision is None}
        disclosures = {(c.limitation_task, c.limitation_key) for c in self.claims.values()
                       if c.kind == "limitation" and self.assessments[c.claim_id].status == "VERIFIED_FACT"}
        missing = [(t, k) for t, k in required if (t, k) not in covered and (t, k) not in disclosures]
        released = [a.factual_text for a in self.assessments.values()
                    if a.status == "VERIFIED_FACT" and a.factual_text]
        pending = {cid: a.status for cid, a in self.assessments.items() if a.status != "VERIFIED_FACT"}
        return {"released_facts": released, "missing_coverage": missing,
                "unreleased_claims": pending, "ready_for_factual_release": not missing,
                "scope": "structured verified facts only; no free-text or clinical certification"}