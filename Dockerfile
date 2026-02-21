# ============================================================
# SalmAlm — Personal AI Gateway
# Multi-stage Docker build
# ============================================================

# --- Stage 1: Builder ---
FROM python:3.12-slim AS builder

WORKDIR /build

COPY pyproject.toml README.md LICENSE ./
COPY salmalm/ ./salmalm/

RUN pip install --no-cache-dir --prefix=/install . && \
    pip install --no-cache-dir --prefix=/install cryptography

# --- Stage 2: Runtime ---
FROM python:3.12-slim AS runtime

LABEL maintainer="SalmAlm <dolsoe@salmalm.dev>"
LABEL description="SalmAlm — Personal AI Gateway"

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd -r salmalm && useradd -r -g salmalm -m salmalm

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy source (for any runtime assets like static/, templates/)
COPY salmalm/ ./salmalm/

# Create data directories
RUN mkdir -p memory workspace uploads plugins data && \
    chown -R salmalm:salmalm /app

USER salmalm

EXPOSE 18800 18801

ENV SALMALM_PORT=18800 \
    SALMALM_BIND=0.0.0.0 \
    PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:18800/api/health || exit 1

CMD ["python", "-m", "salmalm"]
