# Multi-stage build: compile Vite bundle, then serve from Caddy
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm ci

# Build the Vite bundle. Call vite directly (via the container's Node) instead
# of `npm run build` — package.json's build script hardcodes a macOS-only Node
# path (../.local-tools/...darwin-arm64) that doesn't exist in this Linux image.
COPY . .
RUN ./node_modules/.bin/vite build

# Serve from a minimal static server (nginx-alpine is ~9MB; caddy will proxy this)
FROM caddy:2-alpine

# Copy the built Vite dist/ folder to the webroot
COPY --from=builder /app/dist /var/www/html

# Static-file Caddy config (this container just serves the SPA bundle; the
# top-level `caddy` service handles TLS + routing — see Caddyfile.static)
COPY Caddyfile.static /etc/caddy/Caddyfile

EXPOSE 80
