FROM python:3.12-slim AS builder

RUN pip install --no-cache-dir uv

WORKDIR /code

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project --no-dev

FROM python:3.12-slim

RUN useradd --uid 1000 --create-home appuser

WORKDIR /code

COPY --from=builder /code/.venv /code/.venv
COPY app/ app/

ENV PATH="/code/.venv/bin:$PATH" \
    PYTHONPATH=/code

USER appuser

EXPOSE 8010

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
