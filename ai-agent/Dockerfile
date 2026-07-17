FROM golang:1.25.6-alpine

WORKDIR /app
COPY go.mod go.sum .
RUN go mod download

COPY . .
RUN go build -v -o /usr/bin/agent-app ./cmd/server/main.go

ENV AGENT_STATIC_DIR=/app/static

CMD ["sh", "-c", "agent-app -p $PORT"]
