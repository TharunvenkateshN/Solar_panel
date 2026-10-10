"""Virtual INA219 and BH1750 - ported from notebook Sections 12-13.

All readings are SOFTWARE-GENERATED. Nothing here talks to hardware.
"""
from __future__ import annotations

import numpy as np

from ..topics import utc_now


class VirtualINA219:
    """Voltage/current sensor simulation. Power is always P = V * I."""

    def __init__(self, name="INA219_sim", v_range=(0, 30), i_range=(0, 10)):
        self.name = name
        self.v_range = v_range
        self.i_range = i_range
        self._last: dict = {}

    def read(self, voltage: float, current: float) -> dict:
        if not (self.v_range[0] <= voltage <= self.v_range[1]):
            raise ValueError(f"Voltage {voltage} V out of range {self.v_range}")
        if not (self.i_range[0] <= current <= self.i_range[1]):
            raise ValueError(f"Current {current} A out of range {self.i_range}")
        power = voltage * current
        self._last = {
            "sensor": self.name,
            "voltage_V": round(voltage, 4),
            "current_A": round(current, 4),
            "power_W": round(power, 4),
            "timestamp": utc_now(),
        }
        return self._last

    def last_reading(self) -> dict:
        return self._last


class VirtualBH1750:
    """Ambient-light sensor simulation. Lux is NOT irradiance (W/m2)."""

    LUX_TO_IRRADIANCE_FACTOR = 0.0079  # UNCALIBRATED ASSUMPTION (notebook)

    SCENARIOS = {
        "bright_sun": (50000, 120000, "Direct sunlight"),
        "cloudy": (10000, 25000, "Overcast sky"),
        "indoor": (200, 500, "Indoor / shaded"),
        "dusk": (10, 100, "Dusk / dawn"),
        "night": (0.01, 1, "Night"),
    }

    def __init__(self, name="BH1750_sim", rng_seed=None):
        self.name = name
        self._rng = np.random.default_rng(rng_seed)

    def read_lux(self, scenario="bright_sun", noise_frac=0.02) -> dict:
        """Original notebook behaviour: random lux inside a named scenario band."""
        lo, hi, desc = self.SCENARIOS[scenario]
        base = self._rng.uniform(lo, hi)
        lux = max(0.0, base * (1 + self._rng.normal(0, noise_frac)))
        return {
            "sensor": self.name,
            "lux": round(float(lux), 2),
            "scenario": scenario,
            "description": desc,
            "irradiance_est_Wm2": round(float(lux) * self.LUX_TO_IRRADIANCE_FACTOR, 2),
            "irradiance_WARNING": "UNCALIBRATED - lux->W/m2 conversion not validated for this setup",
            "timestamp": utc_now(),
        }

    def read_target(self, target_lux: float, noise_frac: float = 0.01) -> dict:
        """Parametric variant used by the website: noisy reading around a requested lux level."""
        lux = max(0.0, target_lux * (1 + self._rng.normal(0, noise_frac)))
        return {"sensor": self.name, "lux": round(float(lux), 2), "timestamp": utc_now()}
