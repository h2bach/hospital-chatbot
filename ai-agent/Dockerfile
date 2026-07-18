FROM golang:1.25.6-alpine

WORKDIR /app
COPY go.mod go.sum .
RUN --mount=type=cache,target=/go/pkg/mod go mod download

COPY . .
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    go test ./... && \
    go build -v -o /usr/bin/agent-app ./cmd/server/main.go

ENV AGENT_STATIC_DIR=/app/static

CMD ["sh", "-c", "agent-app -p $PORT"]
