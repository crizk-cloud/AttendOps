# Development image: Vite dev server with /api proxied to the backend.
# A production build/serve setup is added in Phase 7 (deployment).
FROM node:22-slim
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
EXPOSE 5173
CMD ["npx", "vite", "--host", "0.0.0.0", "--port", "5173"]
