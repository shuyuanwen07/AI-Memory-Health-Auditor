FROM python:3.12-slim
WORKDIR /service
COPY mem0_target/requirements.lock.txt /service/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY reference_target /service/reference_target
COPY mem0_target /service/mem0_target
ENV MEM0_TELEMETRY=false MEM0_DIR=/data/mem0-sdk
CMD ["uvicorn", "mem0_target.service:app", "--host", "0.0.0.0", "--port", "8011"]
