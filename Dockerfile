FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# Install dependencies before copying code so source edits reuse this layer.
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

# Copy only runtime code and migrations; never bake .env into the image.
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

USER app
EXPOSE 8000

# One application process: the usage counter and cache are process-local.
# Stop startup if migrations fail; exec forwards shutdown signals to Uvicorn.
CMD ["sh", "-c", "python -m alembic upgrade head && exec python -m uvicorn email_assistant.basic.main:app --host 0.0.0.0 --port 8000 --workers 1"]
