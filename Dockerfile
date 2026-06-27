# Use a slim Python base image
FROM python:3.12-slim

# Prevent Python from writing .pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Cloud Run injects PORT; default to 8080 for local runs
ENV PORT=8080

WORKDIR /app

# Install dependencies first to leverage Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run as a non-root user for better security
RUN useradd -m appuser
USER appuser

# Use gunicorn as the production WSGI server.
# Shell form so $PORT is expanded at runtime.
CMD exec gunicorn --bind :$PORT --workers 2 --threads 4 --timeout 0 app:app