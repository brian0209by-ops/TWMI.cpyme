FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --system --create-home app
COPY backend/ backend/
COPY database/ database/
USER app
CMD ["sh", "-c", "python -m backend.cli migrate && exec uvicorn backend.main:app --host 0.0.0.0 --port 8000"]
