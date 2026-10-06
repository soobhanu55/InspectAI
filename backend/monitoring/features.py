"""Cheap image statistics for drift detection (numpy only, no extra dependency)."""
from __future__ import annotations

import numpy as np
from PIL import Image


def image_stats(image: Image.Image) -> tuple[float, float, float]:
    """(brightness, contrast, sharpness) of a frame: mean gray level, gray-level std, variance of the Laplacian."""
    g = np.asarray(image.convert("L"), dtype=np.float64)
    lap = 4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:]
    return float(g.mean()), float(g.std()), float(lap.var())
