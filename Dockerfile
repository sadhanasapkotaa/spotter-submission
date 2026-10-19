# syntax=docker/dockerfile:1.7
#
# One Dockerfile, two runnable targets:
#   local      -> dev dependencies, hot reload, source bind-mounted by compose
#   production -> slim, non-root, gunicorn. Used unchanged for dev, staging and prod
#                 (behaviour differs only through DJANGO_SETTINGS_MODULE + env vars).

ARG PYTHON_VERSION=3.12

# ---------------------------------------------------------------- builder base
FROM ghcr.io/astral-sh/uv:python${PYTHON_VERSION}-bookworm-slim AS builder-base
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0
WORKDIR /app

# ------------------------------------------------------- builder: prod deps only
FROM builder-base AS builder-prod
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev

# ------------------------------------------------------ builder: incl. dev group
FROM builder-base AS builder-dev
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked

# ------------------------------------------------------------- runtime base
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime-base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
# GeoDjango needs the GDAL / GEOS / PROJ shared libraries.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgdal32 libgeos-c1v5 libproj25 \
 && rm -rf /var/lib/apt/lists/*
RUN groupadd --system --gid 999 django \
 && useradd --system --gid 999 --uid 999 --create-home django
WORKDIR /app

# ------------------------------------------------------------------- local
FROM runtime-base AS local
COPY --from=builder-dev --chown=django:django /app/.venv /app/.venv
COPY --chown=django:django docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
COPY --chown=django:django . /app
USER django
ENV DJANGO_SETTINGS_MODULE=config.settings.local
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# -------------------------------------------------------------- production
FROM runtime-base AS production
COPY --from=builder-prod --chown=django:django /app/.venv /app/.venv
COPY --chown=django:django docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
COPY --chown=django:django . /app

# Collect static at build time. Dummy values only; real ones come from the runtime env.
RUN DJANGO_SETTINGS_MODULE=config.settings.prod \
    DJANGO_SECRET_KEY=build-only \
    DATABASE_URL=postgis://x:x@localhost:5432/x \
    python manage.py collectstatic --noinput

USER django
ENV DJANGO_SETTINGS_MODULE=config.settings.prod \
    WEB_CONCURRENCY=3
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health/', timeout=4).status == 200 else 1)"
ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--worker-tmp-dir", "/dev/shm", "--access-logfile", "-", "--error-logfile", "-"]
