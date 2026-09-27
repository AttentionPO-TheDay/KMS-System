# =============================================================================
# ship-source.ps1 —— 生成「源码模式」部署包（远端自行构建镜像）
# -----------------------------------------------------------------------------
# 与 ship.ps1 的区别：
#   ship.ps1        自包含镜像模式：本地 docker save 出 kms-images.tar，远端只 load
#   ship-source.ps1 源码模式：只传**构建输入**，远端 docker compose build
#
# 什么时候用这个：
#   * 远端能联网（基础镜像 mysql/redis/kafka/ubuntu/temurin 可以直接拉）；
#   * 不想传 1.3GB 的镜像 tar；或镜像 tar 与本机架构不同（远端是 arm64 时镜像模式直接不可用，
#     而源码模式在远端构建，架构天然匹配）。
#
# 关键点：**镜像里 COPY 的东西不是源码，而是本地构建产物**（runtime/、front/），
# 而且它们被 .gitignore 排除。所以"只传源码"必定构建失败 —— 本脚本把它们一起打包。
#
# 产出（默认 kms-ops/dist/）：
#   kms-source-deploy.tar.gz   约 400MB，解包后目录结构与本地一致
#   MANIFEST.txt               内容清单 + 远端步骤 + 端口/凭据注意事项
#
# 用法：pwsh -File kms-ops\ship-source.ps1
# =============================================================================
[CmdletBinding()]
param(
    [string]$OutDir = (Join-Path $PSScriptRoot 'dist'),
    # 连公共基础镜像一起导出。
    # 远端拉不到 Docker Hub（构建时报 "failed to resolve source metadata for
    # docker.io/library/nginx:alpine ... i/o timeout"）时必须带上这个开关：
    # 这 7 个镜像不是本地构建的，包里没有它们就构建不起来。
    [switch]$WithBaseImages
)

$ErrorActionPreference = 'Stop'

# 远端构建/运行需要的**全部**公共基础镜像。
#
# 这份清单必须同时看两处，只统计一处必漏：
#   * build/*.Dockerfile 与 Django Dockerfile 的 `FROM`
#   * compose 里没有 build 段、直接写 `image:` 的服务（mysql/redis/kafka/ubuntu/console）
# 我第一次只统计了 compose，漏掉 nginx:alpine 与 debian:bookworm-slim，
# 而它们恰好是最先报错的两个。
$baseImages = @(
    'debian:bookworm-slim',      # acceptance / generate-go / updatedel-go / django 的 FROM
    'eclipse-temurin:8-jre',     # generate-java / updatedel-java 的 FROM，兼 fisco-console 运行
    'nginx:alpine',              # 网关镜像的 FROM
    'mysql:8.0',
    'redis:6.2',
    'apache/kafka:latest',
    'ubuntu:22.04'               # 4 个 FISCO 节点容器
)

function Step($m) { Write-Host "`n=== $m ===" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "  [OK] $m" -ForegroundColor Green }
function Warn2($m){ Write-Host "  [!] $m" -ForegroundColor Yellow }

$repo = Split-Path -Parent $PSScriptRoot          # 仓库根
$distContextRel = 'kms-distribute/extracted/ruoyi (2)'
$distContext = Join-Path $repo $distContextRel

Step '0. 前置检查'
if (-not (Test-Path (Join-Path $PSScriptRoot 'docker-compose.yml'))) { throw '找不到 kms-ops/docker-compose.yml' }
if (-not (Test-Path $distContext)) { throw "找不到 Django 构建上下文: $distContext" }
Ok "仓库根: $repo"

# ---------------------------------------------------------------------------
Step '1. 组装待上传目录树'
# ---------------------------------------------------------------------------
$staging = Join-Path $OutDir '_stage_src'
if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
New-Item -ItemType Directory -Force -Path $staging | Out-Null

# --- kms-ops/：整包带走，但剔除运行态数据与本机排障残留 -------------------
$opsStage = Join-Path $staging 'kms-ops'
New-Item -ItemType Directory -Force -Path $opsStage | Out-Null

