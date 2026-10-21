"""Deterministic EEG analysis baseline without an LLM dependency."""

from .pipeline import run_baseline
from .record import EEGContext, EEGRecord

__all__ = ["EEGContext", "EEGRecord", "run_baseline"]
__version__ = "0.2.0"
