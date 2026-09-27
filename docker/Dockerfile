# syntax=docker/dockerfile:1.7

FROM python:3.11-slim AS production-deps

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv

RUN python -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip==26.2.1 setuptools==84.0.0 \
    && pip install -r /tmp/requirements.txt


FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONHASHSEED=random \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system botuser \
    && useradd --system --gid botuser --create-home --home-dir /home/botuser botuser

COPY --from=production-deps /opt/venv /opt/venv
WORKDIR /app


FROM runtime AS production

COPY --chown=botuser:botuser . /app
COPY docker/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN mkdir -p /app/data /app/logs \
    && sed -i 's/\r$//' /usr/local/bin/docker-entrypoint.sh \
    && chmod 755 /usr/local/bin/docker-entrypoint.sh \
    && chown botuser:botuser /app \
    && chown -R botuser:botuser /app/data /app/logs

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]


FROM production-deps AS development-deps

COPY requirements-dev.txt /tmp/requirements-dev.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r /tmp/requirements-dev.txt


FROM runtime AS development

COPY --from=development-deps /opt/venv /opt/venv
COPY --chown=botuser:botuser . /app
RUN mkdir -p /app/data /app/logs \
    && chown -R botuser:botuser /app

USER botuser
CMD ["python", "dev.py", "run"]
