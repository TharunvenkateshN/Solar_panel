import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import SimConfig  # noqa: E402
from app.engine import SimulationEngine  # noqa: E402


def run(coro):
    return asyncio.run(coro)


FAST = dict(cleaning_duration_s=0.05, tilt_step_s=0.0, tilt_step_deg=15.0, verification_cycles=2)


async def make_engine(tmp_path, scenario="healthy", auto=True, classifier_pref=None, **cfg):
    """Engine with no background loop, empty models dir (-> simulated classifier) and fast actuators."""
    config = SimConfig()
    config.update({**FAST, "auto_execute": auto, **cfg})
    e = SimulationEngine(config=config, models_dir=tmp_path, classifier_pref=classifier_pref)
    e.bus.attach_loop(asyncio.get_running_loop())
    e.captured = []
    e.bus.tap(lambda topic, data, transport: e.captured.append((topic, data, transport)))
    e.select_scenario(scenario)  # performs tick 1
    await e.wait_idle()
    return e


async def ticks(e, n):
    for _ in range(n):
        e.tick()
        await e.wait_idle()


def messages(e, topic):
    return [d for t, d, _ in e.captured if t == topic]


@pytest.fixture
def models_dir(tmp_path):
    d = tmp_path / "models"
    d.mkdir()
    return d
