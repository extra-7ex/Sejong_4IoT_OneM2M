FROM golang:1.23-bookworm AS build
WORKDIR /src
COPY . .
WORKDIR /src/go-apps/meep-app-enablement
RUN CGO_ENABLED=0 go build -o /out/meep-app-enablement .
FROM debian:bookworm-slim
COPY --from=build /out/meep-app-enablement /meep-app-enablement
EXPOSE 80
ENTRYPOINT ["/meep-app-enablement"]
