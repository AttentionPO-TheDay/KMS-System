#!/usr/bin/env bash
# =============================================================================
# deploy.sh —— 远端部署脚本（自包含镜像模式）
# -----------------------------------------------------------------------------
# 前提：已在本目录解包 kms-deploy.tar.gz，并已 docker load 载入 kms-images.tar
#
# 用法：
#   bash deploy.sh load     载入镜像（等价 docker load -i kms-images.tar）
#   bash deploy.sh check    仅做部署前检查（不启动）
#   bash deploy.sh up       启动全部服务
#   bash deploy.sh down     停止（保留数据）
#   bash deploy.sh ps       查看容器状态
#   bash deploy.sh logs     跟踪网关日志
#   bash deploy.sh verify   启动后健康检查（HTTP 探测）
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")"

COMPOSE_FILE="docker-compose.yml"
ENV_FILE=".env"

log()  { printf '\033[36m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m[OK]\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m[!]\033[0m %s\n' "$*"; }
die()  { printf '  \033[31m[ERR]\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 部署前检查
# ---------------------------------------------------------------------------
do_check() {
  log "=== 部署前检查 ==="

  command -v docker >/dev/null 2>&1 || die "未安装 docker"
  docker info >/dev/null 2>&1 || die "docker 守护进程未运行"
  ok "docker 可用: $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo unknown)"

  if docker compose version >/dev/null 2>&1; then
    ok "docker compose 可用"
  else
    die "缺少 docker compose 插件"
  fi

  [ -f "$COMPOSE_FILE" ] || die "缺少 $COMPOSE_FILE"
  [ -f "$ENV_FILE" ]     || die "缺少 $ENV_FILE"
  ok "compose 与 .env 均存在"

  # .env 必填项：与 compose 中的 ${VAR:?...} 对应
  local missing=0
  for k in MYSQL_ROOT_PASSWORD KMS_TOKEN_SECRET INTERNAL_TOKEN \
           DRUID_LOGIN_USERNAME DRUID_LOGIN_PASSWORD; do
    if ! grep -qE "^${k}=.+" "$ENV_FILE"; then
      warn "$k 未设置（启动会失败）"
      missing=$((missing+1))
    fi
  done
  [ "$missing" -eq 0 ] && ok "必填环境变量齐备"

  # FISCO 配置提示（值不校验，仅提醒）
  local addr pk
  addr=$(grep -E '^FISCO_CONTRACT_ADDRESS=' "$ENV_FILE" | cut -d= -f2- || true)
  pk=$(grep -E '^FISCO_PRIVATE_KEY=' "$ENV_FILE" | cut -d= -f2- || true)
  if [ -n "$addr" ]; then ok "FISCO 合约地址: $addr"; else warn "FISCO_CONTRACT_ADDRESS 为空，上链会失败"; fi
  if [ -n "$pk" ]; then ok "FISCO 私钥已配置（${#pk} 字符）"; else warn "FISCO_PRIVATE_KEY 为空，上链会失败"; fi

  # 必需的数据/配置目录
  for d in mysql/init nodes/127.0.0.1 fisco/console/conf nginx; do
    [ -e "$d" ] && ok "存在: $d" || warn "缺失: $d"
  done

  # 镜像是否已载入
  local imgs="kms-generate-go:local kms-generate-java:local kms-updatedel-go:local
kms-updatedel-java:local kms-acceptance-backend:local
kms-gateway-nginx:local kms-dvadmin3-django:local"
  local img_missing=0
  for i in $imgs; do
    if ! docker image inspect "$i" >/dev/null 2>&1; then
      warn "镜像未载入: $i"
      img_missing=$((img_missing+1))
    fi
  done
  if [ "$img_missing" -eq 0 ]; then
    ok "7 个应用镜像均已载入"
  else
    warn "有 $img_missing 个应用镜像尚未构建/载入"
    warn "  - 源码模式（本包）：bash deploy.sh build"
    warn "  - 镜像模式（kms-images.tar）：bash deploy.sh load"
  fi

  # -------- 构建输入（源码模式下最容易出问题的地方）--------
  # FTP/手工上传最常见的失败不是"命令敲错"，而是**漏传文件**：
  # 镜像里 COPY 的是本地构建产物（runtime/、front/）与 Dockerfile，
  # 它们平时被 .gitignore 排除，手工挑选上传时极易漏。
  # 这里逐一核对，让问题在上传后就暴露，而不是等 docker build 报一句难懂的错误。
  local build_missing=0
  for f in runtime/generate-java/kms-generate.jar \
           runtime/updatedel-java/kms-updatedel.jar \
           runtime/generate-go/kms-generate-service \
           runtime/updatedel-go/kms-updatedel-service \
           runtime/acceptance-go/kms-acceptance-backend \
           runtime/acceptance-go/security/security_test.sh \
           front/updatedel/index.html front/user/index.html \
           front/acceptance/index.html \
           build/generate-java.Dockerfile build/updatedel-java.Dockerfile \
           build/generate-go.Dockerfile build/updatedel-go.Dockerfile \
           build/acceptance-go.Dockerfile build/nginx.Dockerfile \
           portal/index.html mysql/my.cnf \
           fisco/console/conf/ca.crt fisco/console/conf/sdk.crt fisco/console/conf/sdk.key \
           nodes/127.0.0.1/fisco-bcos \
           nodes/127.0.0.1/node0/conf/group.1.genesis \
           nodes/127.0.0.1/node0/conf/channel_cert/ca.crt \
           "../kms-distribute/extracted/ruoyi (2)/backend/start.sh" \
           "../kms-distribute/extracted/ruoyi (2)/requirements.txt" \
           "../kms-distribute/extracted/ruoyi (2)/docker_env/django/Dockerfile"; do
    if [ ! -e "$f" ]; then
      warn "缺少构建输入: $f"
      build_missing=$((build_missing+1))
    fi
  done
  if [ "$build_missing" -eq 0 ]; then
    ok "构建输入齐备（上层产物 / Dockerfile / 链数据 / Django 上下文）"
  else
    warn "有 $build_missing 项构建输入缺失 —— 构建一定失败，请补齐后再继续"
  fi

  # -------- 架构 --------
  # kms-images.tar（镜像模式）只能在 amd64 上跑；源码模式在远端构建，
  # 架构天然匹配，因此这里只提示、不拦截。
  local arch
  arch=$(uname -m 2>/dev/null || echo unknown)
  ok "本机架构: $arch（源码模式在本地构建镜像，amd64/arm64 均可）"

  # -------- 端口占用 --------
  # 只说"被占用"没用：真正要判断的是**占用者是不是本项目自己的容器**。
  #   * 本项目的 kms_* 容器占着端口 → 正常，up 时会重建它们；
  #   * 别的容器或非容器进程占着 → 必须先在那边停掉，否则报
  #       failed to bind host port 127.0.0.1:8081/tcp: address already in use
  #     （2026-09-24 远端实测：端口绑定改成回环后，旧容器没停干净就会撞这个错）
  #
  # 注意这里**不再**检查 8081/8082/9081/9082/8001：compose 已经把它们的宿主发布
  # 去掉了（网关与验收容器都按服务名在 Docker 内网访问），因此这些端口不会被占用，
  # 也就不该再要求部署环境"腾出"它们。要在本机直连调试请加覆盖文件：
  #   docker compose -f docker-compose.yml -f docker-compose.debug-ports.yml up -d
  local busy=""
  for p in 80 3307 6379 9092 8545 20200; do
    if command -v ss >/dev/null 2>&1 && ss -ltn "sport = :$p" 2>/dev/null | grep -q LISTEN; then
      local who
      who=$(docker ps --filter "publish=$p" --format '{{.Names}}' 2>/dev/null | head -1 || true)
      if [ -n "$who" ]; then busy="$busy ${p}(${who})"; else busy="$busy ${p}(非容器进程)"; fi
    fi
  done
  if [ -n "$busy" ]; then
    warn "端口已被占用:$busy"
    warn "  括号内为占用者。若全是本项目的 kms_* 容器 → 正常，up 会重建；"
    warn "  若出现别的容器名或'非容器进程' → 必须先释放，否则 up 会报 address already in use"
  else
    ok "关键端口空闲"
  fi

  # -------- 公共基础镜像 --------
  # 远端连不上 Docker Hub 时，构建会在第一步就失败（load metadata ... i/o timeout）。
  # 与其让用户去猜，这里直接点名缺哪个、怎么补。
  local baseList="debian:bookworm-slim eclipse-temurin:8-jre nginx:alpine mysql:8.0 redis:6.2 apache/kafka:latest ubuntu:22.04"
  local base_missing=""
  for bi in $baseList; do
    docker image inspect "$bi" >/dev/null 2>&1 || base_missing="$base_missing $bi"
  done
  if [ -z "$base_missing" ]; then
    ok "7 个公共基础镜像均已就绪"
  else
    warn "公共基础镜像缺失:$base_missing"
    warn "  远端拉不到 Docker Hub 时，两条修法："
    warn "    A) 配镜像加速器: /etc/docker/daemon.json 加 {\"registry-mirrors\":[\"https://<加速器>\"]}"
    warn "       然后 systemctl restart docker，并用 docker pull nginx:alpine 验证"
    warn "    B) 从本机带过来: 本机 ship-source.ps1 -WithBaseImages → 上传 kms-base-images.tar"
    warn "       → 远端 bash deploy.sh load-base"
    warn "  注意：即使镜像就绪，apt-get / apk add 仍需对应包源可达。"
  fi

  # -------- 网络子网（静态 IP 的前提）--------
  # 4 个 FISCO 节点用静态 IP 172.20.0.101~104，且这个网段写死在各节点的 config.ini
  # 里做 peer 地址。若已存在的 kms_net 子网不是 172.20.0.0/16，`up` 会直接失败：
  #   invalid endpoint settings: no configured subnet contains IP address 172.20.0.104
  # 本机之所以正常，只是因为当初 Docker 恰好把该网络分到了 172.20.0.0/16。
  local net_name="kms-ops_kms_net"
  if docker network inspect "$net_name" >/dev/null 2>&1; then
    local subnet
    subnet=$(docker network inspect "$net_name" --format '{{range .IPAM.Config}}{{.Subnet}}{{end}}' 2>/dev/null || echo "")
    if [ "$subnet" = "172.20.0.0/16" ]; then
      ok "网络 $net_name 子网正确（$subnet）"
    else
      warn "网络 $net_name 现存子网为 '${subnet:-未知}'，而节点静态 IP 需要 172.20.0.0/16"
      warn "  修法: sudo docker compose down && sudo docker network rm $net_name && sudo docker compose up -d"
      warn "  （compose 已显式声明该子网；这里是把旧网络删掉让它按新配置重建）"
    fi
  else
    ok "网络 $net_name 尚未创建（首次 up 时会按 compose 声明的 172.20.0.0/16 创建）"
  fi

  # -------- 运行态目录属主（Linux 上最容易漏的一步）--------
  if [ -d kafka/kafka_data ]; then
    local kowner
    kowner=$(stat -c '%u:%g' kafka/kafka_data 2>/dev/null || echo "")
    if [ "$kowner" = "1000:1000" ]; then
      ok "kafka/kafka_data 属主正确（1000:1000）"
    else
      warn "kafka/kafka_data 属主为 '${kowner:-未知}'，而 kafka 以 appuser(1000) 运行"
      warn "  这会让 broker 起不来，现象是 'container kms_kafka is unhealthy'"
      warn "  修法: sudo chown -R 1000:1000 kafka/kafka_data（或 bash deploy.sh prepare）"
    fi
  else
    ok "kafka/kafka_data 尚未创建（up 时会创建并 chown）"
  fi

  log "检查结束"
}

# ---------------------------------------------------------------------------
# 载入镜像
# ---------------------------------------------------------------------------
do_load() {
  [ -f kms-images.tar ] || die "找不到 kms-images.tar"
  log "=== 载入镜像（可能需要数分钟）==="
  docker load -i kms-images.tar
  ok "镜像载入完成"
}

# ---------------------------------------------------------------------------
# 构建镜像（源码模式：包里带的是构建输入，镜像在远端构建）
# ---------------------------------------------------------------------------
do_build() {
  log "=== 构建应用镜像（源码模式）==="
  log "基础镜像（mysql/redis/kafka/ubuntu/temurin）会自动从仓库拉取"
  docker compose -f "$COMPOSE_FILE" build
  ok "7 个应用镜像构建完成"
  log "下一步: bash deploy.sh up"
}

# ---------------------------------------------------------------------------
# 载入公共基础镜像（远端连不上 Docker Hub 时用）
# ---------------------------------------------------------------------------
do_load_base() {
  [ -f kms-base-images.tar ] || die "找不到 kms-base-images.tar（需在本机执行 ship-source.ps1 -WithBaseImages 后上传）"
  log "=== 载入公共基础镜像 ==="
  docker load -i kms-base-images.tar
  ok "基础镜像载入完成，可离线构建: bash deploy.sh build"
}

# ---------------------------------------------------------------------------
# 准备运行态目录的属主（Linux 上的必做项）
# ---------------------------------------------------------------------------
# 为什么需要：bind 挂载只在宿主机上"存在"，容器里的用户能不能写取决于宿主目录属主。
#   * Docker Desktop（Windows/macOS）会自动兜住，所以本地怎么都正常；
#   * Linux 不会 —— 目录由 Docker 以 root 创建，或由上传用户创建，
#     而容器内进程往往不是 root，于是启动即失败。
# 实测（2026-09-24 远端）：kafka 数据目录属主不对，broker 起不来，
# 报错表现为 "dependency failed to start: container kms_kafka is unhealthy"。
#
# 各服务为什么只有 kafka 需要显式 chown：
#   kafka   → 镜像 USER=appuser(1000)，**没有 root 入口**去 chown → 必须宿主先给对
#   redis   → 官方 entrypoint 以 root 启动并 chown /data 后降权 → 不用管
#   mysql   → entrypoint 以 root 启动并 chown datadir → 不用管
#   nginx / django → 以 root 运行 → 不用管
prepare_runtime_dirs() {
  log "=== 准备运行态目录 ==="
  mkdir -p kafka/kafka_data mysql/data redis/data nginx/logs dvadmin-logs

  if [ "$(id -u)" != "0" ]; then
    warn "当前不是 root，跳过 chown。请用 sudo 运行，或手工执行："
    warn "  sudo chown -R 1000:1000 kafka/kafka_data"
    return 0
  fi

  if chown -R 1000:1000 kafka/kafka_data 2>/dev/null; then
    ok "kafka/kafka_data -> 1000:1000（镜像里的 appuser）"
  else
    warn "chown kafka/kafka_data 失败，请手工检查该目录属主"
  fi
  ok "其余目录保持 root（redis/mysql 的 entrypoint 会自行 chown，nginx/django 以 root 运行）"
}

do_up() {
  do_check
  prepare_runtime_dirs
  log "=== 启动服务 ==="
  docker compose -f "$COMPOSE_FILE" up -d
  ok "已启动。等待健康检查…"
  sleep 20
  docker compose -f "$COMPOSE_FILE" ps
}

do_down() {
  log "=== 停止服务（数据卷保留）==="
  docker compose -f "$COMPOSE_FILE" down
}

do_ps()   { docker compose -f "$COMPOSE_FILE" ps; }
do_logs() { docker compose -f "$COMPOSE_FILE" logs -f nginx; }

# ---------------------------------------------------------------------------
# PQKDS 数据库修复
# ---------------------------------------------------------------------------
# 背景：MySQL 的 DDL 不支持事务回滚。若 Django 迁移中途被中断
# （容器重启、进程被杀等），已建的表会保留，但 django_migrations
# 中不会留下对应记录。此时再次迁移会报
#     (1050, "Table 'dvadmin_system_users' already exists")
# 并形成"启动即失败"的重启循环。
#
# 本命令在确认 falcon_kds 处于该残缺状态后，删库重建并重新迁移。
# 注意：会清空 PQKDS 库的数据（该库仅存后量子演示记录，不影响 kms 主库）。
# ---------------------------------------------------------------------------
do_fix_pqkds() {
  log "=== 检查 falcon_kds 迁移状态 ==="

  local mysql_cid
  mysql_cid=$(docker compose -f "$COMPOSE_FILE" ps -q mysql)
  [ -n "$mysql_cid" ] || die "MySQL 容器未运行"

  local pw
  pw=$(grep -E '^MYSQL_ROOT_PASSWORD=' "$ENV_FILE" | cut -d= -f2-)
  [ -n "$pw" ] || die "无法从 .env 读取 MYSQL_ROOT_PASSWORD"

  local tables applied
  tables=$(docker exec "$mysql_cid" mysql -N -uroot -p"$pw" \
      -e "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='falcon_kds';" 2>/dev/null | tr -d '\r' || echo 0)
  applied=$(docker exec "$mysql_cid" mysql -N -uroot -p"$pw" -D falcon_kds \
      -e "SELECT COUNT(*) FROM django_migrations;" 2>/dev/null | tr -d '\r' || echo 0)

  echo "  表数量: ${tables:-0}   django_migrations 记录: ${applied:-0}"

  # 正常：表 >= 40 且迁移有记录。残缺：有表但迁移记录为空/极少。
  if [ "${tables:-0}" -ge 40 ] && [ "${applied:-0}" -ge 10 ]; then
    ok "状态正常，无需修复"
    return 0
  fi

  warn "检测到残缺迁移状态，将重建 falcon_kds 并重新迁移"
  printf '  确认继续？该库数据会被清空 [y/N] '
  read -r ans
  case "$ans" in
    y|Y) ;;
    *) warn "已取消"; return 1 ;;
  esac

  docker exec "$mysql_cid" mysql -uroot -p"$pw" -e \
      "DROP DATABASE IF EXISTS falcon_kds; CREATE DATABASE falcon_kds DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;" 2>/dev/null
  ok "falcon_kds 已重建"

  log "重启 PQKDS 容器以执行迁移"
  docker compose -f "$COMPOSE_FILE" up -d --force-recreate dvadmin3-django
  sleep 45

  tables=$(docker exec "$mysql_cid" mysql -N -uroot -p"$pw" \
      -e "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='falcon_kds';" 2>/dev/null | tr -d '\r' || echo 0)
  if [ "${tables:-0}" -ge 40 ]; then
    ok "修复完成，表数量: $tables"
  else
    warn "表数量仍为 ${tables:-0}，请查看日志: docker logs dvadmin3-django"
  fi
}

