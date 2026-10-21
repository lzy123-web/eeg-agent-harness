"""Bipolar montage migrated from EEGAgent ``tools/polar.py``."""

BIPOLAR_PAIRS = [
    ("FP1", "F7"), ("F7", "T3"), ("T3", "T5"), ("T5", "O1"),
    ("FP2", "F8"), ("F8", "T4"), ("T4", "T6"), ("T6", "O2"),
    ("A1", "T3"), ("T3", "C3"), ("C3", "CZ"),
    ("CZ", "C4"), ("C4", "T4"), ("T4", "A2"),
    ("FP1", "F3"), ("F3", "C3"), ("C3", "P3"), ("P3", "O1"),
    ("FP2", "F4"), ("F4", "C4"), ("C4", "P4"), ("P4", "O2"),
]

INDEX_TO_NAME = {i: f"{left}-{right}" for i, (left, right) in enumerate(BIPOLAR_PAIRS)}
REVERSED_INDEX_TO_NAME = {i: f"{right}-{left}" for i, (left, right) in enumerate(BIPOLAR_PAIRS)}
NAME_TO_INDEX = {
    **{name: index for index, name in INDEX_TO_NAME.items()},
    **{name: index for index, name in REVERSED_INDEX_TO_NAME.items()},
}
