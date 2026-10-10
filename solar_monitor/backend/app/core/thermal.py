"""Virtual AMG8833 8x8 thermal camera and thermal feature extraction.

Ported from notebook Section 14. The original named-scenario ``read`` is preserved;
``read_parametric`` is the website's controllable variant (background temperature,
hotspot peak/area/position, shaded area) so UI sliders change the actual grid.
"""
from __future__ import annotations

import math

import numpy as np

from ..topics import utc_now


def _nearest_pixels(row: int, col: int, n: int, rows: int = 8, cols: int = 8):
    """The n pixels closest to (row, col), nearest first. Returns [(r, c, dist)]."""
    px = [(r, c, math.hypot(r - row, c - col)) for r in range(rows) for c in range(cols)]
    px.sort(key=lambda t: (t[2], t[0], t[1]))
    return px[: max(0, min(n, rows * cols))]


class VirtualAMG8833:
    GRID_ROWS = 8
    GRID_COLS = 8

    def __init__(self, name="AMG8833_sim", rng_seed=None):
        self.name = name
        self._rng = np.random.default_rng(rng_seed)

    def _base_grid(self, base_temp=40.0, noise_std=0.5):
        return base_temp + self._rng.normal(0, noise_std, (self.GRID_ROWS, self.GRID_COLS))

    def read(self, scenario="normal") -> dict:
        """Original notebook scenarios (kept for reference/tests)."""
        if scenario == "normal":
            grid = self._base_grid(40.0, 0.8)
        elif scenario == "mild_variation":
            grid = self._base_grid(42.0, 1.5)
            for r in range(self.GRID_ROWS):
                grid[r, :] += r * 0.3
        elif scenario == "hotspot":
            grid = self._base_grid(41.0, 0.8)
            hr = self._rng.integers(1, self.GRID_ROWS - 2)
            hc = self._rng.integers(1, self.GRID_COLS - 2)
            grid[hr:hr + 2, hc:hc + 2] += self._rng.uniform(18, 28, (2, 2))
        elif scenario == "soiling":
            grid = self._base_grid(44.0, 1.0)
        elif scenario == "shading":
            grid = self._base_grid(40.0, 0.6)
            grid[4:8, 4:8] -= self._rng.uniform(4, 8, (4, 4))
        else:
            raise ValueError(f"Unknown scenario: {scenario}")
        return {"sensor": self.name, "scenario": scenario, "grid": grid.round(2), "timestamp": utc_now()}

    def read_parametric(self, background_C: float, noise_std: float = 0.7,
                        soiling_rise_C: float = 0.0,
                        shade_pixels: int = 0, shade_delta_C: float = 0.0,
                        hotspot_peak_C: float | None = None, hotspot_pixels: int = 0,
                        hotspot_row: int = 2, hotspot_col: int = 2) -> dict:
        grid = self._base_grid(background_C + soiling_rise_C, noise_std)
        # Shaded region: cooler, anchored at the bottom-right corner.
        for r, c, _ in _nearest_pixels(7, 7, shade_pixels):
            grid[r, c] -= shade_delta_C + self._rng.normal(0, 0.3)
        # Hotspot cluster: hottest at the centre pixel, falling off with distance.
        if hotspot_peak_C is not None and hotspot_pixels > 0:
            for r, c, d in _nearest_pixels(hotspot_row, hotspot_col, hotspot_pixels):
                noise = 0.0 if d == 0 else self._rng.normal(0, 0.4)
                grid[r, c] = hotspot_peak_C - 1.5 * d + noise
        return {"sensor": self.name, "grid": grid.round(2), "timestamp": utc_now()}


def extract_thermal_features(grid: np.ndarray) -> dict:
    """Scalar thermal features. Feeds hotspot detection (NOT the ML classifier).

    Notebook rule preserved: hot pixel = value > mean + 2*std. The pixel list and
    threshold are additive outputs so the UI can highlight contributing pixels.
    """
    flat = grid.flatten()
    mean_t = float(flat.mean())
    max_t = float(flat.max())
    min_t = float(flat.min())
    hot_thresh = mean_t + 2 * float(flat.std())
    hot_mask = grid > hot_thresh
    row_idx, col_idx = np.unravel_index(np.argmax(grid), grid.shape)
    return {
        "mean_temp_C": round(mean_t, 3),
        "max_temp_C": round(max_t, 3),
        "min_temp_C": round(min_t, 3),
        "temp_range_C": round(max_t - min_t, 3),
        "max_minus_mean_C": round(max_t - mean_t, 3),
        "hot_pixel_count": int(hot_mask.sum()),
        "hotspot_row": int(row_idx),
        "hotspot_col": int(col_idx),
        # additive (not in notebook):
        "hot_threshold_C": round(hot_thresh, 3),
        "hot_pixels": [[int(r), int(c)] for r, c in zip(*np.nonzero(hot_mask))],
    }
