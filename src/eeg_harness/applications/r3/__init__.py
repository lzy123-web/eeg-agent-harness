"""R3 fine-motor EEG application adapter.

The adapter encodes observed file structure and explicit local rules.  It does
not assign clinical groups or infer participant identity from file names.
"""

from .adapter import (
    R3DatasetRules,
    R3_PROFILE,
    attach_external_event_table,
    diagnose_r3_files,
    load_r3_edf,
)

__all__ = [
    "R3DatasetRules", "R3_PROFILE", "attach_external_event_table",
    "diagnose_r3_files", "load_r3_edf",
]
