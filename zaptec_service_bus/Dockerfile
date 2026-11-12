FROM python:3.15.2-slim

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY zaptec_charge_monitor.py /app/zaptec_charge_monitor.py
COPY monta_charge_monitor.py /app/monta_charge_monitor.py
COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
