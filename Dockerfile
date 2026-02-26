FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY zaptec_charge_monitor.py /app/zaptec_charge_monitor.py

CMD ["python", "/app/zaptec_charge_monitor.py"]
