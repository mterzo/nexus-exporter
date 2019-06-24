FROM python:3.7-alpine

COPY requirements.txt /requirements.txt
RUN pip install -r requirements.txt

EXPOSE 9184
COPY nexus_exporter.py /nexus_exporter.py

ENTRYPOINT ["/nexus_exporter.py"]
