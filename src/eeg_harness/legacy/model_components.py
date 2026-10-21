"""RoPE transformer components migrated from EEGAgent ``tools/localModels/net.py``."""

import math

import torch
import torch.nn as nn
from torch.nn import functional as F


def rope(x):
    batch, length, channels = x.shape
    theta = 10000 ** (-torch.arange(0, channels, 2, device=x.device) / channels)
    positions = torch.arange(length, device=x.device).unsqueeze(1)
    angles = positions * theta
    cos = torch.cos(angles)
    sin = torch.sin(angles)
    x1, x2 = x[:, :, ::2], x[:, :, 1::2]
    rotated_x1 = x1 * cos - x2 * sin
    rotated_x2 = x1 * sin + x2 * cos
    return torch.stack([rotated_x1, rotated_x2], dim=-1).flatten(-2)


class MultiHeadSelfAttentionRoPE(nn.Module):
    def __init__(self, embed_dim, num_heads):
        super().__init__()
        if embed_dim % num_heads != 0:
            raise ValueError("embed_dim must be divisible by num_heads")
        self.embed_dim = embed_dim
        self.num_heads = num_heads
        self.head_dim = embed_dim // num_heads
        self.q_proj = nn.Linear(embed_dim, embed_dim)
        self.k_proj = nn.Linear(embed_dim, embed_dim)
        self.v_proj = nn.Linear(embed_dim, embed_dim)
        self.out_proj = nn.Linear(embed_dim, embed_dim)

    def forward(self, x, pad_mask=None):
        batch, length, _ = x.shape
        q = self.q_proj(x).view(batch, length, self.num_heads, self.head_dim).transpose(1, 2)
        k = self.k_proj(x).view(batch, length, self.num_heads, self.head_dim).transpose(1, 2)
        v = self.v_proj(x).view(batch, length, self.num_heads, self.head_dim).transpose(1, 2)
        q = rope(q.reshape(batch * self.num_heads, length, self.head_dim))
        k = rope(k.reshape(batch * self.num_heads, length, self.head_dim))
        q = q.view(batch, self.num_heads, length, self.head_dim)
        k = k.view(batch, self.num_heads, length, self.head_dim)
        scores = torch.matmul(q, k.transpose(-2, -1)) / math.sqrt(self.head_dim)
        if pad_mask is not None:
            scores = scores.masked_fill(pad_mask[:, None, None, :] == 0, float("-inf"))
        probabilities = F.softmax(scores, dim=-1)
        output = torch.matmul(probabilities, v)
        output = output.transpose(1, 2).contiguous().view(batch, length, self.embed_dim)
        return self.out_proj(output), probabilities


class FeedForward(nn.Module):
    def __init__(self, embed_dim, drop_p=0.1):
        super().__init__()
        self.c_fc = nn.Linear(embed_dim, 4 * embed_dim)
        self.GELU = nn.GELU(approximate="tanh")
        self.c_proj = nn.Linear(4 * embed_dim, embed_dim)
        self.drop = nn.Dropout(drop_p)

    def forward(self, x):
        x = self.c_fc(x)
        x = self.GELU(x)
        x = self.c_proj(x)
        return self.drop(x)


class RoPETransformer(nn.Module):
    def __init__(self, embed_dim, num_heads):
        super().__init__()
        self.ln1 = nn.LayerNorm(embed_dim)
        self.RoPEAttention = MultiHeadSelfAttentionRoPE(embed_dim, num_heads)
        self.ln2 = nn.LayerNorm(embed_dim)
        self.ffn = FeedForward(embed_dim)

    def forward(self, x, mask=None):
        normalized = self.ln1(x)
        attended, attention = self.RoPEAttention(normalized, pad_mask=mask)
        x = x + attended
        x = x + self.ffn(self.ln2(x))
        return x, attention
