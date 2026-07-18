FROM node:22-alpine AS build
WORKDIR /app
ARG VITE_CHATBOT_URL=""
ENV VITE_CHATBOT_URL=${VITE_CHATBOT_URL}
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=5s --timeout=3s --retries=10 CMD wget --spider -q http://127.0.0.1:8080/ || exit 1
