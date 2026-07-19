FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi uvicorn[standard] streamlit \
    langgraph langchain langchain-community \
    pandas plotly openpyxl dashscope \
    pydantic-settings python-multipart pyyaml

COPY . .

RUN mkdir -p logs uploads

EXPOSE 8000 8501
