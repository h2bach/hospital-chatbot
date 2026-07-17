FROM golang:1.25.6-alpine AS build

WORKDIR /src
COPY go.mod ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o /out/mock-info-service ./cmd

FROM alpine:3.22
WORKDIR /app
COPY --from=build /out/mock-info-service /usr/local/bin/mock-info-service
EXPOSE 8080
ENTRYPOINT ["mock-info-service"]
