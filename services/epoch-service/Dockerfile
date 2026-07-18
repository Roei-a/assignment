FROM python:3.12-slim

WORKDIR /srv/epoch-service

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY config ./config

RUN useradd --create-home appuser
USER appuser

# Uses the single config/config.yaml by default; override with CONFIG_PATH.
EXPOSE 8080

CMD ["python", "-m", "app.main"]
