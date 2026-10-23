# Pterodactyl-friendly Python 3.12 yolk image
FROM ghcr.io/parkervcp/yolks:python_3.12

# Install psycopg2 build dependencies (libpq-dev needed for psycopg2-binary)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency files first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create a non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port (set via docker-compose or command line)
EXPOSE 5001

# Healthcheck for the app
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5001/people')" || exit 1

CMD ["python", "app.py"]