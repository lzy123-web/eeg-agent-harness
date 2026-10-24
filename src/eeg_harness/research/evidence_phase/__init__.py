"""Independent evidence-phase fixtures and oracles for CCEP research."""

from .oracle import oracle_event_bandpower, oracle_epoch_data
from .synthetic import SyntheticEpochTruth, build_quality_selection_record

__all__ = [
    "SyntheticEpochTruth",
    "build_quality_selection_record",
    "oracle_epoch_data",
    "oracle_event_bandpower",
]
