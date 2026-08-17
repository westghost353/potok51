# Многостадийная сборка: колёса собираются отдельно, в рантайм-образ
# не попадают ни компиляторы, ни кеш сборки.
FROM python:3.11-slim AS builder

WORKDIR /build
COPY pyproject.toml ./
COPY potok51 ./potok51
COPY synth ./synth

RUN pip install --no-cache-dir --upgrade pip build \
 && pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POTOK51_DATA_DIR=/data

RUN useradd --create-home --uid 10001 potok
WORKDIR /app

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

RUN mkdir -p /data && chown -R potok:potok /data /app
USER potok

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status==200 else 1)"

CMD ["uvicorn", "potok51.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
