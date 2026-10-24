"""Frozen protocol loader for EEG Intent Compiler v1."""

import hashlib
import json
from pathlib import Path


FROZEN_SHA256 = "b14fcb611ac2f8c854fb5b543860f2e76597be4b4e13ddf576f6ce95d544af9f"


def load_protocol(path="config/eeg_intent_compiler_v1_cases.json"):
    raw = Path(path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != FROZEN_SHA256:
        raise ValueError(f"Intent protocol hash mismatch: {digest}")
    protocol = json.loads(raw.decode("utf-8"))
    if len(protocol["cases"]) != 30:
        raise ValueError("Intent protocol must contain exactly 30 frozen cases")
    return protocol, digest

