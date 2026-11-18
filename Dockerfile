FROM python:3.11-slim

# libgomp1 is required by LightGBM's native library. scikit-learn bundles its own
# OpenMP runtime, but LightGBM links the system libgomp.so.1, which the slim base
# image does not ship. Without it the API starts and /health passes, yet the first
# LightGBM training run fails with "libgomp.so.1: cannot open shared object file".
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10

# Override the package index on slow or restricted networks, e.g.:
#   docker compose build --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
# (docker-compose.yml wires this to the PIP_INDEX_URL variable in your .env.)
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL}

WORKDIR /srv/rsal

# Install the fully pinned runtime set for reproducible builds. The BuildKit cache
# mount keeps downloaded wheels across builds, so a retry does not re-download the
# large numeric wheels (numpy/scipy/scikit-learn/rasterio) on a slow link.
COPY requirements.lock.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.lock.txt

COPY app ./app

RUN useradd --create-home rsal && mkdir -p /data && chown -R rsal:rsal /data /srv/rsal
USER rsal

ENV STORAGE_DIR=/data/storage
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
