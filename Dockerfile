FROM golang:1.21-alpine AS builder

WORKDIR /app

# 安装依赖
RUN apk add --no-cache git docker-cli

# 复制源码
COPY . .

# 下载依赖
RUN go mod download

# 构建
RUN CGO_ENABLED=0 GOOS=linux go build -o /app/server ./cmd/server

# 运行镜像
FROM alpine:3.19

WORKDIR /app

# 安装运行时依赖
RUN apk add --no-cache ca-certificates curl

# 复制构建产物
COPY --from=builder /app/server /app/server
COPY configs/config.yaml /app/config.yaml
COPY configs/.env.example /app/.env.example

# 创建非 root 用户
RUN adduser -D -u 1000 appuser
USER appuser

# 暴露端口
EXPOSE 8080

# 启动
CMD ["/app/server"]
