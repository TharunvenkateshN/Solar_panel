"""FastAPI app: REST controls + WebSocket stream + static frontend."""
from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .engine import SimulationEngine
from .mqtt_link import MqttLink

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def create_app(engine: SimulationEngine | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        eng = engine or SimulationEngine(mqtt=MqttLink())
        app.state.engine = eng
        await eng.start()
        try:
            yield
        finally:
            await eng.stop()

    app = FastAPI(title="Solar Panel Monitoring - Simulation", lifespan=lifespan)

    # Only needed when the frontend is hosted on another origin (e.g. Vercel). Comma-separated list, empty = off.
    origins = [o.strip().rstrip("/") for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])

    def eng() -> SimulationEngine:
        return app.state.engine

    def guard(fn, *a):
        try:
            return fn(*a)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    @app.get("/api/state")
    async def state():
        return eng().snapshot()

    @app.get("/api/health")
    async def health():
        e = eng()
        return {"ok": True, "classifier_mode": e.classifier_info["mode"], "mqtt": e.mqtt_status(), "tick": e.tick_no}

    @app.post("/api/scenario/{scenario_id}")
    async def scenario(scenario_id: str):
        guard(eng().select_scenario, scenario_id)
        return {"ok": True}

    @app.put("/api/params")
    async def params(changes: dict = Body(...)):
        guard(eng().update_params, changes)
        return {"ok": True, "params": eng().world.params.to_dict()}

    @app.put("/api/config")
    async def config(changes: dict = Body(...)):
        guard(eng().update_config, changes)
        return {"ok": True, "config": eng().config.to_dict()}

    @app.post("/api/sim/{op}")
    async def sim(op: str):
        e = eng()
        if op == "play":
            e.set_playing(True)
        elif op == "pause":
            e.set_playing(False)
        elif op == "step":
            e.step()
        elif op == "reset":
            e.reset()
        else:
            raise HTTPException(404, f"Unknown sim operation '{op}'")
        return {"ok": True, "sim": e.sim_state()}

    @app.post("/api/command/{action}")
    async def command(action: str):
        ok, info = eng().send_command(action.upper(), "operator", "Manual operator command")
        if not ok:
            raise HTTPException(409, info)
        return {"ok": True, "command_id": info}

    @app.post("/api/event/{event_id}")
    async def event(event_id: str, body: dict | None = Body(default=None)):
        try:
            msg = eng().run_event(event_id, (body or {}).get("params"))
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except RuntimeError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return {"ok": True, "message": msg}

    @app.post("/api/classifier/reload")
    async def reload_classifier():
        return eng().reload_classifier()

    @app.websocket("/ws")
    async def ws(socket: WebSocket):
        await socket.accept()
        e = eng()
        q = e.register_client()
        try:
            await socket.send_text(json.dumps(e.snapshot()))
            while True:
                msg = await q.get()
                await socket.send_text(json.dumps(msg))
        except (WebSocketDisconnect, asyncio.CancelledError, RuntimeError):
            pass
        finally:
            e.unregister_client(q)

    if FRONTEND_DIST.exists():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

        @app.get("/{path:path}")
        async def spa(path: str):
            f = FRONTEND_DIST / path
            if path and f.is_file() and FRONTEND_DIST in f.resolve().parents:
                return FileResponse(f)
            return FileResponse(FRONTEND_DIST / "index.html")
    else:
        @app.get("/")
        async def no_frontend():
            return {"message": "Frontend not built. Run setup.bat (or: cd frontend && npm install && npm run build)."}

    return app


app = create_app()
