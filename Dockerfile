FROM python:3.12-slim-bookworm@sha256:44cf1793efa7c7a476bb0f2cff81443f4a072c90c1cb127e2924933daa3e8c64
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY outpatient ./outpatient
USER 10001:10001
EXPOSE 8080
CMD ["sh", "-ec", "python -m outpatient --work-dir /tmp/outpatient fixtures && python -m outpatient --work-dir /tmp/outpatient ingest && exec python -m outpatient --work-dir /tmp/outpatient serve --host 0.0.0.0"]
