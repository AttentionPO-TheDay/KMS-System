#!/bin/bash

# KMS 生成链路压测脚本 (ENROLL_KEY)
# 使用 wrk 进行 HTTP 压测，并通过 Kafka 发送消息

set -e

# 配置参数
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# 默认配置
KAFKA_BROKER="${KAFKA_BROKER:-localhost:9092}"
KAFKA_TOPIC="key_generate_log"
JAVA_BACKEND_URL="${JAVA_BACKEND_URL:-http://localhost:8080}"
THREADS="${THREADS:-4}"
CONNECTIONS="${CONNECTIONS:-100}"
DURATION="${DURATION:-30s}"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 生成 UUID
generate_uuid() {
    cat /proc/sys/kernel/random/uuid 2>/dev/null || uuidgen 2>/dev/null || printf '%04x%04x-%04x-%04x-%04x-%04x%04x%04x\n' $RANDOM $RANDOM $RANDOM $RANDOM $RANDOM $RANDOM $RANDOM $RANDOM
}

# 生成随机用户ID
generate_user_id() {
    echo "user_$(generate_uuid)"
}

# 生成 payload
generate_payload() {
    local trace_id=$(generate_uuid)
    local request_id=$(generate_uuid)
    local user_id=${1:-$(generate_user_id)}
    local algorithm=${2:-"SSCL"}
    local key_size=${3:-256}
    local timestamp=$(date +%s)

    cat <<EOF
{
  "traceId": "$trace_id",
  "requestId": "$request_id",
  "actionType": "ENROLL_KEY",
  "userId": "$user_id",
  "keyAlgorithm": "$algorithm",
  "keySize": $key_size,
  "timestamp": $timestamp
}
EOF
}

# 发送 Kafka 消息
send_kafka_message() {
    local payload=$1
    local topic=${2:-$KAFKA_TOPIC}

    if command -v kafka-console-producer.sh &> /dev/null; then
        echo "$payload" | kafka-console-producer.sh --broker-list "$KAFKA_BROKER" --topic "$topic" 2>/dev/null
    elif command -v kafkacat &> /dev/null; then
        echo "$payload" | kafkacat -b "$KAFKA_BROKER" -t "$topic" -P 2>/dev/null
    elif command -v kcat &> /dev/null; then
        echo "$payload" | kcat -b "$KAFKA_BROKER" -t "$topic" -P 2>/dev/null
    else
        log_warn "Kafka producer not found, using HTTP API"
        send_http_message "$payload"
    fi
}

# 通过 HTTP 发送消息
send_http_message() {
    local payload=$1
    curl -s -X POST "$JAVA_BACKEND_URL/api/v1/key/generate" \
        -H "Content-Type: application/json" \
        -d "$payload" > /dev/null 2>&1
}

# 生成 Lua 脚本用于 wrk
generate_lua_script() {
    local algorithm=${1:-"SSCL"}
    local key_size=${2:-256}

    cat <<EOF
wrk.method = "POST"
wrk.headers["Content-Type"] = "application/json"

request_num = 0

function gen_uuid()
    local template = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
    return string.gsub(template, "x", function(c)
        local v = (c == "x") and math.random(0, 0xf) or math.random(8, 0xb)
        return string.format("%x", v)
    end)
end

function request()
    request_num = request_num + 1
    local trace_id = gen_uuid()
    local request_id = gen_uuid()
    local user_id = "load_test_user_" .. request_num
    local timestamp = os.time()

    local body = string.format([[{
        "traceId": "%s",
        "requestId": "%s",
        "actionType": "ENROLL_KEY",
        "userId": "%s",
        "keyAlgorithm": "%s",
        "keySize": %d,
        "timestamp": %d
    }]], trace_id, request_id, user_id, "$algorithm", $key_size, timestamp)

    return wrk.format("POST", "$JAVA_BACKEND_URL/api/v1/key/generate", wrk.headers, body)
end

response_count = 0
total_latency = 0

function response(status, headers, body)
    response_count = response_count + 1
end
EOF
}

# 运行压测
run_load_test() {
    local test_name="ENROLL_KEY (Generate)"
    local api_path="/api/v1/key/generate"
    local lua_script_file="/tmp/kms_generate_test.lua"

    log_info "========================================="
    log_info "KMS $test_name Load Test"
    log_info "========================================="
    log_info "Target URL: $JAVA_BACKEND_URL$api_path"
    log_info "Threads: $THREADS"
    log_info "Connections: $CONNECTIONS"
    log_info "Duration: $DURATION"
    log_info "Kafka Broker: $KAFKA_BROKER"
    log_info "Kafka Topic: $KAFKA_TOPIC"
    log_info "-----------------------------------"

    # 生成 Lua 脚本
    generate_lua_script "SSCL" 256 > "$lua_script_file"

    # 检查 wrk 是否可用
    if command -v wrk &> /dev/null; then
        log_info "Running wrk load test..."
        wrk -t"$THREADS" -c"$CONNECTIONS" -d"$DURATION" -s "$lua_script_file" "$JAVA_BACKEND_URL$api_path"
    else
        log_warn "wrk not found, using alternative method"
        alternative_load_test "$test_name" "$api_path"
    fi

    log_info "========================================="
    log_info "Load test completed"
    log_info "========================================="
}

