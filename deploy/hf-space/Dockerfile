# Hugging Face Space (Docker SDK, free CPU: 2 vCPU / 16 GB RAM). Upload this file + README.md to the Space.
# It builds the public GitHub repo; to update the Space after new commits: Space -> Settings -> Factory rebuild.
FROM node:22-slim AS src
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
ARG REPO=https://github.com/Hudiyahaha/GigBid.git
RUN git clone --depth 1 "$REPO" /src
WORKDIR /src/apps/web
RUN npm ci --no-audit --no-fund && npx vite build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS=2 HF_HOME=/models \
    HOST=0.0.0.0 PORT=7860 GIGBID_LOCAL_SQLITE=1 GIGBID_DEV=1 HF_HUB_OFFLINE=0 GIGSIM_POLICY_VERSION=2 \
    REVIEWER_PERSONA=ai_ml
RUN pip install uv==0.13.8 && useradd -m -u 1000 user
WORKDIR /app
COPY --from=src /src/pyproject.toml /src/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
ENV PATH="/app/.venv/bin:$PATH"
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('BAAI/bge-small-en-v1.5'); CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"
COPY --from=src /src /app
RUN uv sync --frozen --no-dev && mkdir -p /app/data/processed && chown -R user:user /app /models
ENV HF_HUB_OFFLINE=1
USER user
EXPOSE 7860
CMD ["python", "-m", "scripts.dev_stack"]
