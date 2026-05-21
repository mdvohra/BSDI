"""ResNet50 + DeepLabV3+ assembly matching HTSM checkpoint keys: encoder.*, segmenter.*."""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

from oil_spill.htsm.encoder_models import resnet50
from oil_spill.htsm.decoder_models import DeepLabV3Plus


class ResNet50DeepLabV3Plus(nn.Module):
    def __init__(self, num_classes: int = 5, pretrained: bool = True):
        super().__init__()
        self.encoder = resnet50(pretrained=pretrained)
        self.segmenter = DeepLabV3Plus(
            in_channels=2048,
            encoder_channels=64,
            num_classes=num_classes,
            encoder_projection_channels=48,
            aspp_out_channels=256,
            final_out_channels=256,
            aspp_dilate=[12, 24, 36],
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        encoded = self.encoder(x)
        block_1 = self.encoder.dict_encoder_features["block_1"]
        logits = self.segmenter(encoded, block_1)
        logits = F.interpolate(
            logits,
            size=x.shape[2:],
            mode="bilinear",
            align_corners=False,
        )
        return logits
