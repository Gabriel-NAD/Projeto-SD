FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY banco_postgres.py banco_redis.py broker.py ./

CMD ["python3", "broker.py"]
