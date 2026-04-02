# Phase 4: custom Python enrichment layer wrapping the OTEL collector.
# For local dev, docker-compose uses the official collector image directly
# with otel-config.yaml mounted. This Dockerfile is for the Phase 4 extension.
FROM python:3.11-slim

WORKDIR /app
COPY collector.py .

# Phase 4: add requirements.txt with opentelemetry-sdk when implementing
EXPOSE 4317 4318
CMD ["python", "collector.py"]
