# Build the Vite frontend and serve it with nginx, which also reverse-proxies
# the API so the browser talks to ONE origin (no CORS, cookies just work).
# Build context is the REPO ROOT (see docker-compose.yml) so this file can
# copy both frontend/ sources and the nginx config next to it.
FROM node:22-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci || npm install
COPY frontend/ .
# Empty base URL -> the app calls relative paths (/themes, /auth, ...) which
# nginx proxies to the backend container.
ENV VITE_API_BASE_URL=""
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY docker/frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