# 目录级排除（相对 kms-ops）
$excludeDirs = @(
    'dist',                  # 本脚本自己的产物
    'experiments',           # 本地实验（含 .venv，极大）
    '.omc',                  # 本地代理状态
    'mysql\data',            # 运行态：远端首次启动自动初始化
    'redis\data',
    'kafka\kafka_data',
    'nginx\logs',
    'dvadmin-logs',
    'fisco\.rebuild',        # 本地重建链的原始产物
    'fisco\cert',            # CA 私钥：只留本机，不该上服务器
    'tests\_probe_out'       # 本地编译的探针 class
)
# 文件级排除
$excludeFiles = @(
    'docker-compose.yml.bak-preimage',
    'docker-compose-before.yml',
    '.env.bak-fisco',
    'menus.txt'
)

$robocopyArgs = @($PSScriptRoot, $opsStage, '/E', '/NFL', '/NDL', '/NJH', '/NJS', '/NP', '/R:1', '/W:1')
$robocopyArgs += '/XD'
foreach ($d in $excludeDirs) { $robocopyArgs += (Join-Path $PSScriptRoot $d) }
$robocopyArgs += '/XF'
foreach ($f in $excludeFiles) { $robocopyArgs += $f }
$robocopyArgs += '/XF'
$robocopyArgs += '*.bak.*'   # 含 nodes/ 下历次排障留下的旧链现场
$robocopyArgs += '/XF'
$robocopyArgs += '.last-backup.txt'

$null = & robocopy @robocopyArgs
if ($LASTEXITCODE -ge 8) { throw "robocopy 失败，退出码 $LASTEXITCODE" }
Ok "kms-ops/ 已组装"

# 旧链现场（目录名形如 127.0.0.1.bak.xxx / .broken.xxx）robocopy 的 /XF 管不到目录，
# 单独清一遍 —— 实测这两个目录合计 194MB，且与部署无关。
$nodesStage = Join-Path $opsStage 'nodes'
if (Test-Path $nodesStage) {
    Get-ChildItem $nodesStage -Force |
        Where-Object { $_.PSIsContainer -and $_.Name -match '\.bak\.|\.broken\.' } |
        ForEach-Object {
            $mb = [math]::Round(((Get-ChildItem $_.FullName -Recurse -File -ErrorAction SilentlyContinue |
                    Measure-Object Length -Sum).Sum / 1MB), 1)
            Remove-Item $_.FullName -Recurse -Force
            Warn2 "剔除旧链现场 nodes/$($_.Name)  ($mb MB)"
        }
}

# --- Django 构建上下文：只带 Dockerfile 真正 COPY 的那几项 ----------------
# 该目录整包 553MB，其中 web/ 占 543MB，而 Dockerfile 只 COPY requirements.txt 与 ./backend/。
# 远端构建不需要 web/，因此这里刻意不带 —— FTP 场景下这是最大的一笔浪费。
$distStage = Join-Path $staging 'kms-distribute\extracted\ruoyi (2)'
New-Item -ItemType Directory -Force -Path $distStage | Out-Null
foreach ($it in @('backend', 'requirements.txt', 'docker_env')) {
    $src = Join-Path $distContext $it
    if (-not (Test-Path $src)) { Warn2 "Django 上下文缺少 $it（构建会失败）"; continue }
    Copy-Item $src (Join-Path $distStage $it) -Recurse -Force
    Ok "Django 上下文: $it"
}

# ---------------------------------------------------------------------------
Step '2. 自检：镜像构建与运行所需的文件是否都在包里'
# ---------------------------------------------------------------------------
# 判据必须来自 Dockerfile 与 compose 本身，而不是我手写的清单 ——
# 手写清单会在别人改了 Dockerfile 之后悄悄失效。
$missing = @()

