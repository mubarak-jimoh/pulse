FROM python:3.13-slim

WORKDIR /app
COPY pyproject.toml ./
COPY pulse ./pulse
RUN pip install --no-cache-dir .

# Run as a non-root user and keep the database on a volume.
RUN useradd --create-home pulse && mkdir /data && chown pulse /data
USER pulse
VOLUME /data

ENV PULSE_CONFIG=/config/monitors.toml PULSE_DB=/data/pulse.db
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')"

CMD ["python", "-m", "pulse", "--config", "/config/monitors.toml", "--db", "/data/pulse.db", "serve", "--host", "0.0.0.0"]
