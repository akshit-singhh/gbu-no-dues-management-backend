# ------------------------------------------------------------
# Base image
# ------------------------------------------------------------
FROM python:3.11-slim-bookworm

# ------------------------------------------------------------
# Environment variables
# ------------------------------------------------------------
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=production \
    PORT=8000

# ------------------------------------------------------------
# Set working directory
# ------------------------------------------------------------
WORKDIR /app

# ------------------------------------------------------------
# System dependencies (UPDATED FOR WEASYPRINT)
# ------------------------------------------------------------
# These are strictly required for WeasyPrint to work on Linux.
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    libpq-dev \
    python3-dev \
    python3-pip \
    python3-setuptools \
    python3-wheel \
    python3-cffi \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------
# Upgrade pip
# ------------------------------------------------------------
RUN pip install --upgrade pip

# ------------------------------------------------------------
# Install Python dependencies
# ------------------------------------------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ------------------------------------------------------------
# Create non-root user
# ------------------------------------------------------------
RUN useradd -m fastapiuser

# ------------------------------------------------------------
# Setup Directories & Permissions
# ------------------------------------------------------------
# Create temp folder for PDFs and assign ownership
RUN mkdir -p /app/static/certificates && \
    mkdir -p /app/temp_pdf && \
    chown -R fastapiuser:fastapiuser /app

# ------------------------------------------------------------
# Copy project files
# ------------------------------------------------------------
COPY --chown=fastapiuser:fastapiuser . .

# ------------------------------------------------------------
# Switch to non-root user
# ------------------------------------------------------------
USER fastapiuser

# ------------------------------------------------------------
# Expose port
# ------------------------------------------------------------
EXPOSE 8000

# ------------------------------------------------------------
# Start Command
# ------------------------------------------------------------
# Using JSON format for better signal handling (SIGTERM)
CMD [
    "gunicorn",
    "app.main:app",
    "--workers", "1",
    "--worker-class", "uvicorn.workers.UvicornWorker",
    "--bind", "0.0.0.0:8000",
    "--timeout", "120",
    "--forwarded-allow-ips=*",
    "--access-logfile", "-",
    "--error-logfile", "-"
]