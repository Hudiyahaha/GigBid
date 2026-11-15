# One image for every Python service (api, worker, MCP servers, gigsim); the command differs per service.
# Stage 1: build the React app (served by the API).
FROM node:22-slim AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web ./
RUN npx vite build

# Stage 2: Python runtime (CPU-only torch).
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 UV_TORCH_BACKEND=cpu TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS=4 \
    HF_HOME=/models GIGBID_LOCAL_SQLITE=0
WORKDIR /app
RUN pip install uv==0.9.5
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
ENV PATH="/app/.venv/bin:$PATH"
# bake the open embedding + reranker models into the image (no download at runtime)
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('BAAI/bge-small-en-v1.5'); CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"
COPY . .
COPY --from=web /web/dist /app/apps/web/dist
RUN uv sync --frozen --no-dev
EXPOSE 8000
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
