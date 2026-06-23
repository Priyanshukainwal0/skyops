FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY worker.py .

RUN useradd -r -u 1001 appuser && chown -R appuser /app
USER appuser

CMD ["python", "worker.py"]