# 2a. Dockerfile 的 COPY 源
foreach ($df in (Get-ChildItem (Join-Path $opsStage 'build') -Filter *.Dockerfile -ErrorAction SilentlyContinue)) {
    foreach ($line in (Select-String -Path $df.FullName -Pattern '^COPY\s+(\S+)' -AllMatches)) {
        $rel = ($line.Line -replace '^COPY\s+', '') -split '\s+' | Select-Object -First 1
        if ($rel -eq 'requirements.txt') {
            if (-not (Test-Path (Join-Path $distStage 'requirements.txt'))) { $missing += "Django: requirements.txt" }
            continue
        }
        if ($rel -like './backend/*' -or $rel -like './backend/') {
            if (-not (Test-Path (Join-Path $distStage 'backend'))) { $missing += "Django: backend/" }
            continue
        }
        $p = Join-Path $opsStage ($rel -replace '/', '\')
        if (-not (Test-Path $p)) { $missing += "$($df.Name): $rel" }
    }
}

# 2b. compose 的 bind 挂载源（相对 kms-ops，且不越界）
#
# 例外：下面这些是**运行态数据目录**，包内有意不带 ——
# Docker 在容器首次启动时会自动创建缺失的 bind 挂载源目录，
# 而带上它们反而会把本机的库/队列数据一起搬过去（那是我们不想要的）。
$runtimeAutoCreated = @('mysql/data', 'redis/data', 'kafka/kafka_data', 'nginx/logs', 'dvadmin-logs')
$composeLines = Get-Content (Join-Path $opsStage 'docker-compose.yml')
foreach ($line in $composeLines) {
    if ($line -match '^\s+-\s+(\./[^:]+):') {
        $rel = $Matches[1].TrimStart('.', '/') -replace '/', '\'
        if ($runtimeAutoCreated -contains ($rel -replace '\\', '/')) { continue }
        $p = Join-Path $opsStage $rel
        if (-not (Test-Path $p)) { $missing += "mount: $($Matches[1])" }
    }
}
Ok "运行态目录不在包内（Docker 首次启动自动创建）: $($runtimeAutoCreated -join ', ')"

# 2c. 运行时必需的关键文件（配置与密钥材料）
foreach ($rel in @('.env', 'nginx\nginx.conf', 'mysql\init', 'mysql\my.cnf',
                   'fisco\console\conf\ca.crt', 'fisco\console\conf\sdk.crt', 'fisco\console\conf\sdk.key',
                   'nodes\127.0.0.1\fisco-bcos', 'nodes\127.0.0.1\node0\conf\group.1.genesis')) {
    if (-not (Test-Path (Join-Path $opsStage $rel))) { $missing += "必需: $rel" }
}

if ($missing.Count) {
    $missing | Sort-Object -Unique | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
    throw "自检失败：包内缺少 $($missing.Count) 项构建/运行输入（见上）"
}
Ok '自检通过：Dockerfile COPY 源、bind 挂载、运行态配置齐备'

# ---------------------------------------------------------------------------
Step '3. 打包'
# ---------------------------------------------------------------------------
$deployTar = Join-Path $OutDir 'kms-source-deploy.tar.gz'
if (Test-Path $deployTar) { Remove-Item $deployTar -Force }
Push-Location $staging
try {
    tar -czf $deployTar 'kms-ops' 'kms-distribute'
    if ($LASTEXITCODE -ne 0) { throw 'tar 打包失败' }
} finally { Pop-Location }

$mb = [math]::Round((Get-Item $deployTar).Length / 1MB, 1)
Ok "kms-source-deploy.tar.gz ($mb MB)"

# ---------------------------------------------------------------------------
Step '3b. 公共基础镜像（远端拉不到 Docker Hub 时需要）'
# ---------------------------------------------------------------------------
$baseTar = Join-Path $OutDir 'kms-base-images.tar'
if ($WithBaseImages) {
    foreach ($bi in $baseImages) {
        if (-not (docker images -q $bi 2>$null)) {
            Warn2 "本机没有 $bi，尝试拉取…"
            docker pull $bi
            if ($LASTEXITCODE -ne 0) { throw "拉取失败: $bi（本机也拉不到，换一台能拉的机器执行）" }
        }
    }
    if (Test-Path $baseTar) { Remove-Item $baseTar -Force }
    docker save -o $baseTar @baseImages
    if ($LASTEXITCODE -ne 0) { throw 'docker save（基础镜像）失败' }
    Ok "kms-base-images.tar ($([math]::Round((Get-Item $baseTar).Length/1MB,1)) MB) —— 远端 docker load -i 后即可离线构建"
}

# ---------------------------------------------------------------------------
Step '4. 从最终 tar 里复核（不信任打包过程）'
# ---------------------------------------------------------------------------
$list = @(tar -tzf $deployTar)
$checks = @{
    'kms-ops/docker-compose.yml'          = '部署编排'
    'kms-ops/build/nginx.Dockerfile'      = 'Dockerfile（⚠️ 曾被 .gitignore 排除）'
    'kms-ops/runtime/updatedel-java/kms-updatedel.jar' = 'Java 产物（构建输入）'
    'kms-ops/front/updatedel/index.html'   = '前端产物（构建输入）'
    'kms-ops/.env'                        = '运行配置与凭据'
    'kms-ops/nodes/127.0.0.1/fisco-bcos'  = 'FISCO 链'
    'kms-ops/fisco/console/conf/sdk.key'  = 'SDK 证书（打进 Java 镜像 + console 挂载）'
    'kms-ops/mysql/init/29_distribution_native_pages.sql' = '建库脚本（含菜单迁移）'
    'kms-distribute/extracted/ruoyi (2)/backend/start.sh' = 'Django 上下文'
}
$bad = @()
foreach ($k in $checks.Keys) {
    $hit = $list | Where-Object { $_ -eq "./$k" -or $_ -eq $k }
    if (-not $hit) { $bad += "$k  （$($checks[$k])）" }
}
if ($bad.Count) {
    $bad | ForEach-Object { Write-Host "    缺失: $_" -ForegroundColor Red }
    throw '最终产物复核失败'
}
Ok "最终产物复核通过（$($checks.Count) 项关键输入均在包内，共 $($list.Count) 个条目）"

# ---------------------------------------------------------------------------
Step '5. MANIFEST.txt'
# ---------------------------------------------------------------------------
$manifest = @()
$manifest += 'KMS 部署包清单（源码模式：远端自行构建镜像）'
$manifest += "生成时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$manifest += "包大小:   $mb MB（$($list.Count) 个条目）"
$manifest += ''
$manifest += '【上传】'
$manifest += '  只需上传这一个文件（FTP 传上万个小文件既慢又容易漏）。'
$manifest += ''
$manifest += '【远端步骤】'
$manifest += '  1) 解包（保持目录结构，注意路径里有空格与括号，要加引号）:'
$manifest += '       tar -xzf kms-source-deploy.tar.gz -C /opt/kms'
$manifest += '  2) cd "/opt/kms/kms-ops"'
$manifest += '  3) 按需修改 .env（见下方凭据）'
$manifest += '  4) bash deploy.sh check      # 部署前检查：输入文件 / 环境变量 / 架构 / 端口'
$manifest += '  5) bash deploy.sh build      # 构建 7 个应用镜像（基础镜像自动拉取）'
$manifest += '  6) bash deploy.sh up         # 启动'
$manifest += '  7) bash deploy.sh verify     # HTTP 健康检查'
$manifest += ''
$manifest += '  也可以直接: docker compose up -d --build（第 5、6 步合一）'
$manifest += ''
$manifest += '【为什么不能只传源码】'
$manifest += '  镜像里 COPY 的是**本地构建产物**，不是源码：'
$manifest += '    kms-ops/runtime/   Java jar 与 Go 二进制（由 build-local.ps1 产出）'
$manifest += '    kms-ops/front/     4 个前端产物（同上）'
$manifest += '    kms-ops/build/     6 个 Dockerfile —— ⚠️ 长期被 .gitignore 的通用 `build/` 规则排除，'
$manifest += '                       从未进入版本库；用 git 方式部署必然构建失败（已修）'
$manifest += '  本包已把它们全部带上，因此远端不需要 JDK / Maven / Node / Go。'
$manifest += ''
$manifest += '【包内不含（有意）】'
$manifest += '  - 运行态数据：mysql/data、redis/data、kafka/kafka_data、nginx/logs、dvadmin-logs'
$manifest += '    → 远端首次启动自动初始化（MySQL 建库脚本在 mysql/init/）'
$manifest += '  - 旧链现场：nodes/*.bak.*、nodes/*.broken.*（合计约 194MB，与部署无关）'
$manifest += '  - CA 私钥：fisco/cert/（只应留在本机）'
$manifest += '  - Django 的 web/（543MB）：该镜像只 COPY requirements.txt 与 ./backend/'
$manifest += '  - 本地实验与缓存：experiments/、tests/_probe_out、dist/'
$manifest += ''
$manifest += '【远端要求】'
$manifest += '  - linux/amd64 或 arm64 均可（源码模式在远端构建，架构天然匹配）'
$manifest += '  - 已装 docker 与 docker compose 插件；能访问镜像仓库与 pypi/apt 源'
$manifest += '    （Django 镜像构建期会 apt-get 与 pip install）'
$manifest += '  - 端口空闲：80(网关) 3307(MySQL) 6379(Redis) 9092(Kafka) 8001(PQKDS)'
$manifest += '    8081/8082(Go) 9081/9082(Java) 8545~8548(链 RPC) 20200~20203(链 channel)'
$manifest += ''
$manifest += '【构建需要 7 个公共基础镜像（远端拉不到 Docker Hub 时最常卡在这）】'
foreach ($bi in $baseImages) { $manifest += "      $bi" }
$manifest += '  若远端报 "failed to resolve source metadata for docker.io/library/nginx:alpine … i/o timeout"，'
$manifest += '  说明 Docker Hub 不可达，两条修法：'
$manifest += '    A) 配镜像加速器（远端）: /etc/docker/daemon.json 加 {"registry-mirrors":["https://<你的加速器>"]}'
$manifest += '       然后 systemctl restart docker；用 docker pull nginx:alpine 验证'
$manifest += '    B) 从本机带过去: 本机 pwsh -File ship-source.ps1 -WithBaseImages '
$manifest += '       → 上传 kms-base-images.tar → 远端 docker load -i kms-base-images.tar'
$manifest += '  注意：即使镜像已就绪，Dockerfile 里的 apt-get / apk add / pip install 仍需'
$manifest += '        对应的包源可达（Django 镜像已内置阿里云 pypi 源）。'
$manifest += ''
$manifest += '【上线前必须处理】'
$manifest += '  - .env 内为开发占位口令，必须轮换：MYSQL_ROOT_PASSWORD / KMS_TOKEN_SECRET /'
$manifest += '    INTERNAL_TOKEN / DRUID_LOGIN_USERNAME / DRUID_LOGIN_PASSWORD / KGC_MASTER_SECRET'
$manifest += '  - **不要**改动 FISCO_CONTRACT_ADDRESS 与 FISCO_PRIVATE_KEY：'
$manifest += '    它们与包内这条链上已部署的 KeyEvidence 合约绑定，改了上链就会失败。'
$manifest += '  - KMS_CAPTCHA_ENABLED=true 表示登录需要图形验证码（当前值）。'
Set-Content -Path (Join-Path $OutDir 'MANIFEST-source.txt') -Value ($manifest -join "`n") -Encoding utf8
Ok 'MANIFEST-source.txt 已生成'

Remove-Item $staging -Recurse -Force
Write-Host "`n完成。产物目录: $OutDir" -ForegroundColor Green
Get-ChildItem $OutDir -File | ForEach-Object { Write-Host ("  {0,-28} {1,8:N1} MB" -f $_.Name, ($_.Length / 1MB)) }