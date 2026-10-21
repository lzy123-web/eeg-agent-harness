"""Single-channel seizure inference migrated from EEGAgent.

The model is loaded lazily from an explicit external path. No weight file is
bundled with this project.
"""

from functools import lru_cache
from pathlib import Path

import torch
import torch.nn as nn

from .model_components import RoPETransformer
from ..record import EEGRecord


class ModelResourceError(RuntimeError):
    """Raised when an external model resource is missing or unusable."""


class SingleChannelEEG(nn.Module):
    def __init__(self, classes, embed_dim=128, num_heads=4):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(1, 16, kernel_size=3, stride=1, padding=1),
            nn.GELU(),
            nn.LayerNorm(256),
            nn.MaxPool1d(2, 2),
            nn.Conv1d(16, 16, kernel_size=3, stride=1, padding=1),
            nn.GELU(),
            nn.LayerNorm(128),
            nn.Conv1d(16, 32, kernel_size=3, stride=1, padding=1),
            nn.GELU(),
            nn.LayerNorm(128),
            nn.MaxPool1d(2, 2),
            nn.Conv1d(32, 64, kernel_size=3, stride=1, padding=1),
            nn.GELU(),
            nn.LayerNorm(64),
            nn.Conv1d(64, 64, kernel_size=3, stride=1, padding=1),
            nn.GELU(),
            nn.LayerNorm(64),
            nn.MaxPool1d(2, 2),
            nn.Conv1d(64, embed_dim, kernel_size=3, stride=1, padding=1),
            nn.GELU(),
            nn.LayerNorm(32),
        )
        self.attn_layers = nn.ModuleList(
            [RoPETransformer(embed_dim=embed_dim, num_heads=num_heads) for _ in range(2)]
        )
        self.pool = nn.AdaptiveAvgPool2d((1, embed_dim))
        self.fc = nn.Linear(embed_dim, classes)

    def forward(self, x):
        x = self.conv(x.unsqueeze(1)).transpose(1, 2)
        for layer in self.attn_layers:
            x, _ = layer(x)
        return self.fc(self.pool(x).squeeze(1))


@lru_cache(maxsize=4)
def load_seizure_model(model_path):
    path = Path(model_path).expanduser().resolve()
    if not path.is_file():
        raise ModelResourceError(f"Seizure model resource not found: {path}")

    model = SingleChannelEEG(classes=2)
    try:
        state_dict = torch.load(str(path), map_location="cpu", weights_only=True)
        model.load_state_dict(state_dict)
    except Exception as exc:
        raise ModelResourceError(f"Failed to load seizure model resource {path}: {exc}") from exc
    model.eval()
    return model


def seizureNormalModel_OneSecond(record: EEGRecord, name, start, end, config, model_path):
    if not 0 <= start < end:
        raise ValueError("Expected 0 <= start < end")
    if end - start > 10:
        raise ValueError("The time interval must not exceed 10 seconds")
    if record.sfreq != 256:
        raise ValueError("SingleChannelEEG requires a 256 Hz input")
    if not float(start).is_integer() or not float(end).is_integer():
        raise ValueError("SingleChannelEEG requires integer-second window boundaries")

    requested = (name,) if isinstance(name, str) else tuple(name)
    missing = [channel for channel in requested if channel not in record.channel_names]
    if missing:
        raise ValueError(f"Unknown EEG channel(s): {', '.join(missing)}")
    channels = sorted(requested, key=record.channel_names.index)
    data = record.slice(start, end, channels)
    model = load_seizure_model(str(Path(model_path).expanduser().resolve()))
    results = []

    start_second = int(start)
    end_second = int(end)
    for second_offset in range(end_second - start_second):
        start_index = second_offset * int(record.sfreq)
        end_index = (second_offset + 1) * int(record.sfreq)
        segment = data[:, start_index:end_index]
        if segment.shape[1] != 256:
            raise ValueError(f"Expected 256 samples per segment, got {segment.shape[1]}")
        tensor = torch.tensor(segment, dtype=torch.float32)
        with torch.no_grad():
            probabilities = torch.softmax(model(tensor), dim=-1)

        item = {"duration": f"{start_second + second_offset}s-{start_second + second_offset + 1}s"}
        for index, channel in enumerate(channels):
            item[channel] = {
                "Non-seiz": round(float(probabilities[index, 0].item()), 2),
                "seiz": round(float(probabilities[index, 1].item()), 2),
            }
        results.append(item)
    return results
