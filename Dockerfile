FROM python:3.12-slim

WORKDIR /app

RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends \
    curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data /app/logs && \
    chmod +x /app/*.sh 2>/dev/null || true

ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]
