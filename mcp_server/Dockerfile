FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY mcp_server /app/mcp_server

WORKDIR /app/mcp_server

EXPOSE 8000

CMD ["python", "sql_mcp_server.py"]