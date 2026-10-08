$ErrorActionPreference = "Stop"

Push-Location $PSScriptRoot
try {

# 数据库口令从 .env / 环境变量读取，不再硬编码
$MySqlPassword = $env:MYSQL_ROOT_PASSWORD
if ([string]::IsNullOrWhiteSpace($MySqlPassword)) {
    # 兼容未导出环境变量的场景：直接从 .env 读取
    $envFile = Join-Path $PSScriptRoot ".env"
    if (Test-Path $envFile) {
        $line = Select-String -Path $envFile -Pattern '^\s*MYSQL_ROOT_PASSWORD\s*=' | Select-Object -First 1
        if ($line) { $MySqlPassword = ($line.Line -split '=', 2)[1].Trim() }
    }
}
if ([string]::IsNullOrWhiteSpace($MySqlPassword)) {
    throw "未找到 MYSQL_ROOT_PASSWORD，请检查 kms-ops/.env 或环境变量"
}

# ---------------------------------------------------------------------------
# KGC 主私钥（无证书方案里唯一的秘密）
# ---------------------------------------------------------------------------
# 服务端（generate-go / generate-java / updatedel-java）在启动时就会校验它：
# 缺失或仍是那个**公开的演示值**都直接拒绝启动。所以理论上服务能起来就说明配好了。
# 仍然在这里再查一遍，是为了在"服务恰好是旧镜像/旧进程"时也能把问题暴露出来 ——
# 历史教训正是：这一项长期为空，而服务靠硬编码默认值照常启动，没人发现。
$demoKgc = "6BDD93B210F79415FE0F6388C1C932C208319FF7D7E99C972B3535C9F19A9FF9"
$kgc = $env:KGC_MASTER_SECRET
if ([string]::IsNullOrWhiteSpace($kgc)) {
    $envFile = Join-Path $PSScriptRoot ".env"
    if (Test-Path $envFile) {
        $line = Select-String -Path $envFile -Pattern '^\s*KGC_MASTER_SECRET\s*=' | Select-Object -First 1
        if ($line) { $kgc = ($line.Line -split '=', 2)[1].Trim() }
    }
}
if ([string]::IsNullOrWhiteSpace($kgc)) {
    throw "KGC_MASTER_SECRET 未配置。该值是无证书方案里唯一的秘密，缺失时服务会拒绝启动；请参见 kms-ops/.env.example。"
}
if ($kgc -eq $demoKgc) {
    throw "KGC_MASTER_SECRET 仍是公开的演示默认值。任何拿到它的人都能为任意身份伪造部分私钥，请轮换为真实随机值（openssl rand -hex 32）。"
}
if ($kgc.Length -ne 64 -or $kgc -notmatch '^[0-9A-Fa-f]{64}$') {
    throw "KGC_MASTER_SECRET 格式非法：应为 64 位十六进制，实际长度 $($kgc.Length)。"
}
Write-Host "[OK] KGC_MASTER_SECRET 已配置且非演示值（64 位十六进制）"

# ---------------------------------------------------------------------------
# 数据存储端口不应暴露给局域网
# ---------------------------------------------------------------------------
# Kafka 是 PLAINTEXT 且消息里带密钥材料，MySQL 用的是仓库内口令 —— 两者都只该绑回环。
function Test-LoopbackOnly {
    param([string]$Container, [string]$Port)

    $mapping = docker port $Container 2>$null | Select-String -Pattern ":$Port$"
    if (-not $mapping) {
        Write-Host "[SKIP] $Container 未发布 $Port（可能未启动）"
        return
    }
    if ($mapping -match '127\.0\.0\.1') {
        Write-Host "[OK] $Container $Port 仅绑定回环"
        return
    }
    throw "$Container 的 $Port 绑定在非回环地址上：$mapping。该端口不应暴露给局域网。"
}

Test-LoopbackOnly -Container "kms_mysql" -Port "3307"
Test-LoopbackOnly -Container "kms_kafka" -Port "9092"
Test-LoopbackOnly -Container "kms_redis" -Port "6379"

# P5：旧分发服务**不应发布任何端口**（它已无消费方）。
# `Test-LoopbackOnly` 只管"有没有绑到非回环"，而这里的期望更强：
# 根本不该有端口映射。用一个独立的断言表达，避免日后有人"顺手"把它发布回来。
function Test-NoPublishedPort {
    param([string]$Container)

    $mapping = docker port $Container 2>$null
    if ([string]::IsNullOrWhiteSpace($mapping)) {
        Write-Host "[OK] $Container 未发布任何端口"
        return
    }
    throw "$Container 本不该发布端口（P5 后它已无消费方），但实际发布了：$mapping"
}

# kms_distribute_java 已整体下线（Q11），不再有容器可断言。
# 保留 Test-NoPublishedPort 函数本身：日后若重新引入任何''无消费方''的服务，
# 它仍是一个现成的、比 Test-LoopbackOnly 更强的判据。

function Test-HttpEndpoint {
    param(
        [string]$Name,
        [string]$Url
    )

    try {
        $response = Invoke-WebRequest -UseBasicParsing $Url -TimeoutSec 10
        Write-Host "[OK] $Name -> $($response.StatusCode) $Url"
    }
    catch {
        Write-Host "[FAIL] $Name -> $Url"
        throw
    }
}

function Test-MySqlTable {
    param(
        [string]$TableName,
        # 默认查 `kms`（主 KMS 库）。分发模块的表在 `falcon_kds`，必须显式指定 ——
        # 否则会给出一句"表不存在"，而表其实好好的，只是查错了库。
        [string]$Database = "kms"
    )

    $result = docker exec kms_mysql mysql -N -uroot -p"$MySqlPassword" -D $Database -e "SHOW TABLES LIKE '$TableName';"
    if ($result -match "^$TableName$") {
        Write-Host "[OK] MySQL table exists -> $Database.$TableName"
        return
    }

    throw "MySQL table missing: $Database.$TableName"
}

Write-Host "== Docker Compose Status =="
docker compose ps

# 注意：统一使用 127.0.0.1 而非 localhost。
# 在启用了 IPv6 的 Windows 上，localhost 会优先解析到 ::1，
# 而 Docker Desktop 的端口转发在此环境下只绑定 IPv4，导致请求超时。
Write-Host "`n== Gateway Checks =="
Test-HttpEndpoint -Name "gateway /ping"        -Url "http://127.0.0.1:80/ping"
Test-HttpEndpoint -Name "gateway portal /"     -Url "http://127.0.0.1:80/"
Test-HttpEndpoint -Name "gateway /user/"       -Url "http://127.0.0.1:80/user/"
Test-HttpEndpoint -Name "gateway /updatedel/"  -Url "http://127.0.0.1:80/updatedel/"
Test-HttpEndpoint -Name "gateway /distribute/" -Url "http://127.0.0.1:80/distribute/"
Test-HttpEndpoint -Name "gateway /acceptance/" -Url "http://127.0.0.1:80/acceptance/"

Write-Host "`n== Ingress Layer (Go) =="
Test-HttpEndpoint -Name "generate-go ping"  -Url "http://127.0.0.1:8081/generate/ping"
Test-HttpEndpoint -Name "updatedel-go ping" -Url "http://127.0.0.1:8082/lifecycle/ping"

Write-Host "`n== Business Layer (Java) =="
Test-HttpEndpoint -Name "generate-java ping"  -Url "http://127.0.0.1:9081/generate/ping"
Test-HttpEndpoint -Name "updatedel-java ping" -Url "http://127.0.0.1:9082/lifecycle/ping"

Write-Host "`n== Proxy via Gateway =="
Test-HttpEndpoint -Name "generate-api proxy"  -Url "http://127.0.0.1:80/generate-api/generate/ping"
Test-HttpEndpoint -Name "lifecycle-api proxy" -Url "http://127.0.0.1:80/lifecycle-api/lifecycle/ping"
Test-HttpEndpoint -Name "acceptance-api"      -Url "http://127.0.0.1:80/acceptance-api/health"

Write-Host "`n== Database Checks =="
Test-MySqlTable -TableName "sys_user"
Test-MySqlTable -TableName "keymanage"
Test-MySqlTable -TableName "key_operation_record"
Test-MySqlTable -TableName "permission_request"
# P5：`key_distribute_record` 已被新链路取代（批次表 + 用户信封表），
# 这里随之改为检查新表 —— 否则旧表删掉之后，健康检查会在一个**已经不存在**的
# 对象上报错，而真正该盯的两张表反而没人看。
Test-MySqlTable -TableName "dvadmin_pqkds_distribution_batches" -Database "falcon_kds"
Test-MySqlTable -TableName "dvadmin_pqkds_user_key_envelopes" -Database "falcon_kds"
Test-MySqlTable -TableName "dvadmin_pqkds_user_node_authorizations" -Database "falcon_kds"
# 节点多级授权（任务书指标）：节点发起申请 → 管理员审批。不登记的话，
# 迁移没跑成功时健康检查是绿的，而「申请授权」会在页面上直接报错。
Test-MySqlTable -TableName "dvadmin_pqkds_node_authorization_requests" -Database "falcon_kds"

Write-Host "`nAll checks passed."
}
finally {
    Pop-Location
}