# ---------------------------------------------------------------------------
# 启动后 HTTP 校验
# ---------------------------------------------------------------------------
do_verify() {
  log "=== HTTP 健康检查 ==="
  # 用 127.0.0.1 而非 localhost：启用 IPv6 的机器上 localhost 可能解析到 ::1，
  # 而 docker 端口转发通常只绑 IPv4，会导致误判为服务故障。
  local base="http://127.0.0.1"
  local fail=0
  probe() {
    local name="$1" url="$2"
    local code
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$url" || echo 000)
    if [ "$code" = "200" ]; then ok "$name -> 200"; else warn "$name -> $code"; fail=$((fail+1)); fi
  }
  probe "gateway /ping"        "$base/ping"
  probe "portal /"             "$base/"
  probe "user /user/"          "$base/user/"
  probe "updatedel"            "$base/updatedel/"
  probe "distribute"           "$base/distribute/"
  probe "acceptance"           "$base/acceptance/"
  probe "generate-api"         "$base/generate-api/generate/ping"
  probe "lifecycle-api"        "$base/lifecycle-api/lifecycle/ping"
  probe "acceptance-api"       "$base/acceptance-api/health"

  # `/generate/` 前端已退役（页面并入管理端），网关对它**显式返回 404**。
  # 这里按"应当 404"来验：以前把它当 200 来探，于是每次 verify 都固定报 1 项未通过，
  # 久而久之就没人看这一行了 —— 一个恒假的告警比没有告警更糟。
  local gcode
  gcode=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$base/generate/" || echo 000)
  if [ "$gcode" = "404" ]; then ok "generate 前端 -> 404（已退役，符合预期）"
  else warn "generate 前端 -> $gcode（期望 404）"; fail=$((fail+1)); fi

  if [ "$fail" -eq 0 ]; then
    log "全部通过"
  else
    warn "$fail 项未通过，请查看日志: bash deploy.sh logs"
  fi
}

