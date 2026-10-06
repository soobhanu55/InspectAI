"""Statistical checks over a sliding window of frame records, each compared with a baseline fitted on frames
assumed to be in control. A detector returns a Breach when the window looks different from the baseline.

  HitRateShift    Fisher's exact test on "frame had a detection": the share of defective frames differs between
                  baseline and window. Exact, because the share is often near 100% (or 0%), where the usual
                  mean +/- 3 sigma control limits are far too tight and false-alarm on healthy lines
  ClassMixDrift   chi-square test of homogeneity: the mix of defect classes differs between baseline and window
  FeatureDrift    two-sample Kolmogorov-Smirnov test on an image statistic or on detection confidence
  LatencySLO      the window's p95 latency exceeded a limit (fixed, or a multiple of the baseline p95)
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from scipy import stats

from monitoring.records import FrameRecord


@dataclass
class Breach:
    name: str
    message: str
    severity: str = "warning"
    details: dict = field(default_factory=dict)


class HitRateShift:
    """Two-sided Fisher exact test on the 2 x 2 table (baseline vs window) x (frame had a detection or not).
    A shift UP means more defects than usual; a shift DOWN is just as important, because a dirty lens or a dead camera
    makes a model find nothing, which looks like a perfect production line.

    An earlier version used control limits p +/- 3.5 sigma. On real detector output the hit rate was 97%, the count of
    missed frames per window is then a skewed, Poisson-like count, the normal limits were far too tight in the upper
    tail, and 9% of healthy 900-frame runs raised a false alarm, all from this detector."""

    name = "defect_rate"

    def __init__(self, alpha: float = 1e-4):
        self.alpha = alpha
        self.hits = self.n = 0

    def fit(self, baseline: list[FrameRecord]) -> None:
        self.n = len(baseline)
        self.hits = sum(r.has_defect for r in baseline)

    def check(self, window: list[FrameRecord]) -> Breach | None:
        n = len(window)
        hits = sum(r.has_defect for r in window)
        _, p = stats.fisher_exact([[self.hits, self.n - self.hits], [hits, n - hits]])
        if p >= self.alpha:
            return None
        base, rate = self.hits / self.n, hits / n
        d = {"window_rate": round(rate, 3), "baseline_rate": round(base, 3), "p_value": float(p)}
        if rate > base:
            return Breach(self.name, f"defect rate {rate:.0%} is above the baseline {base:.0%} (exact test p={p:.1e})", "critical", d)
        return Breach(self.name, f"defect rate {rate:.0%} is below the baseline {base:.0%} (exact test p={p:.1e}); "
                                 "check the camera and lighting", "critical", d)


class ClassMixDrift:
    """Chi-square test of homogeneity (2 x K table: baseline vs window counts per defect class). Comparing the window
    with the baseline PROPORTIONS as if they were known would ignore that the baseline mix is itself estimated from a
    few dozen defects, and false-alarms often on a healthy line."""

    name = "class_mix_drift"

    def __init__(self, alpha: float = 1e-4, min_defects: int = 20):
        self.alpha, self.min_defects = alpha, min_defects
        self.base: Counter = Counter()

    def fit(self, baseline: list[FrameRecord]) -> None:
        self.base = Counter(r.top_class for r in baseline if r.top_class)

    def check(self, window: list[FrameRecord]) -> Breach | None:
        win = Counter(r.top_class for r in window if r.top_class)
        if sum(win.values()) < self.min_defects or sum(self.base.values()) < self.min_defects:
            return None
        classes = sorted(set(self.base) | set(win))  # a class absent from the baseline counts as a difference
        table = np.array([[self.base[c] for c in classes], [win[c] for c in classes]], dtype=float)
        table = table[:, table.sum(axis=0) > 0]
        if table.shape[1] < 2:
            return None
        _, p, _, _ = stats.chi2_contingency(table)
        if p < self.alpha:
            top = max(win, key=win.get)
            return Breach(self.name, f"the mix of defect classes changed (chi-square p={p:.1e}; most frequent now: {top})",
                          "warning", {"p_value": float(p), "baseline": dict(self.base), "window": dict(win)})
        return None


class FeatureDrift:
    """KS test between the baseline sample and the window for one numeric feature of the records."""

    def __init__(self, name: str, getter: Callable[[FrameRecord], float], alpha: float = 1e-4,
                 only_defects: bool = False, min_n: int = 20):
        self.name, self.getter, self.alpha, self.only_defects, self.min_n = name, getter, alpha, only_defects, min_n
        self.base = np.array([])

    def _values(self, recs: list[FrameRecord]) -> np.ndarray:
        return np.array([self.getter(r) for r in recs if r.has_defect or not self.only_defects])

    def fit(self, baseline: list[FrameRecord]) -> None:
        self.base = self._values(baseline)

    def check(self, window: list[FrameRecord]) -> Breach | None:
        win = self._values(window)
        if len(win) < self.min_n or len(self.base) < self.min_n:
            return None
        res = stats.ks_2samp(self.base, win)
        if res.pvalue < self.alpha:
            return Breach(self.name, f"{self.name.removeprefix('drift_')} shifted from the baseline "
                                     f"(median {np.median(self.base):.3g} -> {np.median(win):.3g}, KS p={res.pvalue:.1e})",
                          "warning", {"ks_statistic": float(res.statistic), "p_value": float(res.pvalue),
                                      "baseline_median": float(np.median(self.base)), "window_median": float(np.median(win))})
        return None


class LatencySLO:
    name = "latency_slo"

    def __init__(self, limit_ms: float | None = None, factor: float = 2.0):
        self.limit_ms, self.factor = limit_ms, factor
        self.limit: float | None = limit_ms

    def fit(self, baseline: list[FrameRecord]) -> None:
        if self.limit_ms is None:
            self.limit = self.factor * float(np.percentile([r.latency_ms for r in baseline], 95))

    def check(self, window: list[FrameRecord]) -> Breach | None:
        p95 = float(np.percentile([r.latency_ms for r in window], 95))
        if self.limit is not None and p95 > self.limit:
            return Breach(self.name, f"p95 latency {p95:.0f} ms exceeds the limit {self.limit:.0f} ms", "warning",
                          {"p95_ms": p95, "limit_ms": self.limit})
        return None


def default_detectors() -> list:
    return [
        HitRateShift(),
        ClassMixDrift(),
        FeatureDrift("drift_brightness", lambda r: r.brightness),
        FeatureDrift("drift_contrast", lambda r: r.contrast),
        FeatureDrift("drift_sharpness", lambda r: r.sharpness),
        FeatureDrift("drift_confidence", lambda r: r.confidence, only_defects=True),
        LatencySLO(),
    ]
