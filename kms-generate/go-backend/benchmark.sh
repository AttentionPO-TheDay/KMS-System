#!/bin/bash

# 压测脚本 - 需要先启动服务 go run cmd/main.go

HOST="http://localhost:8081"
ENDPOINT="/generate/request/ENROLL_KEY"

# 生成测试 UA (130字符，04开头)
UA="04"
for i in {1..64}; do UA="${UA}$(printf '%02x' $((RANDOM % 256)))"; done
for i in {1..64}; do UA="${UA}$(printf '%02x' $((RANDOM % 256)))"; done

# 生成 payload
cat > /tmp/enroll_payload.json << EOF
{
  "user": "loadtest_user",
  "password": "password123",
  "encryt_type": "无证书非对称加密",
  "encryt_name": "SSCL",
  "ua": "${UA}",
  "key_domain": "loadtest_domain"
}
EOF

echo "=== KMS Generate Backend 压测 ==="
echo "Target: ${HOST}${ENDPOINT}"
echo "Payload prepared, starting load test..."

# 使用 ab 进行压测 (ApacheBench)
if command -v ab &> /dev/null; then
    ab -n 10000 -c 100 -p /tmp/enroll_payload.json -T application/json "${HOST}${ENDPOINT}"
else
    echo "ab not found, trying wrk..."
    if command -v wrk &> /dev/null; then
        wrk -t10 -c100 -d30s -s /tmp/enroll_payload.json "${HOST}${ENDPOINT}"
    else
        echo "Neither ab nor wrk found. Please install one of them."
        echo "Alternatively, use curl for simple test:"
        curl -X POST "${HOST}${ENDPOINT}" -H "Content-Type: application/json" -d @/tmp/enroll_payload.json
    fi
fi
