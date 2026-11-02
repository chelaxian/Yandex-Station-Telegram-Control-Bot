FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml requirements.lock.txt ./
COPY src ./src
RUN python -m pip install --no-cache-dir . -c requirements.lock.txt && useradd --uid 10001 --create-home stationbot
USER 10001:10001
ENTRYPOINT ["python", "-m", "stationbot", "--config", "/config/config.toml", "run"]
