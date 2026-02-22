FROM python:3.11-slim

WORKDIR /app

COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/kluspilot ./kluspilot
COPY app/tenants ./tenants

CMD ["uvicorn", "kluspilot.main:app", "--host", "0.0.0.0", "--port", "8000"]