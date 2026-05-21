FROM python:3.12-slim
WORKDIR /app
RUN pip install fastapi uvicorn mysql-connector-python highspy pulp
COPY server.py .
CMD ["python", "server.py"]
