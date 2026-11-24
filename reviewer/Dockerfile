FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY watch ./watch

RUN useradd --system --uid 10001 --home-dir /data reviewer \
    && mkdir -p /data && chown reviewer /data
USER reviewer

CMD ["python", "-m", "watch.main"]
