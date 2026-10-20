# Build stage
FROM node:18-alpine as build-stage

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ .
RUN npm run generate

# Production stage
FROM nginx:alpine as production-stage

COPY --from=build-stage /app/frontend/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
