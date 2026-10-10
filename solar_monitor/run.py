"""Start the simulation: python run.py  ->  http://localhost:8000"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    print(f"Solar monitor simulation -> http://localhost:{port}")
    print("MQTT broker: %s:%s (falls back to local simulation mode if unreachable)"
          % (os.environ.get("MQTT_HOST", "127.0.0.1"), os.environ.get("MQTT_PORT", "1883")))
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, log_level="info")
