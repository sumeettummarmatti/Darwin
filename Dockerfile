# SETU — single container: API + kernel + built console + SQLite. Synthetic data only.
FROM node:22-alpine AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY core core
COPY mocks mocks
COPY tools tools
COPY bench bench
RUN pip install --no-cache-dir -e .
COPY . .
COPY --from=web /web/dist apps/web/dist
ENV SETU_VAR=/app/var
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "apps.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
