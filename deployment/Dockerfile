# Application image. Python 3.12 is used because every planned dependency
# (including PyTorch, torchvision and OpenCV in later stages) ships wheels
# for it. Build context is the repo root (see deployment/docker-compose.yml).

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/ai_engine:/app

WORKDIR /app

# Tesseract OCR (Apache-2.0) for reading drawing PDFs and images (Stage 4), English data only.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first, so code changes do not reinstall them. pip itself is upgraded first: the pip in the base
# image had published advisories (pip-audit, Stage 8).
COPY requirements.txt .
RUN pip install --upgrade "pip>=26.3" && pip install -r requirements.txt

COPY ai_engine ./ai_engine
COPY backend ./backend
COPY frontend ./frontend
# The answer-key schema is shared with the extracted values; the parts catalogue and the
# estimate rules are read at start-up. The only project data in the image is the four files of
# the sample enquiry ("Try the sample enquiry"), from the committed showcase.
COPY data_generator ./data_generator
COPY data/catalogue ./data/catalogue
COPY data/projects/showcase ./data/projects/showcase
COPY config ./config

# Run as an unprivileged user. Uploaded originals live in /app/storage (a volume).
RUN useradd --create-home --uid 10001 app     && mkdir -p /app/storage && chown app:app /app/storage
ENV STORAGE_DIR=/app/storage
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"

# Apply migrations, then serve with a single worker to keep memory low.
CMD ["sh", "-c", "alembic -c backend/alembic.ini upgrade head && exec uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 1"]
