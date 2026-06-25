# --- Build stage: compile the Vue/TS app to static assets ---
FROM node:22-slim AS build
WORKDIR /app

# Install deps from the lockfile first for layer caching.
COPY package.json package-lock.json ./
RUN npm ci

# Build the production bundle.
COPY . .
RUN npm run build

# --- Serve stage: static files behind nginx, /api proxied to the backend ---
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
