"""Rule-based hotspot detector - ported from notebook Section 15.

Independent of the ML classifier. Hotspot is NOT a fourth ML class.
Rule (unchanged): YES when max > abs threshold, OR (max-mean > delta threshold
AND hot_pixel_count >= pixel threshold). Thresholds are provisional.
"""
from __future__ import annotations

import numpy as np

from ..config import SimConfig
from .thermal import extract_thermal_features


class HotspotDetector:
    def __init__(self, config: SimConfig):
        self.config = config

    def detect(self, grid: np.ndarray) -> dict:
        c = self.config
        feats = extract_thermal_features(grid)
        cond_abs = feats["max_temp_C"] > c.hotspot_abs_thresh_c
        cond_delta = (feats["max_minus_mean_C"] > c.hotspot_delta_thresh_c
                      and feats["hot_pixel_count"] >= c.hot_pixel_thresh)
        return {
            **feats,
            "hotspot_detected": "YES" if (cond_abs or cond_delta) else "NO",
            "cond_abs_triggered": bool(cond_abs),
            "cond_delta_triggered": bool(cond_delta),
            "thresholds": {
                "abs_thresh": c.hotspot_abs_thresh_c,
                "delta_thresh": c.hotspot_delta_thresh_c,
                "hot_px_thresh": c.hot_pixel_thresh,
            },
            "PROVISIONAL": "Thresholds not experimentally calibrated",
        }
