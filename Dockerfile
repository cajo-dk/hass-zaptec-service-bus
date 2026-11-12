FROM python:3.15.2-slim

WORKDIR /app

LABEL org.opencontainers.image.title="Zaptec Service Bus Monitor" \
      org.opencontainers.image.description="Bridge Zaptec Azure Service Bus telemetry to MQTT" \
      org.opencontainers.image.source="https://github.com/cajo-dk/hass-zaptec-service-bus"

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY zaptec_charge_monitor.py /app/zaptec_charge_monitor.py
COPY monta_charge_monitor.py /app/monta_charge_monitor.py

RUN useradd --system --uid 10001 --create-home zaptec
USER zaptec

ENV HEARTBEAT_FILE=/tmp/zaptec-service-bus-heartbeat \
    CONFIG_FILE=/config/config.env \
    MQTT_DISCOVERY_ENABLED=false \
    PYTHONUNBUFFERED=1

VOLUME ["/config"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import os,time; p=os.environ['HEARTBEAT_FILE']; age=max(120,int(os.getenv('AZURE_SERVICE_BUS_MAX_WAIT_TIME','5'))+60); raise SystemExit(0 if os.path.exists(p) and time.time()-os.path.getmtime(p) < age else 1)"]

CMD ["python", "/app/zaptec_charge_monitor.py"]
