# Image cho thiết bị edge (build được cho linux/arm64 và linux/amd64)
#   docker buildx build --platform linux/arm64 -t aistaff:latest .
#   docker run -d -p 8000:8000 -v $PWD/models:/app/models -v $PWD/data:/app/data \
#     -v $PWD/config:/app/config -e ADMIN_PIN=1234 aistaff:latest
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 OMP_NUM_THREADS=2
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 curl bzip2 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install ".[speech]"
COPY config ./config
COPY scripts ./scripts
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD curl -fs http://localhost:8000/healthz || exit 1
CMD ["aistaff", "--store", "config/stores/quan-ngon", "serve", "--host", "0.0.0.0", "--port", "8000"]
