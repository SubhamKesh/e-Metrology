# --- MaapSetu backend (FastAPI) ---
#
# Multi-stage build: install deps in a builder layer, copy only what's
# needed into a slim runtime image, and run as a non-root user.
FROM python:3.12-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.12-slim

# Non-root user — running the app as root inside the container is
# unnecessary risk if the container is ever compromised.
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

COPY --from=builder /root/.local /home/appuser/.local
COPY app/ ./app/

RUN chown -R appuser:appuser /app
USER appuser

ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

# Uses the app's own health endpoint — lets Docker/orchestrators (and a
# load balancer, per the checklist's "load distribution" section) detect
# an unhealthy container without a separate script.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health', timeout=3)" || exit 1

# --workers is a cheap first step towards Section 4's "run multiple
# instances" — actual horizontal scaling still needs multiple containers
# behind a load balancer, which is an infra decision made at deploy time,
# not something a Dockerfile can do alone.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
