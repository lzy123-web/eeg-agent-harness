"""Deterministic EEG analysis baseline without an LLM dependency."""

from .pipeline import run_baseline
from .profiles import EDF_NATIVE, TUEV_BIPOLAR_22, TaskProfile
from .record import EEGContext, EEGRecord

__all__ = [
    "EDF_NATIVE",
    "EEGContext",
    "EEGRecord",
    "TUEV_BIPOLAR_22",
    "TaskProfile",
    "run_baseline",
]
__version__ = "0.2.0"
