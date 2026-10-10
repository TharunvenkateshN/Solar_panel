"""Feature preparation for the condition classifier.

The trained model (notebook Section 6/11) expects 19 scalar features taken from a full
I-V curve sweep. This project has no sweep hardware, so the curve is SYNTHESISED from the
operating point (single-diode-style empirical curve) and fed through the notebook's own
`extract_iv_features`. This keeps the adapter contract identical to the notebook schema:
when the real model is dropped in, nothing else needs to change.

`derived` holds extra values used ONLY by the simulated stand-in classifier.
"""
from __future__ import annotations

import math

import numpy as np

from ..config import SimConfig

FEATURE_COLS = [
    "Voc", "Isc", "Vmpp", "Impp", "Pmpp",
    "Max_Voltage", "Min_Voltage", "Max_Current", "Min_Current",
    "Max_Power", "Min_Power", "Mean_Voltage", "Mean_Current", "Mean_Power",
    "Voltage_Range", "Current_Range", "Power_Range",
    "Irradiance", "Temperature",
]


def extract_iv_features(V, I, irradiance=None, temperature=None, label=None,
                        source="unknown", curve_idx=None) -> dict:
    """Ported verbatim from notebook Section 6.1."""
    P = V * I
    mask = V > 0
    if mask.sum() < 5:
        mask = np.ones(len(V), dtype=bool)
    Vv, Iv, Pv = V[mask], I[mask], P[mask]
    try:
        isc_val = Iv.max()
        voc_region = Pv < (Pv.max() * 0.01)
        voc_val = Vv[voc_region].max() if voc_region.any() else Vv.max()
    except Exception:
        isc_val = Iv.max()
        voc_val = Vv.max()
    mpp_idx = np.argmax(Pv)
    return {
        "source": source, "curve_idx": curve_idx, "label": label,
        "Irradiance": irradiance, "Temperature": temperature,
        "Voc": voc_val, "Isc": isc_val,
        "Vmpp": Vv[mpp_idx], "Impp": Iv[mpp_idx], "Pmpp": Pv[mpp_idx],
        "Max_Voltage": Vv.max(), "Min_Voltage": Vv.min(),
        "Max_Current": Iv.max(), "Min_Current": Iv.min(),
        "Max_Power": Pv.max(), "Min_Power": Pv.min(),
        "Mean_Voltage": Vv.mean(), "Mean_Current": Iv.mean(), "Mean_Power": Pv.mean(),
        "Voltage_Range": Vv.max() - Vv.min(), "Current_Range": Iv.max() - Iv.min(),
        "Power_Range": Pv.max() - Pv.min(),
        "N_points": len(Vv),
    }


def synthesize_iv_curve(v_op: float, i_op: float, n: int = 100,
                        vmpp_over_voc: float = 0.82, impp_over_isc: float = 0.92):
    """Empirical single-diode-style curve passing exactly through (v_op, i_op)."""
    v_op = max(v_op, 1e-3)
    i_op = max(i_op, 1e-4)
    voc = v_op / vmpp_over_voc
    isc = i_op / impp_over_isc
    c2 = (v_op / voc - 1) / math.log(1 - i_op / isc)
    c1 = (1 - i_op / isc) * math.exp(-v_op / (c2 * voc))
    V = np.linspace(0, voc, n)
    I = np.clip(isc * (1 - c1 * (np.exp(V / (c2 * voc)) - 1)), 0, None)
    return V, I


def cool_pixel_count(grid: np.ndarray, delta: float, hot_gap: float = 11.0) -> tuple[int, float]:
    """Pixels clearly cooler than the panel's normal (warm) level - the signature of a shadow.

    Works for any shaded fraction (a median would fail once more than half the panel is shaded):
      1. a jump of >= `hot_gap` degC above the bulk marks a hotspot cluster, which is ignored here
         (hotspot jumps are >= 11 degC, shadows cool by only 4-10 degC);
      2. the remaining values split into clusters at gaps >= `delta`; the hottest cluster is the normal level;
      3. cool pixels = pixels more than `delta` below that level.
    """
    v = np.sort(grid.ravel())
    jumps = np.where(np.diff(v) >= hot_gap)[0]
    if len(jumps) and len(v) - (jumps[0] + 1) <= 25:
        v = v[: jumps[0] + 1]
    clusters = np.split(v, np.where(np.diff(v) >= delta)[0] + 1)
    reference = float(np.median(clusters[-1]))
    return int((v < reference - delta).sum()), reference


def build_feature_bundle(v: float, i: float, irradiance_wm2: float | None, temp_c: float,
                         expected_power_w: float, grid: np.ndarray, cfg: SimConfig) -> dict:
    V, I = synthesize_iv_curve(v, i)
    feats = extract_iv_features(V, I, irradiance=irradiance_wm2, temperature=temp_c, source="synthesized_from_operating_point")
    iv_features = {c: float(feats[c]) if feats[c] is not None else float("nan") for c in FEATURE_COLS}

    cool_pixels, reference = cool_pixel_count(grid, cfg.classifier_cool_delta_c)
    p = v * i
    derived = {
        "power_ratio": round(p / expected_power_w, 4) if expected_power_w > 0 else None,
        "expected_power_W_ref": expected_power_w,
        "thermal_reference_C": round(reference, 3),
        "cool_pixel_count": cool_pixels,
    }
    step = max(1, len(V) // 25)
    return {
        "iv_features": iv_features,
        "derived": derived,
        "curve": {"V": [round(float(x), 3) for x in V[::step]], "I": [round(float(x), 4) for x in I[::step]]},
        "provenance": "I-V curve synthesised from the simulated operating point (no sweep hardware).",
    }
