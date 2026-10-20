# One image, three roles (chosen by the container command):
#   gateway       uvicorn app.main:app            (default)
#   usage-worker  python -m app.workers.usage_worker
#   alert-worker  python -m app.workers.alert_worker
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TIKTOKEN_CACHE_DIR=/app/.tiktoken

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the tokenizer into the image so pods never need to download it at runtime.
RUN python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"

COPY app ./app
COPY seed_data.py .

RUN useradd --create-home --uid 1000 acg && chown -R acg /app
USER acg

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
