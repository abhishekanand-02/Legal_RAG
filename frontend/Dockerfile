FROM node:22-alpine AS build

WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

# Skip docker-entrypoint noise; run nginx with minimal error logging.
ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off; error_log /dev/null crit;"]
