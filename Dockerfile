FROM python:3.12-alpine

RUN apk add --no-cache git ca-certificates
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY collector.py .
ENTRYPOINT ["python", "/app/collector.py"]
