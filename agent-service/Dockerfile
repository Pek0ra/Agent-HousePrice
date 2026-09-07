# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

ARG PIP_INDEX_URL=https://pypi.org/simple

WORKDIR /app

RUN groupadd --system agent && useradd --system --gid agent agent

COPY pyproject.toml ./

RUN --mount=type=cache,target=/root/.cache/pip \
    mkdir -p app && touch app/__init__.py && \
    python -m pip install --index-url "$PIP_INDEX_URL" --upgrade pip && \
    python -m pip install --index-url "$PIP_INDEX_URL" .

COPY app ./app

RUN python -m pip install --no-deps . && \
    mkdir -p /data/checkpoints && chown -R agent:agent /data

USER agent

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
