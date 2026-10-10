"""Scenario presets. Each preset is a set of *physical* parameters for the virtual panel;
the class / hotspot / action outputs are DERIVED by the pipeline, never hard-coded here."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace


@dataclass
class SimParams:
    irradiance_Wm2: float = 900.0
    background_temp_C: float = 40.0
    soiling_level: float = 0.02      # 0..1 (dust coverage)
    shading_fraction: float = 0.0    # 0..1 of panel area in shadow
    hotspot_enabled: bool = False
    hotspot_peak_C: float = 75.0
    hotspot_pixels: int = 4
    hotspot_row: int = 2
    hotspot_col: int = 2

    def to_dict(self) -> dict:
        return asdict(self)


PARAM_RANGES = {
    "irradiance_Wm2": (0, 1200),
    "background_temp_C": (10, 70),
    "soiling_level": (0, 1),
    "shading_fraction": (0, 0.9),
    "hotspot_peak_C": (40, 130),
    "hotspot_pixels": (1, 16),
    "hotspot_row": (0, 7),
    "hotspot_col": (0, 7),
}


def validate_params(changes: dict) -> dict:
    out = {}
    defaults = SimParams()
    for key, raw in changes.items():
        if not hasattr(defaults, key):
            raise ValueError(f"Unknown parameter: {key}")
        t = type(getattr(defaults, key))
        try:
            value = bool(raw) if t is bool else t(raw)
        except (TypeError, ValueError):
            raise ValueError(f"{key}: cannot convert {raw!r}")
        if key in PARAM_RANGES:
            lo, hi = PARAM_RANGES[key]
            if not (lo <= value <= hi):
                raise ValueError(f"{key}: {value} outside [{lo}, {hi}]")
        out[key] = value
    return out


@dataclass
class Scenario:
    id: str
    name: str
    description: str
    expected: str          # what a reviewer should expect to see (documentation only)
    params: SimParams


_BASE = SimParams()
_SOILED = replace(_BASE, soiling_level=0.6)
_SHADED = replace(_BASE, shading_fraction=0.35)
_HOT = dict(hotspot_enabled=True, hotspot_peak_C=75.0, hotspot_pixels=4, hotspot_row=2, hotspot_col=2)

SCENARIOS: dict[str, Scenario] = {s.id: s for s in [
    Scenario("healthy", "Healthy / Clean", "Clean panel, normal irradiance, uniform temperature.",
             "Healthy_Clean, no hotspot, no action.", _BASE),
    Scenario("soiled", "Soiled / Dusty", "Dust layer: uniform power loss and slight heat build-up.",
             "Soiling_Dusty; WAIT for 2 cycles, then START_CLEANING.", _SOILED),
    Scenario("shading", "Partial shading", "Shadow over part of the panel: cool thermal region, current collapse.",
             "Partial_Shading; TILT_PANEL requested.", _SHADED),
    Scenario("hotspot", "Hotspot detected", "Otherwise healthy panel with a localised hot cell cluster.",
             "Healthy_Clean + hotspot -> HOTSPOT_ALERT.", replace(_BASE, **_HOT)),
    Scenario("soiled_hotspot", "Soiling + hotspot", "Dusty panel that also shows a hot cell cluster.",
             "Soiling_Dusty preserved; HOTSPOT_ALERT_WITH_SOILING.", replace(_SOILED, **_HOT)),
    Scenario("shading_hotspot", "Partial shading + hotspot", "Shaded panel with a hot cell cluster.",
             "Partial_Shading preserved; HOTSPOT_ALERT_WITH_PARTIAL_SHADING.", replace(_SHADED, **_HOT)),
    Scenario("post_cleaning", "Normal after cleaning", "Panel that has just been cleaned: residual dust only.",
             "Healthy_Clean, deviation within threshold.", replace(_BASE, soiling_level=0.02)),
    Scenario("custom", "Custom", "Start from a healthy panel and set every parameter yourself.",
             "Whatever the pipeline derives from your parameters.", _BASE),
]}
