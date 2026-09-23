FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LAYOUT_FILE=/data/palace.yaml \
    PORT=8080

WORKDIR /app
COPY pyproject.toml README.md ./
COPY palace ./palace
RUN pip install . \
    && useradd --system --uid 1000 --home-dir /data palace \
    && mkdir -p /data && chown palace /data

USER palace
VOLUME ["/data"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8080\")}/api/state', timeout=4)"

CMD ["palace"]
