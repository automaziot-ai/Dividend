FROM python:3.11-slim

WORKDIR /app

COPY ocr_tool/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ocr_tool/ ./ocr_tool/

ENV PORT=8080 \
    PYTHONUNBUFFERED=1

WORKDIR /app/ocr_tool

CMD gunicorn server:app --bind 0.0.0.0:${PORT} --workers 2 --timeout 180
