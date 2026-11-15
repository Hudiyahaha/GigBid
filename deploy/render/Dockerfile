# Lean image for Render's FREE plan (512 MB RAM): same open models (bge-small, ms-marco-MiniLM) on ONNX Runtime via
# fastembed, torch never installed. GigSim + API + web app in one process (scripts/dev_stack.py).
FROM node:22-slim AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web ./
RUN npx vite build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS=1 \
    EMBED_BACKEND=fastembed FASTEMBED_CACHE_PATH=/models/fastembed HOST=0.0.0.0 GIGBID_LOCAL_SQLITE=1 \
    MALLOC_ARENA_MAX=2
WORKDIR /app
RUN pip install uv==0.13.8
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project \
    --no-install-package torch --no-install-package sentence-transformers --no-install-package transformers
ENV PATH="/app/.venv/bin:$PATH"
RUN python -c "from fastembed import TextEmbedding; from fastembed.rerank.cross_encoder import TextCrossEncoder; \
TextEmbedding('BAAI/bge-small-en-v1.5'); TextCrossEncoder('Xenova/ms-marco-MiniLM-L-6-v2')"
COPY . .
COPY --from=web /web/dist /app/apps/web/dist
RUN uv sync --frozen --no-dev \
    --no-install-package torch --no-install-package sentence-transformers --no-install-package transformers
ENV HF_HUB_OFFLINE=1
CMD ["python", "-m", "scripts.dev_stack"]
