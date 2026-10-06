"""One processed camera frame, reduced to what the monitor needs."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FrameRecord:
    has_defect: bool
    top_class: str | None  # class of the highest-confidence detection, None if nothing was detected
    confidence: float  # that detection's confidence, 0.0 if nothing was detected
    brightness: float  # mean gray level
    contrast: float  # gray-level standard deviation
    sharpness: float  # variance of the Laplacian: drops when the image is blurred or out of focus
    latency_ms: float  # time to preprocess + detect this frame
