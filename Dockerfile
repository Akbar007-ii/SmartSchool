FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Root эмес колдонуучу; media папкасы volume катары туташтырылат
RUN useradd --create-home app \
    && mkdir -p /app/media \
    && chown -R app:app /app
USER app

EXPOSE 8000

# Ар бир иштетүүдө алгач миграциялар колдонулат, андан кийин API көтөрүлөт
CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000 --workers ${WEB_WORKERS:-2} --proxy-headers --forwarded-allow-ips='*'"]
