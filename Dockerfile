# syntax=docker/dockerfile:1
#
# TR-0 Docker packaging (NFR-7). Multi-stage: uv resolves/installs dependencies and
# the project itself into a venv in the builder stage; the runtime stage copies only
# that venv + src/, so build tooling (uv, compilers) never reaches the final image.
#
# Secrets, .env and the state directory are intentionally NEVER copied in here (see
# .dockerignore) — they are mounted at runtime, per the TR-0 Design Decision.

FROM python:3.12-slim AS builder

RUN pip install --no-cache-dir uv==0.10.6

WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Dependencies first, in their own layer, so editing src/ doesn't bust this cache.
COPY pyproject.toml uv.lock README.md .python-version ./
RUN uv sync --frozen --no-install-project --no-dev

# Now install the project itself.
COPY src/ ./src/
RUN uv sync --frozen --no-dev


FROM python:3.12-slim AS runtime

RUN useradd --create-home --uid 1000 --user-group expenses

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY --from=builder /app/src /app/src

# Pre-create the state mount point with the right ownership: when a *named* volume
# is first attached here, Docker seeds it from this directory (including
# permissions), so a fresh volume is writable by the non-root user below without
# extra setup. A bind-mounted host directory still needs to be writable by uid 1000.
RUN mkdir -p /app/state && chown expenses:expenses /app/state
VOLUME ["/app/state"]

USER expenses

EXPOSE 8000

# Runs inside the container's own network namespace, so this works against the
# default loopback bind (EXPENSES_SERVER_HOST=127.0.0.1) without publishing the port.
# Plain urllib keeps the image free of curl/wget.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('EXPENSES_SERVER_PORT', '8000') + '/health', timeout=3)"]

CMD ["expenses-serve"]
