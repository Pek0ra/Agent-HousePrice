# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system agent && useradd --system --gid agent agent

COPY pyproject.toml ./

RUN --mount=type=cache,target=/root/.cache/pip \
    mkdir -p app && touch app/__init__.py && \
    python -m pip install --upgrade pip && \
    python -m pip install .

COPY app ./app

RUN python -m pip install --no-deps .

USER agent

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
