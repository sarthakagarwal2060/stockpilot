FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
# pip is only needed at build time; removing it also removes the libraries it vendors
# (urllib3, msgpack, ...), which otherwise show up as CVEs in the Trivy scan.
RUN pip install -r requirements.txt \
    && pip uninstall -y pip \
    && useradd --create-home --uid 10001 appuser

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

USER 10001
EXPOSE 8000

# Apply migrations, then serve. Kubernetes probes hit /health and /ready.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
