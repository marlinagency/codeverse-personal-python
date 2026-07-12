FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic

RUN pip install --no-cache-dir .

EXPOSE 8000

# A fresh Postgres volume has no tables. Apply every committed migration
# before accepting traffic, then replace the shell with the API process.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn codeverse_api.main:app --host 0.0.0.0 --port 8000"]
