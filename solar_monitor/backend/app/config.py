"""Runtime-configurable simulation parameters.

Every threshold here is PROVISIONAL (inherited from the notebook) or a SIMULATION
ASSUMPTION - none is experimentally validated. They can be edited live from the UI
(PUT /api/config) and are validated against RANGES.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields


@dataclass
class SimConfig:
    # --- Decision engine / digital twin (notebook defaults) -------------------
    soiling_dev_thresh_pct: float = 10.0   # % deviation that counts as degradation
    persist_cycles: int = 3                # consecutive cycles above threshold
    hotspot_abs_thresh_c: float = 65.0     # max pixel temperature threshold
    hotspot_delta_thresh_c: float = 15.0   # max - mean threshold
    hot_pixel_thresh: int = 2              # min hot pixels for the delta rule
    p_stc_w: float = 30.0                  # rated power at STC (example value)
    gamma: float = -0.004                  # temperature coefficient (/degC)
    g_stc: float = 1000.0
    t_stc: float = 25.0
    lux_to_irradiance: float = 0.0079      # W/m2 per lux - UNCALIBRATED

    # --- Post-action verification --------------------------------------------
    verification_dev_thresh_pct: float = 10.0  # post-action mean deviation must be below this
    verification_cycles: int = 2               # readings averaged after the action

    # --- Simulated actuators (assumptions, not measurements) ------------------
    actuator_simulator_enabled: bool = True    # disable if real hardware answers on solar/panel/feedback
    auto_execute: bool = True                  # decision engine commands are sent automatically
    command_timeout_s: float = 30.0            # no feedback within this -> command abandoned
    cleaning_effectiveness: float = 1.0        # fraction of soiling removed by one cleaning cycle
    cleaning_duration_s: float = 5.0
    tilt_target_angle_deg: float = 120.0       # assumed angle that clears the shadow
    tilt_step_deg: float = 5.0
    tilt_step_s: float = 0.3
    tilt_full_recovery_deg: float = 30.0       # tilt change giving full tilt_efficacy
    tilt_efficacy: float = 0.85                # max fraction of shading loss recovered by tilting (tilting the other way enlarges the shadow by the same factor)
    event_time_scale: float = 1.0              # speed of timed what-if events (weather etc.); tests use a small value

    # --- Simulation clock -----------------------------------------------------
    tick_interval_s: float = 1.5
    sim_minutes_per_tick: float = 1.0          # notebook assumes 1-minute sampling
    seed: int = 42

    # --- Virtual-panel model assumptions -------------------------------------
    baseline_loss: float = 0.02                # healthy panel delivers ~98% of the twin's expectation
    soiling_max_loss: float = 0.30             # power loss at soiling_level = 1
    shading_loss_per_fraction: float = 0.80    # power loss per unit shaded-area fraction
    soiling_temp_rise_c: float = 6.5           # trapped-heat rise at soiling_level = 1
    shade_cool_base_c: float = 4.0
    shade_cool_per_fraction_c: float = 6.0
    power_noise_frac: float = 0.008
    lux_noise_frac: float = 0.01
    thermal_noise_c: float = 0.7

    # --- Simulated classifier (stand-in for the trained model) ---------------
    classifier_cool_delta_c: float = 2.5
    classifier_cool_pixels_min: int = 4

    def to_dict(self) -> dict:
        return asdict(self)

    def update(self, changes: dict) -> list[str]:
        """Validate and apply changes atomically. Returns the keys that changed."""
        types = {f.name: type(getattr(self, f.name)) for f in fields(self)}
        staged = {}
        for key, raw in changes.items():
            if key not in types:
                raise ValueError(f"Unknown config key: {key}")
            t = types[key]
            try:
                value = bool(raw) if t is bool else t(raw)
            except (TypeError, ValueError):
                raise ValueError(f"{key}: cannot convert {raw!r} to {t.__name__}")
            if key in RANGES:
                lo, hi = RANGES[key]
                if not (lo <= value <= hi):
                    raise ValueError(f"{key}: {value} outside allowed range [{lo}, {hi}]")
            staged[key] = value
        changed = [k for k, v in staged.items() if getattr(self, k) != v]
        for k, v in staged.items():
            setattr(self, k, v)
        return changed


RANGES = {
    "soiling_dev_thresh_pct": (0.1, 100),
    "persist_cycles": (1, 20),
    "hotspot_abs_thresh_c": (30, 200),
    "hotspot_delta_thresh_c": (1, 100),
    "hot_pixel_thresh": (1, 64),
    "p_stc_w": (1, 1000),
    "gamma": (-0.01, 0.0),
    "lux_to_irradiance": (0.001, 0.05),
    "verification_dev_thresh_pct": (0.1, 100),
    "verification_cycles": (1, 20),
    "command_timeout_s": (1, 600),
    "cleaning_effectiveness": (0, 1),
    "cleaning_duration_s": (0, 60),
    "tilt_target_angle_deg": (0, 180),
    "tilt_step_deg": (1, 45),
    "tilt_step_s": (0, 5),
    "tilt_full_recovery_deg": (1, 90),
    "tilt_efficacy": (0, 1),
    "event_time_scale": (0.001, 10),
    "tick_interval_s": (0.2, 30),
    "sim_minutes_per_tick": (0.1, 60),
    "baseline_loss": (0, 0.5),
    "soiling_max_loss": (0, 0.9),
    "shading_loss_per_fraction": (0, 1.2),
    "classifier_cool_pixels_min": (1, 64),
}
