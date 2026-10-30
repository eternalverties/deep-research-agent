FROM node:22-slim AS frontend

WORKDIR /frontend

# 国内构建可传 --build-arg NPM_REGISTRY=https://registry.npmmirror.com
ARG NPM_REGISTRY=https://registry.npmjs.org

COPY frontend/package*.json ./
RUN npm ci --registry="$NPM_REGISTRY"
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 国内构建可传 --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_INDEX_URL=https://pypi.org/simple

COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir --index-url "$PIP_INDEX_URL" .

COPY --from=frontend /frontend/dist ./frontend/dist

EXPOSE 8000

CMD ["uvicorn", "research_agent.api:api", "--host", "0.0.0.0", "--port", "8000"]
