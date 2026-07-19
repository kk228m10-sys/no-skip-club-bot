FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Almaty \
    DB_PATH=/app/data/no_skip.db

RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /app/data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Каталоги видео — в bundled_data/ (из Git). SQLite — только в /app/data (volume Bothost).
CMD ["python", "bot.py"]
