FROM python:3.12.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=3600 \
    DEBIAN_FRONTEND=noninteractive \
    PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 300 --retries 15 -r requirements.txt

COPY . .

# Directorios persistentes
VOLUME ["/app/data", "/app/.cache", "/app/txt"]

EXPOSE 8000

CMD ["python", "app.py"]
