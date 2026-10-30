FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 国内构建可传 --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_INDEX_URL=https://pypi.org/simple

COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir --index-url "$PIP_INDEX_URL" .

EXPOSE 8000

CMD ["uvicorn", "research_agent.api:api", "--host", "0.0.0.0", "--port", "8000"]
