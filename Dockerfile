FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY pyproject.toml README.md requirements.txt ./
COPY src ./src
COPY config ./config
COPY demo/adequate_supply_summary.csv ./demo/adequate_supply_summary.csv
RUN mkdir -p /app/data/processed
RUN python -m pip install --no-cache-dir ".[phase2,geo]"

EXPOSE 8000
CMD ["uvicorn", "resq.api:app", "--host", "0.0.0.0", "--port", "8000"]
