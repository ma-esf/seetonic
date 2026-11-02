FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /bin/uv

WORKDIR /srv
# Dependencies first, so a change to app/ or static/ reuses this layer.
# --no-install-project: app/ runs from the source tree, because app/main.py finds static/ beside it.
# --compile-bytecode: compile the dependencies at build time, not on every cold start.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --compile-bytecode
COPY app ./app
COPY static ./static

ENV PATH="/srv/.venv/bin:$PATH" PORT=8080
# Cloud Run sets PORT. exec makes uvicorn process 1, so it gets the stop signal.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