case "${1:-}" in
  load)      do_load ;;
  load-base) do_load_base ;;
  build)     do_build ;;
  prepare)   prepare_runtime_dirs ;;
  check)     do_check ;;
  up)        do_up ;;
  down)      do_down ;;
  ps)        do_ps ;;
  logs)      do_logs ;;
  verify)    do_verify ;;
  fix-pqkds) do_fix_pqkds ;;
  *)
    cat <<'USAGE'
用法: bash deploy.sh <命令>

  build      构建 7 个应用镜像（源码模式：包里带构建输入，镜像在远端构建）
  load-base  载入公共基础镜像（远端连不上 Docker Hub 时用，需先上传 kms-base-images.tar）
  up         启动全部服务（会自动先做一次 check）
  verify     启动后 HTTP 健康检查
  check      部署前检查（构建输入、环境变量、架构、端口、镜像）
  ps         查看容器状态
  logs       跟踪网关日志
  down       停止服务（保留数据）
  load       载入镜像（仅镜像模式：docker load -i kms-images.tar）
  fix-pqkds  修复 PQKDS 库的残缺迁移状态（会清空 falcon_kds）

源码模式推荐顺序: check -> build -> up -> verify
镜像模式推荐顺序: load  -> check -> up -> verify
等价一步到位（源码模式）: docker compose up -d --build
若后量子密钥生成报 500 且日志出现 "Table ... already exists"，
执行: bash deploy.sh fix-pqkds
USAGE
    ;;
esac
