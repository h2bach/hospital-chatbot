FROM golang:1.25.6-alpine

COPY go.mod go.sum .
RUN go mod download

COPY . .
RUN go build -v -o /usr/bin/agent-app ./cmd/server/main.go

ENV AGENT_STATIC_DIR=/usr/src/app/static

CMD ["sh", "-c", "agent-app -p $PORT"]
