# Key Service Generate Backend

生成系统 Go 后端，高吞吐入口。

## 环境要求

- Go 1.21+
- Kafka (默认: kafka:9092)

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| KAFKA_ADDR | kafka:9092 | Kafka 地址 |
| KAFKA_TOPIC | key_generate_log | Kafka Topic |
| SERVER_PORT | 8081 | 服务端口 |
| JAVA_BACKEND_BASE | http://localhost:9081 | Java 后端基础地址，`Register` 接口会转发到该服务 |
| INTERNAL_TOKEN | kms-generate-internal-secret-2026 | Java 后端调用 Go 接口时使用的内部鉴权 token |

## 快速启动

```bash
# 进入目录
cd kms-generate/go-backend

# 下载依赖
go mod tidy

# 启动服务
go run cmd/main.go
```

## 接口列表

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /generate/request/Register | 用户注册，转发到 Java 后端 |
| POST | /generate/request/ENROLL_KEY | 密钥生成（需 `X-Internal-Token`） |
| POST | /generate/request/REENROLL_KEY | 重新生成（需 `X-Internal-Token`） |
| POST | /generate/request/comparam | 获取公共参数（需 `X-Internal-Token`） |
| GET | /generate/ping | 健康检查 |

说明：`Register` 用于用户注册流程，不走内部鉴权；其余 `/generate/request/*` 接口仅允许已完成用户鉴权的 Java 后端转发调用，请在 Header 中携带 `X-Internal-Token`。

## ENROLL_KEY 请求示例

```json
{
  "user": "testuser",
  "password": "password123",
  "encryt_type": "无证书非对称加密",
  "encryt_name": "SSCL",
  "ua": "04...",
  "key_domain": "default"
}
```

## 压测脚本

```bash
# 启动压测 (需先安装 wrk)
./benchmark.sh
```

或使用 ab:

```bash
ab -n 10000 -c 100 -p payload.json -T application/json http://localhost:8081/generate/request/ENROLL_KEY
```