# 备选压测方法
alternative_load_test() {
    local test_name=$1
    local api_path=$2

    log_info "Sending test requests..."

    local start_time=$(date +%s)
    local success_count=0
    local fail_count=0

    for i in $(seq 1 100); do
        local payload=$(generate_payload)
        local response=$(curl -s -w "%{http_code}" -o /dev/null -X POST "$JAVA_BACKEND_URL$api_path" \
            -H "Content-Type: application/json" \
            -d "$payload" 2>/dev/null)

        if [ "$response" = "200" ]; then
            ((success_count++))
        else
            ((fail_count++))
        fi
    done

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    local qps=$(echo "scale=2; 100 / $duration" | bc 2>/dev/null || echo "N/A")

    echo ""
    log_info "Results:"
    log_info "  Total Requests: 100"
    log_info "  Success: $success_count"
    log_info "  Failed: $fail_count"
    log_info "  Duration: ${duration}s"
    log_info "  QPS: $qps"
}

# 验证链路
verify_chain() {
    log_info "========================================="
    log_info "Verifying Generate Chain (ENROLL_KEY)"
    log_info "========================================="

    local test_payload=$(generate_payload "test_user_001" "SSCL" 256)

    log_info "Sending test message to Kafka topic: $KAFKA_TOPIC"
    log_info "Payload: $test_payload"

    # 1. 发送到 Java Backend
    log_info "Step 1: Client -> Java Backend"
    local http_response=$(curl -s -w "\n%{http_code}" -X POST "$JAVA_BACKEND_URL/api/v1/key/generate" \
        -H "Content-Type: application/json" \
        -d "$test_payload")
    local http_code=$(echo "$http_response" | tail -n1)

    if [ "$http_code" = "200" ]; then
        log_info "  Result: PASS (HTTP $http_code)"
    else
        log_error "  Result: FAIL (HTTP $http_code)"
    fi

    # 2. 验证 Kafka 消息
    log_info "Step 2: Java Backend -> Kafka"
    log_info "  Topic: $KAFKA_TOPIC"
    log_info "  Result: (Verify with kafka-consumer)"

    # 3. 验证 Go Backend 消费
    log_info "Step 3: Kafka -> Go Backend"
    log_info "  Result: (Verify with Go Backend logs)"

    # 4. 验证上链
    log_info "Step 4: Go Backend -> FISCO-BCOS"
    log_info "  Result: (Verify with blockchain explorer)"

    log_info "========================================="
}

# 显示帮助
show_help() {
    cat <<EOF
KMS Generate Load Test Script (ENROLL_KEY)

Usage: $0 [OPTIONS]

OPTIONS:
    -u, --url          Java Backend URL (default: $JAVA_BACKEND_URL)
    -k, --kafka        Kafka Broker (default: $KAFKA_BROKER)
    -t, --threads      Number of threads (default: $THREADS)
    -c, --connections  Number of connections (default: $CONNECTIONS)
    -d, --duration     Test duration (default: $DURATION)
    -v, --verify       Verify chain only, no load test
    -h, --help         Show this help message

EXAMPLES:
    $0                                    # Run with defaults
    $0 -u http://localhost:8080 -t 8     # Custom URL and threads
    $0 --verify                           # Verify chain only

EOF
}

# 主函数
main() {
    case "${1:-}" in
        -h|--help)
            show_help
            exit 0
            ;;
        -v|--verify)
            verify_chain
            exit 0
            ;;
        *)
            if [ "$#" -gt 0 ]; then
                # 解析参数
                while [ "$#" -gt 0 ]; do
                    case "$1" in
                        -u|--url)
                            JAVA_BACKEND_URL="$2"
                            shift 2
                            ;;
                        -k|--kafka)
                            KAFKA_BROKER="$2"
                            shift 2
                            ;;
                        -t|--threads)
                            THREADS="$2"
                            shift 2
                            ;;
                        -c|--connections)
                            CONNECTIONS="$2"
                            shift 2
                            ;;
                        -d|--duration)
                            DURATION="$2"
                            shift 2
                            ;;
                        *)
                            log_error "Unknown option: $1"
                            show_help
                            exit 1
                            ;;
                    esac
                done
            fi

            run_load_test
            ;;
    esac
}

main "$@"
