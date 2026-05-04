FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY langgraph_app/ langgraph_app/

EXPOSE 8501

CMD ["streamlit", "run", "langgraph_app/frontend.py", "--server.port=8501", "--server.address=0.0.0.0"]