FROM node:22-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# Same-origin API: nginx below proxies /api to the backend and injects the API key.
RUN npm run build

FROM nginxinc/nginx-unprivileged:alpine
ENV PORT=8080 \
    BACKEND_URL=http://backend:8000 \
    API_KEY=
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://127.0.0.1:${PORT}/ >/dev/null || exit 1
