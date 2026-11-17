FROM python:3.11.9-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PORT=7860
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
RUN useradd --create-home --uid 1000 user \
    && mkdir -p /app/backend/data /app/backend/cache \
    && chown -R user:user /app/backend
USER user
WORKDIR /app/backend

EXPOSE 7860
CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
