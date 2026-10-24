"""Offline controlled-gold pilot for EEG goal-completeness diagnostics.

This research package is intentionally separate from the production intent,
TGSRG, CIEDG, planner, and executor paths.
"""

from .matcher import compare_contracts
from .models import CoverageReport, ScientificClaim, ScientificContract
from .protocol import load_protocol, parse_controlled_request

__all__ = [
    "CoverageReport",
    "ScientificClaim",
    "ScientificContract",
    "compare_contracts",
    "load_protocol",
    "parse_controlled_request",
]
