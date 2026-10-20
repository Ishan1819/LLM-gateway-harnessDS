# Build the React dashboard, then serve it with nginx. nginx also reverse-
# proxies /api and /v1 to the gateway Service, so the browser talks to a
# single origin and the API base URL is empty (same origin).
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci || npm install
COPY . .
RUN printf 'VITE_API_BASE_URL=\n' > .env.production.local && npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
