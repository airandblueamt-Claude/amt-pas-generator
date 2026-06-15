# AMT PAS Generator — container for free deployment (e.g. Hugging Face Spaces, Docker SDK)
# Includes LibreOffice so tables/Arabic render pixel-faithfully (not the reportlab fallback).
FROM python:3.11-slim

# LibreOffice (calc+writer) for high-fidelity Excel/Word rendering, plus fonts.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-calc libreoffice-writer \
        fonts-noto fonts-noto-cjk git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Fetch the compiler engine (read-only dependency).
ARG PAS_COMPILER_REPO=https://github.com/airandblueamt-Claude/amt-pas-compiler.git
RUN git clone --depth 1 "$PAS_COMPILER_REPO" /app/compiler

COPY app.py .
COPY static ./static

# Hugging Face Spaces routes to port 7860; locally any port works.
ENV PORT=7860 PAS_SESSIONS_DIR=/tmp/pas-sessions
EXPOSE 7860
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT}"]
