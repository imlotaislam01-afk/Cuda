FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY brain/ brain/
COPY market/ market/
COPY config/ config/
COPY tests/ tests/

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir pytest && \
    pip install --no-cache-dir -e .

RUN mkdir -p /app/data /app/logs

ENV APEX_ENV=PAPER
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "brain.main", "--mode=paper"]
