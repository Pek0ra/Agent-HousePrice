# syntax=docker/dockerfile:1.7
FROM node:22-alpine AS build
WORKDIR /workspace
COPY package*.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /workspace/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=10s --timeout=3s --retries=6 --start-period=10s \
  CMD wget -q -O - http://127.0.0.1/health || exit 1
