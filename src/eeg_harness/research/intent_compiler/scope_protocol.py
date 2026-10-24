"""Frozen protocol loader for the EEG goal-scope safety evaluation."""

import hashlib
import json
from pathlib import Path


FROZEN_SCOPE_SHA256 = "e6d47bd3c38eaf0efa26e8b7e8bcab32bf535b5faf5d774ffae2db80b1c1d250"


def load_scope_protocol(path="config/eeg_intent_scope_v2_cases.json"):
    raw = Path(path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != FROZEN_SCOPE_SHA256:
        raise ValueError(f"Scope protocol hash mismatch: {digest}")
    protocol = json.loads(raw.decode("utf-8"))
    if len(protocol["cases"]) != 20:
        raise ValueError("Scope protocol must contain exactly 20 frozen cases")
    return protocol, digest
