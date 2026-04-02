FROM python:3.11-slim

WORKDIR /app

# Phase 4: add requirements.txt with opentelemetry-sdk, azure-servicebus
COPY collector.py .

EXPOSE 8001
CMD ["python", "collector.py"]
