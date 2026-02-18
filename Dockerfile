FROM python:3.12-slim

LABEL maintainer="SalmAlm"
LABEL description="SalmAlm — Personal AI Gateway"

WORKDIR /app

RUN pip install --no-cache-dir salmalm cryptography

RUN mkdir -p memory workspace uploads plugins

EXPOSE 18800 18801

ENV SALMALM_PORT=18800
ENV PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:18800/api/health')" || exit 1

ENTRYPOINT ["python3", "-m", "salmalm"]
