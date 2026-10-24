"""Frozen evidence-phase corpus validation and canonical hashing."""

import hashlib
import json
from pathlib import Path


def canonical_payload(payload):
    normalized = dict(payload)
    normalized.pop("corpus_sha256", None)
    return json.dumps(
        normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def corpus_hash(payload):
    return hashlib.sha256(canonical_payload(payload)).hexdigest()


def load_protocol(path="config/point1_evidence_phase_v1.json"):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    if len(cases) != 24 or len({item["case_id"] for item in cases}) != 24:
        raise ValueError("Evidence-phase corpus must contain 24 unique cases")
    if {item["split"] for item in cases} != {"development", "holdout"}:
        raise ValueError("Evidence-phase corpus requires development and holdout splits")
    actual = corpus_hash(payload)
    if payload.get("corpus_sha256") != actual:
        raise ValueError(f"Evidence-phase corpus hash mismatch: {actual}")
    return payload
