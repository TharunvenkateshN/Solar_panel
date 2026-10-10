"""Start the simulation: python run.py  ->  http://localhost:8000"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

if __name__ == "__main__":
    import uvicorn

    # HOST defaults to localhost-only; deployments (Docker / Render) set HOST=0.0.0.0
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", 8000))
    print(f"Solar monitor simulation -> http://{'localhost' if host == '127.0.0.1' else host}:{port}")
    print("MQTT broker: %s:%s (falls back to local simulation mode if unreachable)"
          % (os.environ.get("MQTT_HOST", "127.0.0.1"), os.environ.get("MQTT_PORT", "1883")))
    uvicorn.run("app.main:app", host=host, port=port, log_level="info")
