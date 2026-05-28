FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY Procfile .

ENV PORT=8080

CMD gunicorn main:app --bind 0.0.0.0:${PORT} --workers 2 --timeout 120
