FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY backend/ ./backend/
RUN pip install --no-cache-dir -e .
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

ENV DATABASE_PATH=/app/data/kairo.db
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
