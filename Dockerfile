# --- stage 1: build the React / three.js frontend ---
FROM node:20-slim AS web
WORKDIR /web
COPY solar_monitor/frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY solar_monitor/frontend/ ./
RUN npm run build

# --- stage 2: Python backend serving the API, WebSocket and the built frontend ---
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 PORT=10000 MQTT_ENABLED=0
WORKDIR /app/solar_monitor
COPY solar_monitor/requirements-prod.txt ./
RUN pip install --no-cache-dir -r requirements-prod.txt
COPY solar_monitor/run.py ./
COPY solar_monitor/backend ./backend
COPY --from=web /web/dist ./frontend/dist
EXPOSE 10000
CMD ["python", "run.py"]
