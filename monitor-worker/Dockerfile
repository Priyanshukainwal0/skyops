FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

# Use local wheels if available (local dev), otherwise pull from PyPI (CI)
COPY wheels/ ./wheels/
RUN if [ -d "./wheels" ] && [ "$(ls -A ./wheels)" ]; then \
      pip install --no-cache-dir --no-index --find-links=./wheels -r requirements.txt; \
    else \
      pip install --no-cache-dir -r requirements.txt; \
    fi

COPY worker.py .

RUN useradd -r -u 1001 appuser && chown -R appuser /app
USER appuser

CMD ["python", "worker.py"]
