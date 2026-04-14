# Artha API — main gateway + agent registry
#
# Includes PDF-parsing system deps for the ingestion pipeline.
# Agent containers use their own leaner Dockerfiles.
#
# Build from repo root:
#   docker build -t artha-api .

FROM python:3.12-slim

# System deps for PDF parsing (camelot → ghostscript, pdfplumber → poppler)
RUN apt-get update && apt-get install -y --no-install-recommends \
        ghostscript \
        libgl1 \
        poppler-utils \
        tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps before copying source so the layer is cached
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e "."

# Copy full source
COPY . .

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Run migrations then start the server
CMD ["sh", "-c", "alembic upgrade head && uvicorn api.main:app --host 0.0.0.0 --port 8000"]
