"""Deterministic source-candidate contract matcher.

The matcher knows nothing about natural-language templates or offline case IDs.
It compares two caller-supplied contracts and therefore can be tested against
oracle source claims without pretending to solve source extraction.
"""

from itertools import permutations
from typing import Iterable

from .models import CoverageReport, ScientificClaim, ScientificContract


COMPARE_FIELDS = (
    "input_stage",
    "output_stage",
    "polarity",
    "authorization",
    "supported",
    "parameters",
)


def _pair_cost(source: ScientificClaim, candidate: ScientificClaim) -> int:
    return sum(getattr(source, field) != getattr(candidate, field)
               for field in COMPARE_FIELDS)


def _best_pairs(
    source_claims: Iterable[ScientificClaim],
    candidate_claims: Iterable[ScientificClaim],
) -> tuple[list[tuple[ScientificClaim, ScientificClaim]], list[ScientificClaim], list[ScientificClaim]]:
    """Find a minimum-field-mismatch pairing inside each semantic anchor."""
    source = list(source_claims)
    candidate = list(candidate_claims)
    pairs: list[tuple[ScientificClaim, ScientificClaim]] = []
    missing: list[ScientificClaim] = []
    extra: list[ScientificClaim] = []
    anchors = sorted({item.semantic_anchor() for item in source + candidate})
    for anchor in anchors:
        left = [item for item in source if item.semantic_anchor() == anchor]
        right = [item for item in candidate if item.semantic_anchor() == anchor]
        if not left:
            extra.extend(right)
            continue
        if not right:
            missing.extend(left)
            continue
        if len(left) <= len(right):
            choices = permutations(right, len(left))
            selected = min(choices, key=lambda values: sum(
                _pair_cost(a, b) for a, b in zip(left, values)))
            pairs.extend(zip(left, selected))
            selected_ids = {id(item) for item in selected}
            extra.extend(item for item in right if id(item) not in selected_ids)
        else:
            choices = permutations(left, len(right))
            selected = min(choices, key=lambda values: sum(
                _pair_cost(a, b) for a, b in zip(values, right)))
            pairs.extend(zip(selected, right))
            selected_ids = {id(item) for item in selected}
            missing.extend(item for item in left if id(item) not in selected_ids)
    return pairs, missing, extra


def _relation_set(
    contract: ScientificContract,
    id_to_source_id: dict[str, str],
) -> set[tuple[str, str]]:
    result = set()
    for left, right in contract.precedence:
        if left in id_to_source_id and right in id_to_source_id:
            result.add((id_to_source_id[left], id_to_source_id[right]))
    return result


def compare_contracts(
    source: ScientificContract,
    candidate: ScientificContract,
) -> CoverageReport:
    """Return an auditable coverage certificate for two typed contracts."""
    pairs, missing_claims, extra_claims = _best_pairs(source.claims, candidate.claims)
    covered = []
    conflicts = []
    candidate_to_source: dict[str, str] = {}
    for left, right in pairs:
        candidate_to_source[right.claim_id] = left.claim_id
        mismatches = [field for field in COMPARE_FIELDS
                      if getattr(left, field) != getattr(right, field)]
        if not mismatches:
            covered.append({
                "source_claim_id": left.claim_id,
                "candidate_claim_id": right.claim_id,
                "operation": left.operation,
            })
            continue
        for field in mismatches:
            conflict_type = {
                "input_stage": "stage_conflict",
                "output_stage": "stage_conflict",
                "polarity": "polarity_conflict",
                "authorization": "authorization_conflict",
                "supported": "support_conflict",
                "parameters": "parameter_conflict",
            }[field]
            conflicts.append({
                "type": conflict_type,
                "field": field,
                "source_claim_id": left.claim_id,
                "candidate_claim_id": right.claim_id,
                "operation": left.operation,
                "source_value": getattr(left, field),
                "candidate_value": getattr(right, field),
            })

    source_relations = set(source.precedence)
    candidate_relations = _relation_set(candidate, candidate_to_source)
    missing_relations = tuple(sorted(source_relations - candidate_relations))
    extra_relations = tuple(sorted(candidate_relations - source_relations))
    unsupported = tuple(sorted({
        claim.operation for claim in source.claims
        if claim.polarity == "required" and not claim.supported
    }))

    has_coverage_error = bool(
        missing_claims or extra_claims or conflicts
        or missing_relations or extra_relations
    )
    if unsupported:
        disposition = "reject"
    elif has_coverage_error:
        disposition = "clarify"
    elif not source.runtime_supported or source.expected_disposition == "clarify":
        disposition = "clarify"
    else:
        disposition = source.expected_disposition

    return CoverageReport(
        disposition=disposition,
        covered=tuple(covered),
        missing=tuple({
            "claim_id": claim.claim_id,
            "operation": claim.operation,
            "evidence_span": claim.evidence_span,
        } for claim in missing_claims),
        extra=tuple({
            "claim_id": claim.claim_id,
            "operation": claim.operation,
        } for claim in extra_claims),
        conflicts=tuple(conflicts),
        missing_relations=missing_relations,
        extra_relations=extra_relations,
        unsupported_operations=unsupported,
    )
