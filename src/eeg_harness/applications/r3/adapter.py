"""Application-layer R3 adaptation and de-identified resource diagnostics."""

from collections import Counter
import csv
from dataclasses import dataclass
from dataclasses import replace
import hashlib
from pathlib import Path

import mne

from ...edf import load_edf
from ...events import EEGEvent, EventSet
from ...profiles import TaskProfile


R3_EEG_CHANNELS = (
    "P3", "C3", "F3", "Fz", "F4", "C4", "P4", "Cz", "A1", "Fp1", "Fp2",
    "T3", "T5", "O1", "O2", "F7", "F8", "A2", "T6", "T4", "Pz",
)

R3_PROFILE = TaskProfile(
    profile_id="r3_fine_motor",
    description="R3 application profile; file structure verified, task meaning remains unverified",
    adapter="configured_native",
    reference="average reference applied by Harness",
    montage="observed 21-channel 10-20 layout",
    required_channels=R3_EEG_CHANNELS,
    target_sfreq=300.0,
    max_window_seconds=60.0,
    compatible_tools=(
        "record_info", "amplitude", "psd", "list_events", "create_epochs",
        "epoch_summary", "event_bandpower",
        "record_quality", "epoch_quality",
        "select_quality_epochs",
    ),
    l_freq=1.0,
    h_freq=40.0,
    notch_freq=50.0,
    average_reference=True,
)


@dataclass(frozen=True)
class R3DatasetRules:
    analysis_labels: tuple[str, ...] = tuple(str(value) for value in range(1, 9))
    boundary_labels: tuple[str, ...] = ("9",)
    boundary_rule_status: str = "candidate_from_local_statistics; scientific meaning unverified"
    epoch_window: tuple[float, float] = (-0.2, 0.8)
    baseline: tuple[float, float] = (-0.2, 0.0)


def load_r3_edf(path):
    """Load one R3 EDF without deriving participant or group semantics."""

    return load_edf(path, R3_PROFILE, selected_channels=R3_EEG_CHANNELS)


def attach_external_event_table(record, table_path, onset_offset_seconds=0.0):
    """Attach an explicit CSV event table aligned to the record start."""

    path = Path(table_path).expanduser().resolve()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    events = []
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"onset_seconds", "label"}
        if not required.issubset(reader.fieldnames or ()):
            raise ValueError("External event table requires onset_seconds and label columns")
        for index, row in enumerate(reader):
            onset = float(row["onset_seconds"]) + float(onset_offset_seconds)
            duration = float(row.get("duration_seconds") or 0.0)
            label = str(row["label"]).strip()
            if not label or onset < 0 or onset > record.duration_seconds or duration < 0:
                raise ValueError(f"Invalid external event row {index + 2}")
            events.append(EEGEvent(label, onset, duration, index))
    source = f"external-table-sha256:{digest}"
    return replace(record, events=EventSet(tuple(events), source=source))


def diagnose_r3_files(paths):
    """Inspect local EDF resources and return only aggregate, de-identified facts."""

    files = [Path(path).expanduser().resolve() for path in paths]
    if not files:
        return {"file_count": 0, "status": "no_files"}
    layouts = set()
    rates = set()
    event_counts = []
    labels = Counter()
    durations = []
    for path in files:
        if not path.is_file():
            raise FileNotFoundError("Configured R3 EDF resource is missing")
        raw = mne.io.read_raw_edf(str(path), preload=False, verbose=False)
        eeg_names = tuple(
            name for name, kind in zip(raw.ch_names, raw.get_channel_types()) if kind == "eeg"
        )
        layouts.add(eeg_names)
        rates.add(float(raw.info["sfreq"]))
        descriptions = [str(item) for item in raw.annotations.description]
        labels.update(descriptions)
        event_counts.append(len(descriptions))
        durations.append(float(raw.n_times / raw.info["sfreq"]))
    return {
        "file_count": len(files),
        "status": "inspected",
        "eeg_channel_count_values": sorted({len(item) for item in layouts}),
        "channel_layout_count": len(layouts),
        "sampling_rates_hz": sorted(rates),
        "annotation_labels": sorted(labels),
        "event_count_range": [min(event_counts), max(event_counts)],
        "duration_seconds_range": [min(durations), max(durations)],
        "profile_contract_matches": layouts == {R3_EEG_CHANNELS} and rates == {300.0},
        "group_semantics_verified": False,
        "label_meanings_verified": False,
    }
