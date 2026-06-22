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

COPY app/ ./app/

RUN useradd -r -u 1001 appuser && chown -R appuser /app && \
    mkdir -p /data && chown appuser /data
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
