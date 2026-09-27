#!/bin/bash
# KMS-OPS 一键启动脚本
# 支持 kms-generate 和 kms-updatedel 双系统启动

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

DOCKER_COMPOSE=()
FISCO_TEMPLATE_ROOT="$SCRIPT_DIR/fisco/template"
FISCO_TEMPLATE_NODE_ROOT="$FISCO_TEMPLATE_ROOT/nodes/127.0.0.1"
FISCO_TEMPLATE_CONSOLE_CONF="$FISCO_TEMPLATE_ROOT/console/conf"
FISCO_TEMPLATE_STATE_ENV="$FISCO_TEMPLATE_ROOT/state/.env.template.local"
FISCO_LIVE_NODE_ROOT="$SCRIPT_DIR/nodes/127.0.0.1"
FISCO_LIVE_CONSOLE_CONF="$SCRIPT_DIR/fisco/console/conf"
FISCO_LIVE_STATE_DIR="$SCRIPT_DIR/fisco/live"
FISCO_LIVE_STATE_ENV="$FISCO_LIVE_STATE_DIR/contract.env"

init_docker_compose() {
    if docker compose version >/dev/null 2>&1; then
        DOCKER_COMPOSE=(docker compose)
        return 0
    fi

    if sudo -n docker compose version >/dev/null 2>&1; then
        DOCKER_COMPOSE=(sudo docker compose)
        return 0
    fi

    if command -v run_compose >/dev/null 2>&1; then
        DOCKER_COMPOSE=(run_compose)
        return 0
    fi

    if sudo -n run_compose version >/dev/null 2>&1; then
        DOCKER_COMPOSE=(sudo run_compose)
        return 0
    fi

    echo "[ERROR] docker compose is not available or requires sudo without cached credentials"
    exit 1
}

