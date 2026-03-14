FROM node:18-alpine AS builder

WORKDIR /app

# Fix ajv peer dependency conflict with react-scripts 5 on Node 18
COPY package.json .
RUN npm install --legacy-peer-deps && \
    npm install ajv@^8.0.0 --legacy-peer-deps

COPY . .

# Set env to skip preflight checks that block the build
ENV CI=false
ENV SKIP_PREFLIGHT_CHECK=true
ENV NODE_OPTIONS=--openssl-legacy-provider

RUN npm run build

FROM nginx:alpine

COPY --from=builder /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
