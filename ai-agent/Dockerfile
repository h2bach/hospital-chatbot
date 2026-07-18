FROM node:24-alpine AS web-build

WORKDIR /web
COPY web-interface/package.json web-interface/package-lock.json ./
RUN npm ci
COPY web-interface/ ./
RUN npm run build

FROM golang:1.25.6-alpine AS go-build

WORKDIR /app
COPY go.mod go.sum .
RUN go mod download

COPY . .
RUN go test ./... && go build -trimpath -ldflags="-s -w" -o /agent-app ./cmd/server/main.go

FROM alpine:3.23

RUN apk add --no-cache ca-certificates wget
WORKDIR /app
COPY --from=go-build /agent-app /usr/bin/agent-app
COPY --from=web-build /static /app/static

ENV AGENT_STATIC_DIR=/app/static

CMD ["sh", "-c", "agent-app -p $PORT"]
