"""Read and validate the append-only formal evaluation supplement."""

import hashlib
import json
from pathlib import Path


DEFAULT_CASES = Path("config/point1_formal_eval_cases_v1.json")
FROZEN_CANDIDATE_SHA = "921b04a561b27c2e68964d5f3f1e995ee08c8c6d"
FROZEN_SUPPLEMENT_SHA256 = "43e7fb634ff1eb246e2685a0831bf28c3bf08bed05f481bb36a8ebc5e45d49f2"


def load_cases(path=DEFAULT_CASES, *, verify_hash=True):
    path = Path(path)
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if verify_hash and path.as_posix().endswith(DEFAULT_CASES.as_posix()):
        if digest != FROZEN_SUPPLEMENT_SHA256:
            raise ValueError("Formal case supplement hash does not match the frozen value")
    payload = json.loads(raw)
    if payload["candidate_sha"] != FROZEN_CANDIDATE_SHA:
        raise ValueError("Formal case supplement names a different candidate SHA")
    if len(payload["cases"]) != 24:
        raise ValueError("Formal case supplement must contain exactly 24 cases")
    return payload, digest
