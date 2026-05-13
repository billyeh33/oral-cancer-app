from __future__ import annotations

from typing import Tuple

import torch
from torch import nn
from torchvision.models import ConvNeXt_Tiny_Weights, convnext_tiny


DEFAULT_DROPOUT = 0.32594504304690466


class HierarchicalConvNeXt(nn.Module):
    """Three-head ConvNeXt-Tiny model used by the screening prototype."""

    def __init__(
        self,
        dropout: float = DEFAULT_DROPOUT,
        initialize_from_imagenet: bool = True,
    ) -> None:
        super().__init__()
        weights = (
            ConvNeXt_Tiny_Weights.DEFAULT if initialize_from_imagenet else None
        )
        base = convnext_tiny(weights=weights)
        self.backbone = nn.Sequential(base.features, base.avgpool)
        feat_dim = base.classifier[2].in_features

        def _head() -> nn.Sequential:
            return nn.Sequential(
                nn.LayerNorm(feat_dim),
                nn.Dropout(p=dropout),
                nn.Linear(feat_dim, 2),
            )

        self.head_s1 = _head()
        self.head_s2 = _head()
        self.head_s3 = _head()

    def forward(
        self,
        x: torch.Tensor,
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        feat = self.backbone(x).flatten(1)
        return self.head_s1(feat), self.head_s2(feat), self.head_s3(feat)
