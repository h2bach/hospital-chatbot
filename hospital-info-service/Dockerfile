FROM golang:1.24-alpine AS build
WORKDIR /src
COPY go.mod ./
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o /out/hospital-info-service ./cmd

FROM alpine:3.21
RUN adduser -D -H app
COPY --from=build /out/hospital-info-service /usr/local/bin/hospital-info-service
USER app
ENTRYPOINT ["hospital-info-service"]
