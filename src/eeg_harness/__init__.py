"""Deterministic EEG analysis baseline without an LLM dependency."""

from .agent import EEGAgent
from .pipeline import run_baseline
from .profiles import EDF_NATIVE, TUEV_BIPOLAR_22, TaskProfile
from .record import EEGContext, EEGRecord

__all__ = [
    "EDF_NATIVE",
    "EEGAgent",
    "EEGContext",
    "EEGRecord",
    "TUEV_BIPOLAR_22",
    "TaskProfile",
    "run_baseline",
]
__version__ = "0.3.0"
