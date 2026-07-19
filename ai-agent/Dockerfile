FROM node:22-alpine AS web-builder
WORKDIR /build/web-interface
COPY web-interface/package.json web-interface/package-lock.json ./
RUN npm install --no-audit
COPY web-interface/ ./
# vite.config.ts: outDir: "../static" → outputs to /build/static
RUN npm run build

FROM golang:1.25.6-alpine
WORKDIR /app
COPY go.mod go.sum .
RUN go mod download
COPY . .
# Replace prebuilt static with freshly built assets
COPY --from=web-builder /build/static ./static
RUN go build -v -o /usr/bin/agent-app ./cmd/server/main.go

ENV AGENT_STATIC_DIR=/app/static
CMD ["sh", "-c", "agent-app -p $PORT"]
