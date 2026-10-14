# ---- Stage 1: build the static bundle with Node ----
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# ---- Stage 2: serve it with an unprivileged Nginx (runs as uid 101, port 8080) ----
FROM nginxinc/nginx-unprivileged:1.31-alpine
# Pull in OS security fixes released after the base image was built (keeps the Trivy gate green).
USER root
RUN apk upgrade --no-cache
ENV BACKEND_URL=http://backend:8000
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
USER 101
EXPOSE 8080
