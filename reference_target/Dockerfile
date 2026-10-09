FROM python:3.12-slim
WORKDIR /service
RUN pip install --no-cache-dir fastapi==0.115.6 uvicorn==0.34.0 pydantic==2.10.3 httpx==0.28.1
COPY service.py .
CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8010"]
