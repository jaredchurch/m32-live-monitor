FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace

COPY pyproject.toml requirements.txt ./
COPY m32_monitor ./m32_monitor
RUN python -m pip install --no-cache-dir -e ".[dev]"

COPY . .

EXPOSE 8000
EXPOSE 10024/udp

CMD ["uvicorn", "m32_monitor.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
