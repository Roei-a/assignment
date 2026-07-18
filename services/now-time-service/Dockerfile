FROM python:3.12-slim

WORKDIR /srv/now-time-service

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY config ./config

RUN useradd --create-home appuser
USER appuser

# Uses the single config/config.yaml by default; override with CONFIG_PATH.
# EPOCH_SERVICE_URL (set in docker-compose.yml) points at the sibling service.
EXPOSE 8081

CMD ["python", "-m", "app.main"]
