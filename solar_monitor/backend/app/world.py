"""The virtual panel ("world"): generates telemetry from physical parameters + actuator state.

Everything here is SIMULATION. The pipeline never sees these internals - only the telemetry
message (INA219 / BH1750 / AMG8833 readings and actuator state), exactly as it would over MQTT.

Model assumptions (all in SimConfig, none validated experimentally):
  P_actual = P_expected(G, T) * (1 - baseline) * (1 - soiling_loss) * (1 - shading_loss) * noise
  soiling_loss = soiling_max_loss * effective_soiling   (cleaning removes `cleaning_effectiveness`)
  shading_loss = shading_loss_per_fraction * effective_shading
  effective_shading = shading_fraction * (1 - tilt_efficacy * clamp((tilt - 90) / tilt_full_recovery_deg, -1, 1))
      i.e. tilting toward the sun side (angle > 90) shrinks the shadow, tilting away (angle < 90) enlarges it.
      ASSUMPTION - there is no sun-tracking / cosine model, so tilting changes power only through the shadow.
  Timed what-if events (rain, cloud, heat wave ...) add temporary irradiance / temperature modifiers.
"""
from __future__ import annotations

import math
from copy import copy

import numpy as np

from .config import SimConfig
from .core.digital_twin import pv_expected_power
from .core.sensors import VirtualBH1750, VirtualINA219
from .core.thermal import VirtualAMG8833
from .scenarios import SimParams

DEFAULT_TILT_DEG = 90.0
V_MPP_STC = 17.5  # nominal MPP voltage of the example 30 W panel (assumption)


class PanelWorld:
    def __init__(self, config: SimConfig, params: SimParams):
        self.config = config
        self.params = copy(params)
        self.reset(self.params)

    # -- state ---------------------------------------------------------------
    def reset(self, params: SimParams | None = None) -> None:
        if params is not None:
            self.params = copy(params)
        s = self.config.seed
        self.amg = VirtualAMG8833(rng_seed=s)
        self.bh = VirtualBH1750(rng_seed=s + 1)
        self.ina = VirtualINA219()
        self._rng = np.random.default_rng(s + 2)
        self.tilt_angle_deg = DEFAULT_TILT_DEG
        self.cleaned_fraction = 0.0
        self.cleaning_active = False
        self.tilt_active = False
        self.revision = 0  # bumped whenever an actuator completes (lets verification ignore stale readings)
        self.weather = {"rain": False, "cloud": False, "dust_storm": False, "heat_wave": False}
        self.irr_mods: dict[str, float] = {}    # event id -> irradiance multiplier
        self.temp_mods: dict[str, float] = {}   # event id -> temperature offset (degC)

    @property
    def irr_factor(self) -> float:
        f = 1.0
        for v in self.irr_mods.values():
            f *= v
        return f

    @property
    def temp_offset(self) -> float:
        return sum(self.temp_mods.values())

    def add_dust(self, delta: float) -> None:
        """Deposit dust on top of whatever is currently on the glass."""
        self.params.soiling_level = min(1.0, self.effective_soiling + delta)
        self.cleaned_fraction = 0.0

    @property
    def effective_soiling(self) -> float:
        return self.params.soiling_level * (1 - self.cleaned_fraction)

    @property
    def effective_shading(self) -> float:
        c = self.config
        offset = (self.tilt_angle_deg - DEFAULT_TILT_DEG) / c.tilt_full_recovery_deg
        recov = c.tilt_efficacy * max(-1.0, min(1.0, offset))
        return min(0.9, max(0.0, self.params.shading_fraction * (1 - recov)))

    # -- actuator effects (called by the actuator simulator) -------------------
    def apply_cleaning(self, effectiveness: float) -> None:
        self.cleaned_fraction = min(1.0, 1 - (1 - self.cleaned_fraction) * (1 - effectiveness))
        self.revision += 1

    def finish_tilt(self) -> None:
        self.revision += 1

    # -- parameter changes ------------------------------------------------------
    def set_params(self, changes: dict) -> None:
        old = copy(self.params)
        for k, v in changes.items():
            setattr(self.params, k, v)
        if self.params.soiling_level != old.soiling_level:
            self.cleaned_fraction = 0.0          # user re-dirtied the panel
        if self.params.shading_fraction != old.shading_fraction:
            self.tilt_angle_deg = DEFAULT_TILT_DEG  # new shadow: tilt back to default

    # -- telemetry ----------------------------------------------------------------
    def read(self) -> dict:
        c, p = self.config, self.params
        soil, shade = self.effective_soiling, self.effective_shading
        shade_px = int(round(shade * 64))
        cool = c.shade_cool_base_c + c.shade_cool_per_fraction_c * shade if shade_px > 0 else 0.0

        amg = self.amg.read_parametric(
            background_C=p.background_temp_C + self.temp_offset, noise_std=c.thermal_noise_c,
            soiling_rise_C=c.soiling_temp_rise_c * soil,
            shade_pixels=shade_px, shade_delta_C=cool,
            hotspot_peak_C=p.hotspot_peak_C if p.hotspot_enabled else None,
            hotspot_pixels=p.hotspot_pixels if p.hotspot_enabled else 0,
            hotspot_row=p.hotspot_row, hotspot_col=p.hotspot_col)
        grid = amg["grid"]
        t_panel = float(grid.mean())

        g = p.irradiance_Wm2 * self.irr_factor
        p_exp = pv_expected_power(g, t_panel, c)
        soil_loss = c.soiling_max_loss * soil
        shade_loss = min(0.95, c.shading_loss_per_fraction * shade)
        power = p_exp * (1 - c.baseline_loss) * (1 - soil_loss) * (1 - shade_loss) \
            * (1 + self._rng.normal(0, c.power_noise_frac))
        power = max(0.0, power)

        v_nom = V_MPP_STC * (1 - 0.0035 * (t_panel - 25.0))
        v = v_nom * (1 + 0.04 * math.log(max(g, 50.0) / 1000.0)) * (1 - 0.05 * soil_loss)
        v = min(max(v, 0.5), 29.0)
        i = min(power / v, 9.99)
        ina = self.ina.read(v, i)

        bh = self.bh.read_target(g / c.lux_to_irradiance, c.lux_noise_frac)
        return {
            "ina219": ina,
            "bh1750": bh,
            "amg8833": {"sensor": amg["sensor"], "grid": grid.tolist()},
            "actuators": {
                "tilt_angle_deg": self.tilt_angle_deg,
                "cleaning_active": self.cleaning_active,
                "tilt_active": self.tilt_active,
            },
            "world_revision": self.revision,
        }

    def truth(self) -> dict:
        """Ground truth for the UI's 'simulation internals' panel - NOT visible to the pipeline."""
        return {
            "params": self.params.to_dict(),
            "effective_soiling": round(self.effective_soiling, 4),
            "effective_shading": round(self.effective_shading, 4),
            "cleaned_fraction": round(self.cleaned_fraction, 4),
            "tilt_angle_deg": self.tilt_angle_deg,
            "weather": dict(self.weather),
            "irradiance_effective": round(self.params.irradiance_Wm2 * self.irr_factor, 1),
            "temp_offset": round(self.temp_offset, 1),
        }