run_compose() {
    if [ ${#DOCKER_COMPOSE[@]} -eq 0 ]; then
        init_docker_compose
    fi
    "${DOCKER_COMPOSE[@]}" "$@"
}

restore_dir_from_template() {
    local source_dir="$1"
    local target_dir="$2"
    local label="$3"

    if [ ! -d "$source_dir" ]; then
        echo "[ERROR] 缺少${label}模板目录: $source_dir" >&2
        return 1
    fi

    echo "[INFO] 从模板恢复${label}..."
    rm -rf "$target_dir"
    mkdir -p "$target_dir"
    cp -a "$source_dir/." "$target_dir/"
}

ensure_writable_dir() {
    local target_dir="$1"

    if [ -d "$target_dir" ] && [ ! -w "$target_dir" ]; then
        rm -rf "$target_dir"
    fi

    mkdir -p "$target_dir"
}

ensure_dotenv_value() {
    local key="$1"
    local value="$2"

    if grep -q "^${key}=" .env; then
        python3 - "$key" "$value" .env <<'PY'
import sys
from pathlib import Path
key, value, path = sys.argv[1:4]
p = Path(path)
lines = p.read_text().splitlines()
out = []
for line in lines:
    if line.startswith(f"{key}="):
        out.append(f"{key}={value}")
    else:
        out.append(line)
p.write_text("\n".join(out) + "\n")
PY
    else
        printf '\n%s=%s\n' "$key" "$value" >> .env
    fi
}

sync_contract_env_from_state() {
    local state_file="$1"

    if [ ! -f "$state_file" ]; then
        return 0
    fi

    local contract_address
    local private_key
    contract_address=$(grep '^FISCO_CONTRACT_ADDRESS=' "$state_file" | tail -n 1 | cut -d '=' -f 2-)
    private_key=$(grep '^FISCO_PRIVATE_KEY=' "$state_file" | tail -n 1 | cut -d '=' -f 2-)

    if [ -n "$contract_address" ]; then
        ensure_dotenv_value "FISCO_CONTRACT_ADDRESS" "$contract_address"
    fi
    if [ -n "$private_key" ]; then
        ensure_dotenv_value "FISCO_PRIVATE_KEY" "$private_key"
    fi
}

restore_fisco_live_state() {
    ensure_writable_dir "$FISCO_LIVE_STATE_DIR"

    if [ ! -f "$FISCO_LIVE_NODE_ROOT/node0/start.sh" ]; then
        restore_dir_from_template "$FISCO_TEMPLATE_NODE_ROOT" "$FISCO_LIVE_NODE_ROOT" "单节点链"
        sed -i 's/listen_ip=127.0.0.1/listen_ip=0.0.0.0/g' "$FISCO_LIVE_NODE_ROOT"/node*/config.ini 2>/dev/null || true
    fi

    if [ ! -f "$FISCO_LIVE_CONSOLE_CONF/ca.crt" ] || [ ! -f "$FISCO_LIVE_CONSOLE_CONF/sdk.crt" ] || [ ! -f "$FISCO_LIVE_CONSOLE_CONF/sdk.key" ]; then
        restore_dir_from_template "$FISCO_TEMPLATE_CONSOLE_CONF" "$FISCO_LIVE_CONSOLE_CONF" "FISCO console 配置"
    fi

    if [ -f "$FISCO_LIVE_STATE_ENV" ]; then
        sync_contract_env_from_state "$FISCO_LIVE_STATE_ENV"
    elif [ -f "$FISCO_TEMPLATE_STATE_ENV" ]; then
        cp "$FISCO_TEMPLATE_STATE_ENV" "$FISCO_LIVE_STATE_ENV"
        sync_contract_env_from_state "$FISCO_LIVE_STATE_ENV"
    fi
}

echo "=========================================="
echo "  KMS-OPS 双系统启动脚本"
echo "=========================================="

if [ ! -f "docker-compose.yml" ]; then
    echo "[ERROR] docker-compose.yml not found!"
    exit 1
fi

if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "[INFO] 未检测到 .env，使用 .env.example 初始化..."
        cp .env.example .env
    else
        echo "[ERROR] .env and .env.example are both missing" >&2
        exit 1
    fi
fi

echo "[INFO] 创建必要的数据目录..."
mkdir -p mysql/data mysql/init redis/data kafka/kafka_data
mkdir -p fisco/console/account fisco/console/accounts fisco/console/log
mkdir -p fisco/live
mkdir -p nginx/logs
# 注意：/generate/ 静态前端已退役，不再需要 front/generate
#（详见 kms-generate/front/RETIRED.md；generate 后端仍在下面的 runtime/ 清单里）
mkdir -p front/updatedel front/distribute front/user front/acceptance
mkdir -p runtime/generate-go runtime/generate-java runtime/updatedel-go runtime/updatedel-java runtime/acceptance-go

if [ ! -f "runtime/generate-go/kms-generate-service" ] \
    || [ ! -f "runtime/generate-java/kms-generate.jar" ] \
    || [ ! -f "runtime/updatedel-go/kms-updatedel-service" ] \
    || [ ! -f "runtime/updatedel-java/kms-updatedel.jar" ] \
    || [ ! -f "runtime/acceptance-go/kms-acceptance-backend" ] \
    || [ ! -f "runtime/acceptance-go/security/security_test.sh" ] \
    || [ ! -f "front/updatedel/index.html" ] \
    || [ ! -f "front/distribute/index.html" ] \
    || [ ! -f "front/user/index.html" ] \
    || [ ! -f "front/acceptance/index.html" ]; then
    echo "[ERROR] 缺少运行产物，请先执行 bash ./build-local.sh" >&2
    exit 1
fi

restore_fisco_live_state

if [ ! -d "fisco/console/apps" ] || [ ! -d "fisco/console/lib" ]; then
    echo "[INFO] 未检测到 FISCO Console 运行包，开始下载并初始化..."
    rm -rf nodes/127.0.0.1/console nodes/127.0.0.1/console*.tar.gz
    (
        cd nodes/127.0.0.1
        bash ./download_console.sh -f
    )
    rm -rf fisco/console/apps fisco/console/lib fisco/console/classes
    cp -R nodes/127.0.0.1/console/apps fisco/console/apps
    cp -R nodes/127.0.0.1/console/lib fisco/console/lib
    if [ -d "nodes/127.0.0.1/console/classes" ]; then
        cp -R nodes/127.0.0.1/console/classes fisco/console/classes
    fi
fi

if [ -d "nodes/127.0.0.1/sdk" ]; then
    cp -f nodes/127.0.0.1/sdk/* fisco/console/conf/
fi

if ! chmod -R 0777 kafka/kafka_data 2>/dev/null; then
    echo "[WARN] 无法修改 kafka/kafka_data 权限，继续使用现有权限..."
fi

echo "[INFO] 启动所有容器..."
run_compose up -d --force-recreate \
    fisco-node \
    fisco-console \
    generate-go \
    generate-java \
    updatedel-go \
    updatedel-java \
    acceptance-backend \
    nginx

echo "[INFO] 等待中间件启动..."
sleep 5

# ---------------------------------------------------------------------------
# 幂等补齐运行期新增的数据库列
# ---------------------------------------------------------------------------
# key_operation_record.proof_path 是本次改造新增的列，用于存储 Merkle 证明路径。
# 注意：mysql/init/ 下的脚本只在 MySQL 数据卷为空时执行，
# 因此对已存在的部署必须在此补齐，否则证明刷新会因缺列而失败。
ensure_key_operation_record_proof_path() {
    local db_password
    db_password="${MYSQL_ROOT_PASSWORD:-}"
    if [ -z "$db_password" ] && [ -f ".env" ]; then
        db_password=$(grep '^MYSQL_ROOT_PASSWORD=' .env | tail -n 1 | cut -d '=' -f 2-)
    fi
    if [ -z "$db_password" ]; then
        echo "[WARN] 未找到 MYSQL_ROOT_PASSWORD，跳过 proof_path 列补齐检查"
        return 0
    fi

    # 等待 MySQL 可用（最多 ~60s）
    local i
    for i in $(seq 1 30); do
        if docker exec kms_mysql mysqladmin ping -h localhost -p"$db_password" >/dev/null 2>&1; then
            break
        fi
        sleep 2
    done

    local exists
    exists=$(docker exec kms_mysql mysql -N -B -uroot -p"$db_password" -D kms \
        -e "SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='kms' AND TABLE_NAME='key_operation_record' AND COLUMN_NAME='proof_path';" 2>/dev/null || echo "")

    if [ "$exists" = "1" ]; then
        echo "[INFO] key_operation_record.proof_path 已存在，跳过"
        return 0
    fi
    if [ "$exists" != "0" ]; then
        echo "[WARN] 无法确认 proof_path 列状态（MySQL 可能尚未就绪），跳过补齐"
        return 0
    fi

    echo "[INFO] 补齐 key_operation_record.proof_path 列（Merkle 证明路径）..."
    if docker exec kms_mysql mysql -uroot -p"$db_password" -D kms -e \
        "ALTER TABLE key_operation_record ADD COLUMN proof_path VARCHAR(2000) DEFAULT NULL COMMENT 'Merkle proof path: R:<hash>|L:<hash>|ROOT:<hash>';" >/dev/null 2>&1; then
        echo "[INFO] proof_path 列补齐完成"
    else
        echo "[WARN] proof_path 列补齐失败，请手动执行 kms-updatedel/sql/4_key_operation_record_merkle_proof_path.sql"
    fi
}

ensure_key_operation_record_proof_path

if ! grep -q '^FISCO_CONTRACT_ADDRESS=0x' .env; then
    if [ -f "$FISCO_LIVE_STATE_ENV" ]; then
        sync_contract_env_from_state "$FISCO_LIVE_STATE_ENV"
    fi
fi

# 判断是否需要部署合约：
# 1. 没有合约地址 → 需要部署
# 2. 有合约地址但 FISCO_PRIVATE_KEY 为空 → 也需要重新部署（否则上链必然失败）
needs_deploy=false
if ! grep -q '^FISCO_CONTRACT_ADDRESS=0x' .env; then
    needs_deploy=true
    echo "[INFO] 未检测到已部署合约地址，需要部署 KeyEvidence..."
else
    fisco_pk=$(grep '^FISCO_PRIVATE_KEY=' .env | tail -n 1 | cut -d '=' -f 2-)
    if [ -z "$fisco_pk" ]; then
        needs_deploy=true
        echo "[INFO] FISCO_PRIVATE_KEY 为空，需要重新部署 KeyEvidence 以提取部署账户私钥..."
    fi
fi

if [ "$needs_deploy" = true ]; then
    echo "[INFO] 开始自动部署 KeyEvidence..."
    bash ./deploy-keyevidence.sh
fi

echo ""
echo "[INFO] 容器状态:"
run_compose ps

echo ""
echo "=========================================="
echo "  KMS-OPS 启动完成!"
echo ""
echo "  访问地址:"
echo "  - 网关:      http://localhost:80"
echo "  - 生成系统:  http://localhost:80/generate/"
echo "  - 生命周期:  http://localhost:80/lifecycle/"
echo ""
echo "  后端端口:"
echo "  - generate-go:     8081"
echo "  - generate-java:  9081"
echo "  - updatedel-go:   8082"
echo "  - updatedel-java: 9082"
echo ""
echo "  中间件端口:"
echo "  - MySQL: 3306"
echo "  - Redis: 6379"
echo "  - Kafka: 9092"
echo "=========================================="
