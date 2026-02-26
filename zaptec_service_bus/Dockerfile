ARG BUILD_FROM
FROM $BUILD_FROM

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

COPY zaptec_charge_monitor.py /app/zaptec_charge_monitor.py
COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
