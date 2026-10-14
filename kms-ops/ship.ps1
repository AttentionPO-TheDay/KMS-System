# =============================================================================
#requires -Version 7.0
# ship.ps1 —— 生成远端部署包（自包含镜像模式）
# -----------------------------------------------------------------------------
# 用途：把「直接可运行的镜像」+「必需的配置与数据目录」打成两个文件，
#       传到远端后无需网络、无需构建即可启动。
#
# 产出（默认在 kms-ops/dist/ 下）：
#   kms-images.tar        默认 8 个应用镜像（含 DID，docker save 自包含镜像）
#   kms-deploy.tar.gz     部署包：compose（已剥离 build 段）、.env、配置与数据目录
#   MANIFEST.txt          内容清单与校验信息
#
# 远端步骤见 deploy.sh。
#
# 设计说明：
#   - 镜像模式为「自包含」：代码在构建期打入镜像，因此远端**不需要**
#     runtime/、front/ 等构建输入，部署包可显著瘦身。
#   - 但 mysql/init（建库脚本）、nodes（仅链启动配置）、fisco/console（运维容器）、
#     nginx/nginx.conf 仍必须在远端存在，这些是数据与配置，不属于代码。
#   - 运行时状态目录（mysql/data、kafka/kafka_data、redis/data、nginx/logs）
#     刻意**不打包**，让远端从干净状态初始化，避免带入本地数据。
# =============================================================================

[CmdletBinding()]
param(
    [string]$OutDir = (Join-Path $PSScriptRoot 'dist'),
    # 跳过 docker save（镜像另行传输时使用），只生成部署包
    [switch]$SkipImages,
    # 连公共基础镜像一起导出（mysql / redis / kafka / ubuntu / temurin）。
    # 远端**不能联网拉镜像**时必须带上这个开关，否则 compose 起不来：
    # 这 5 个镜像不是本地构建的，不导出就没有。
    [switch]$WithBaseImages,
    # 默认完整包含 DID，但不复制 SDK 凭据、不自动开启链写入。
    [switch]$WithoutDid,
    # 从当前源码重新生成运行产物并构建镜像；不会启动/重建本机容器。
    [switch]$Rebuild,
    # 仅本次前端构建使用该 Node/npm，不修改全局 NVM 版本。
    [string]$NodeHome
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Write-Step([string]$msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Write-Ok([string]$msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn2([string]$msg){ Write-Host "  [!] $msg" -ForegroundColor Yellow }

$root = $PSScriptRoot
$OutDir = [System.IO.Path]::GetFullPath($OutDir)
if ($OutDir.TrimEnd('\', '/') -eq $root.TrimEnd('\', '/')) { throw 'OutDir 不能是 kms-ops 源目录' }
function Remove-PackageDirectory([string]$Path) {
    $target = [System.IO.Path]::GetFullPath($Path)
    $prefix = $OutDir.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
    if (-not $target.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw '拒绝删除输出目录外的路径'
    }
    if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
}
$composePath = Join-Path $root 'docker-compose.yml'

$composeArgs = @('-f', $composePath)
if (-not $WithoutDid) { $composeArgs += @('-f', (Join-Path $root 'docker-compose.fabric-did.yml')) }
if ($Rebuild -and $SkipImages) { throw '-Rebuild 不能与 -SkipImages 同时使用' }
if ($Rebuild) {
    & (Join-Path $root 'build-local.ps1') -WithoutDid:$WithoutDid -NodeHome $NodeHome
    if ($WithoutDid) { docker compose @composeArgs build }
    else { docker compose @composeArgs --profile fabric-did build }
    if ($LASTEXITCODE -ne 0) { throw '从当前源码构建镜像失败，停止打包' }
} else {
    Write-Warn2 '未使用 -Rebuild：只导出现有镜像；请确认它们已从最新代码构建。'
}
$composeArgs += @('-f', (Join-Path $root 'docker-compose.fresh-deploy.yml'))

if (-not (Test-Path $composePath)) { throw "找不到 docker-compose.yml: $composePath" }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

# ---------------------------------------------------------------------------
# 1. 生成「远端版 compose」：剥离 build: 段，只保留 image:
# ---------------------------------------------------------------------------
Write-Step '生成远端版 compose（剥离 build 段）'

# build 段形如：
#     build:
#       context: .
#       dockerfile: build/xxx.Dockerfile
# 需要连同其下缩进的子行一起删除。
$lines = @(docker compose @composeArgs config --no-interpolate --no-path-resolution)
if ($LASTEXITCODE -ne 0) { throw '合并远端 compose 失败' }
$out = New-Object System.Collections.Generic.List[string]
$i = 0
$removed = 0
while ($i -lt $lines.Count) {
    $line = $lines[$i]
    if ($line -match '^(\s+)build:\s*$') {
        $indent = $Matches[1].Length
        $removed++
        $i++
        # 跳过比 build 更深缩进的子行
        while ($i -lt $lines.Count) {
            $l = $lines[$i]
            if ($l.Trim() -eq '') { $i++; continue }
            $lead = $l.Length - $l.TrimStart().Length
            if ($lead -gt $indent) { $i++; continue }
            break
        }
        continue
    }
    $out.Add($line)
    $i++
}

$remoteCompose = Join-Path $OutDir 'docker-compose.yml'
Set-Content -Path $remoteCompose -Value ($out -join "`n") -Encoding utf8
Write-Ok "已剥离 $removed 处 build 段 → $remoteCompose"

# 剥离结果自检：远端 compose 中不得残留 build 指令，
# 也不得出现逃出部署目录的相对路径（../），否则包无法独立运行。
$stripped = Get-Content $remoteCompose -Raw
$leftBuild = Select-String -Path $remoteCompose -Pattern '^\s+build:\s*$|^\s+dockerfile:'
if ($leftBuild) {
    $leftBuild | ForEach-Object { Write-Host "    L$($_.LineNumber): $($_.Line.Trim())" -ForegroundColor Red }
    throw '剥离后仍残留 build 段'
}
$escape = Select-String -Path $remoteCompose -Pattern '^\s+(?:-\s+|source:\s+)\.\./|^\s+source:\s+(?:[A-Za-z]:|/[^/])'
if ($escape) {
    $escape | ForEach-Object { Write-Host "    L$($_.LineNumber): $($_.Line.Trim())" -ForegroundColor Red }
    throw '存在逃出部署目录的挂载路径（../），远端将无法解析'
}
Write-Ok '剥离结果自检通过（无 build 残留、无越界路径）'

# compose 插值需要 .env（其中的 ${VAR:?...} 在缺失时会直接报错），
# 因此先把 .env 放到产物目录，再校验剥离结果。
$envSrc = Join-Path $root '.env'
if (-not (Test-Path $envSrc)) { throw "找不到 .env: $envSrc" }
Copy-Item $envSrc (Join-Path $OutDir '.env') -Force
# 只修改输出副本；不迁移旧链合约/账户引用，不影响本机配置。
$remoteEnv = Join-Path $OutDir '.env'
$envLines = Get-Content $remoteEnv | ForEach-Object {
    if ($_ -match '^(FISCO_CONTRACT_ADDRESS|FISCO_PRIVATE_KEY)=') { "$($Matches[1])=" }
    elseif ($_ -match '^FABRIC_DID_ENABLED=') { 'FABRIC_DID_ENABLED=false' }
    else { $_ }
}
Set-Content $remoteEnv -Value $envLines -Encoding utf8

Push-Location $OutDir
try {
    $cfgErr = docker compose -f $remoteCompose config --quiet 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host ($cfgErr | Out-String) -ForegroundColor Red
        throw '剥离后 compose 解析失败'
    }
    Write-Ok '剥离后 compose 解析通过'
} finally { Pop-Location }

# ---------------------------------------------------------------------------
# 2. docker save 全部应用镜像
# ---------------------------------------------------------------------------
$images = @(
    'kms-generate-go:local',
    'kms-generate-java:local',
    'kms-updatedel-go:local',
    'kms-updatedel-java:local',
    # `kms-distribute-java:local` 已移除（Q11：旧分发服务整体下线）—— 应用镜像 8 → 7
    'kms-acceptance-backend:local',
    'kms-gateway-nginx:local',
    'kms-dvadmin3-django:local'
)
if (-not $WithoutDid) { $images += 'kms-fabric-did:local' }

$tarPath = Join-Path $OutDir 'kms-images.tar'
if (-not $SkipImages) {
    Write-Step '导出应用镜像（docker save）'
    foreach ($img in $images) {
        $exist = docker images -q $img 2>$null
        if (-not $exist) { throw "镜像不存在，请先执行 docker compose build：$img" }
    }
    if (Test-Path $tarPath) { Remove-Item $tarPath -Force }
    docker save -o $tarPath @images
    if ($LASTEXITCODE -ne 0) { throw 'docker save 失败' }
    $mb = [math]::Round((Get-Item $tarPath).Length / 1MB, 1)
    Write-Ok "已导出 $($images.Count) 个镜像 → kms-images.tar ($mb MB)"
}

# ---------------------------------------------------------------------------
# 2b. 增量镜像包：只含网关镜像
# ---------------------------------------------------------------------------
# 4 个前端产物与 nginx.conf 全部打进 kms-gateway-nginx，因此「改前端 / 改网关配置」
# 这一类最常见的发版，实际只有这一个镜像变了。此时重传 1.28GB 的 kms-images.tar
# 纯属浪费——单独导出一个小包，供「远端已在运行、只需替换网关」的场景增量更新。
$deltaPath = Join-Path $OutDir 'kms-nginx-update.tar'
if (-not $SkipImages) {
    Write-Step '导出增量镜像包（仅网关）'
    if (Test-Path $deltaPath) { Remove-Item $deltaPath -Force }
    docker save -o $deltaPath 'kms-gateway-nginx:local'
    if ($LASTEXITCODE -ne 0) { throw 'docker save（增量）失败' }
    $nMb = [math]::Round((Get-Item $deltaPath).Length / 1MB, 1)
    Write-Ok "已导出 kms-gateway-nginx:local → kms-nginx-update.tar ($nMb MB)"
}

# ---------------------------------------------------------------------------
# 3. 打部署包（配置与数据目录）
# ---------------------------------------------------------------------------
Write-Step '打包部署包（配置与数据目录）'

# 需要随包提供的条目（不含运行时状态目录）
# 注意：
#   1. redis 无配置文件，其参数（--appendonly yes）写在 compose 的 command 中
#   2. **不要**把 docker-compose.yml 放进这个列表：该文件必须用前面生成的
#      「远端版」（已剥离 build 段），而本列表是从 $root 复制的，
#      若包含它会把远端版覆盖回源版（曾因此导致部署包仍带 build 段）。
#   3. **不要**把 front/ 加进来：前端产物是构建期打进 kms-gateway-nginx 镜像的，
#      本包（自包含镜像模式）不需要它们。其中 /generate/ 前端已退役，
#      连构建都不再做（见 kms-generate/front/RETIRED.md）。
$items = @(
    '.env',
    'mysql/init',
    'mysql/my.cnf',
    'nginx/nginx.conf',
    'nginx/demo-server.conf.template',
    'nginx/30-kms-demo.sh',
    'nginx/snippets',       # nginx.conf 里 include 的复用片段（安全头 / SPA 禁缓存）
    'portal',               # 手工编写的门户页（镜像里也有，保留一份便于改）
    'check.ps1'
)

$staging = Join-Path $OutDir '_stage'
Remove-PackageDirectory $staging
New-Item -ItemType Directory -Force -Path $staging | Out-Null

# 先放入「远端版 compose」（已剥离 build 段），必须早于复制循环
Copy-Item $remoteCompose (Join-Path $staging 'docker-compose.yml') -Force
Write-Ok '已加入远端版 compose（无 build 段）'

foreach ($it in $items) {
    $src = if ($it -eq '.env') { $remoteEnv } else { Join-Path $root $it }
    if (-not (Test-Path $src)) { throw "缺少必需部署文件: $it" }
    $dst = Join-Path $staging $it
    $dstParent = Split-Path $dst -Parent
    if (-not (Test-Path $dstParent)) { New-Item -ItemType Directory -Force -Path $dstParent | Out-Null }
    Copy-Item $src $dst -Recurse -Force
    Write-Ok "已加入: $it"
}

# Console 只带运行依赖及 SDK 配置；不带部署日志或本机账户私钥。
$consoleTarget = Join-Path $staging 'fisco/console'
New-Item -ItemType Directory -Force -Path $consoleTarget | Out-Null
foreach ($entry in @('conf', 'lib', 'apps', 'contracts', 'console.sh', 'start.sh', 'get_account.sh', 'get_gm_account.sh', 'sol2java.sh')) {
    $source = Join-Path $root "fisco/console/$entry"
    if (-not (Test-Path $source)) { throw "缺少 Console 运行配置: $entry" }
    Copy-Item $source $consoleTarget -Recurse -Force
}

# 白名单复制节点配置，绝不复制 node*/data、log、历史现场或数据库。
$nodeSource = Join-Path $root 'nodes/127.0.0.1'
$nodeTarget = Join-Path $staging 'nodes/127.0.0.1'
New-Item -ItemType Directory -Force -Path $nodeTarget | Out-Null
foreach ($entry in @('fisco-bcos', 'sdk', 'node0', 'node1', 'node2', 'node3')) {
    $source = Join-Path $nodeSource $entry
    if (-not (Test-Path $source)) { throw "缺少链初始化配置: $entry" }
    if ($entry -match '^node[0-3]$') {
        $destination = Join-Path $nodeTarget $entry
        New-Item -ItemType Directory -Force -Path $destination | Out-Null
        foreach ($part in @('config.ini', 'conf')) {
            $inputPath = Join-Path $source $part
            if (-not (Test-Path $inputPath)) { throw "缺少链初始化配置: $entry/$part" }
            Copy-Item $inputPath $destination -Recurse -Force
        }
    } else { Copy-Item $source $nodeTarget -Recurse -Force }
}

if (-not $WithoutDid) {
    $didDir = Join-Path $staging 'fabric-did-secrets'
    New-Item -ItemType Directory -Force -Path (Join-Path $didDir 'work') | Out-Null
    Copy-Item (Join-Path $root 'fabric-did-secrets/README.md') $didDir -Force
    Copy-Item (Join-Path $root '../kms-fabric-did/config/*.example') $didDir -Force
    Set-Content (Join-Path $staging 'WITH_DID') -Value 'DID included, disabled until configured; SysPid integration pending.' -Encoding utf8
}
Copy-Item (Join-Path $root 'SERVER_DEPLOY.md') $staging -Force

# 放入远端部署脚本
Copy-Item (Join-Path $root 'deploy.sh') $staging -Force
Copy-Item (Join-Path $root 'enable-node-fisco.py') $staging -Force
Copy-Item (Join-Path $root 'recover-node-fisco-hash.py') $staging -Force
Copy-Item (Join-Path $root 'check.ps1') $staging -Force -ErrorAction SilentlyContinue

# 空目录占位：这些目录由远端首次启动时自动创建，显式建出便于排查
foreach ($d in @('mysql/data','redis/data','kafka/kafka_data','nginx/logs','dvadmin-logs')) {
    $p = Join-Path $staging $d
    New-Item -ItemType Directory -Force -Path $p | Out-Null
    Set-Content -Path (Join-Path $p '.gitkeep') -Value '' -Encoding utf8
}

# ---------------------------------------------------------------------------
# 4. 打 tar.gz
# ---------------------------------------------------------------------------
$deployTar = Join-Path $OutDir 'kms-deploy.tar.gz'
if (Test-Path $deployTar) { Remove-Item $deployTar -Force }

Write-Step '生成 kms-deploy.tar.gz'
# Windows 自带的 tar 可正确处理 gzip
Push-Location $staging
try {
    tar -czf $deployTar .
    if ($LASTEXITCODE -ne 0) { throw 'tar 打包失败' }
} finally { Pop-Location }
Remove-PackageDirectory $staging

$dMb = [math]::Round((Get-Item $deployTar).Length / 1MB, 1)
Write-Ok "部署包: kms-deploy.tar.gz ($dMb MB)"

# ---------------------------------------------------------------------------
# 4b. 从**最终 tar 包**中实际校验 compose
# ---------------------------------------------------------------------------
# 这一步是必要的：此前出现过「脚本自检通过但包内文件是旧版」的问题
# （docker-compose.yml 被复制循环用源版覆盖）。直接从产物校验才能发现。
Write-Step '校验最终产物内的 compose'
$verifyDir = Join-Path $OutDir '_verify'
Remove-PackageDirectory $verifyDir
New-Item -ItemType Directory -Force -Path $verifyDir | Out-Null
Push-Location $verifyDir
try {
    tar -xzf $deployTar 'docker-compose.yml' 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw '从 tar 中提取 compose 失败' }
} finally { Pop-Location }

$inTar = Join-Path $verifyDir 'docker-compose.yml'
if (-not (Test-Path $inTar)) { throw 'tar 包内未找到 docker-compose.yml' }

$badBuild = Select-String -Path $inTar -Pattern '^\s+build:\s*$|^\s+dockerfile:'
if ($badBuild) {
    $badBuild | ForEach-Object { Write-Host "    L$($_.LineNumber): $($_.Line.Trim())" -ForegroundColor Red }
    throw '最终产物中的 compose 仍含 build 段'
}
$badPath = Select-String -Path $inTar -Pattern '^\s+(?:-\s+|source:\s+)\.\./|^\s+source:\s+(?:[A-Za-z]:|/[^/])'
if ($badPath) {
    $badPath | ForEach-Object { Write-Host "    L$($_.LineNumber): $($_.Line.Trim())" -ForegroundColor Red }
    throw '最终产物中的 compose 含越界挂载路径'
}
# 这里原来写死「应为 8」，而旧分发服务下线后只剩 7 个 —— 断言写死数字的结果是
# 脚本自己先挂掉，且报错说的是"镜像数不对"，看着像产物有问题。
# 改成"与导出清单比对"：compose 引用的 kms-* 镜像必须都在我们要 save 的列表里。
$refImages = Select-String -Path $inTar -Pattern '^\s+image:\s+(kms-[^\s]+)' -AllMatches |
    ForEach-Object { $_.Matches } | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique
$missingExport = @($refImages | Where-Object { $images -notcontains $_ })
if ($missingExport.Count) {
    throw "compose 引用了未导出的镜像: $($missingExport -join ', ')"
}
Write-Ok "最终产物校验通过（无 build 段、无越界路径、$(@($refImages).Count) 个不同应用镜像且全部在导出清单内）"
Remove-PackageDirectory $verifyDir

# ---------------------------------------------------------------------------
# 4c2. 公共基础镜像：远端拉不到就起不来，必须显式告知
# ---------------------------------------------------------------------------
$baseImages = @('mysql:8.0', 'redis:6.2', 'apache/kafka:latest', 'ubuntu:22.04', 'eclipse-temurin:8-jre')
$baseTar = Join-Path $OutDir 'kms-base-images.tar'
if ($WithBaseImages -and -not $SkipImages) {
    Write-Step '导出公共基础镜像（-WithBaseImages）'
    foreach ($b in $baseImages) {
        if (-not (docker images -q $b 2>$null)) {
            Write-Warn2 "本机没有 $b，直接 docker pull 后重跑"
            docker pull $b
            if ($LASTEXITCODE -ne 0) { throw "拉取失败: $b" }
        }
    }
    if (Test-Path $baseTar) { Remove-Item $baseTar -Force }
    docker save -o $baseTar @baseImages
    if ($LASTEXITCODE -ne 0) { throw 'docker save（基础镜像）失败' }
    Write-Ok "已导出基础镜像 → kms-base-images.tar ($([math]::Round((Get-Item $baseTar).Length/1MB,1)) MB)"
}

# ---------------------------------------------------------------------------
# 4c. 校验 nginx.conf 依赖的 snippet 确实在包里
# ---------------------------------------------------------------------------
# nginx.conf 从单文件改为 include nginx/snippets/*.conf 后，漏打包会让包内那份
# nginx.conf 变成残缺配置（直接挂载即启动失败）。与上面 compose 一样，必须从
# 最终 tar 里核对，而不是相信复制循环的结果。
$tarList = @(tar -tzf $deployTar)
if ($LASTEXITCODE -ne 0) { throw '读取最终部署包目录失败' }
$businessData = @($tarList | Where-Object { $_ -match 'nodes/[^/]+/node\d+/(data|log)/|fisco/console/(accounts?|log)/|deploylog\.txt|\.bak\.|\.broken\.' })
if ($businessData.Count) { throw '全新部署包混入了本地链数据、日志或备份' }
foreach ($required in @('SERVER_DEPLOY.md', 'deploy.sh', 'mysql/init/03.sql')) {
    if (-not ($tarList | Where-Object { $_ -eq "./$required" })) { throw "最终部署包缺少: $required" }
}
if (-not $WithoutDid) {
    foreach ($required in @('WITH_DID', 'fabric-did-secrets/README.md', 'fabric-did-secrets/fabric.config.properties.example', 'fabric-did-secrets/gm-sdk.properties.example')) {
        if (-not ($tarList | Where-Object { $_ -eq "./$required" })) { throw "最终部署包缺少 DID 条目: $required" }
    }
    $unexpectedSecrets = @($tarList | Where-Object { $_ -match '^\./fabric-did-secrets/.+\.(pem|key|crt)$|^\./fabric-did-secrets/(connection\.json|fabric\.config\.properties|gm-sdk\.properties)$' })
    if ($unexpectedSecrets.Count) { throw '部署包意外包含真实 DID 凭据' }
}
$confEntry = $tarList | Where-Object { $_ -match 'nginx/nginx\.conf$' } | Select-Object -First 1
if (-not $confEntry) { throw '包内未找到 nginx/nginx.conf' }
# 注意：tar 条目形如 ./nginx/nginx.conf，解包会还原出相对目录结构，
# 所以必须解到独立的临时目录再按条目名拼路径，不能假设解出来就叫 _nginx.conf。
$nxDir = Join-Path $OutDir '_nginxcheck'
Remove-PackageDirectory $nxDir
New-Item -ItemType Directory -Force -Path $nxDir | Out-Null
Push-Location $nxDir
try {
    tar -xzf $deployTar $confEntry 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "从 tar 中提取 $confEntry 失败" }
} finally { Pop-Location }

$inNginx = Join-Path $nxDir ($confEntry -replace '^\./', '')
if (-not (Test-Path $inNginx)) { throw "提取后未找到 nginx.conf（期望 $inNginx）" }
$need = Select-String -Path $inNginx -Pattern 'include\s+/etc/nginx/snippets/([A-Za-z0-9_.\-]+)' -AllMatches |
    ForEach-Object { $_.Matches } | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique
# Shared demo locations and generated proxy credentials are indirect includes.
$need = @($need) + @('kms-security-headers.conf', 'kms-spa-no-store.conf', 'kms-demo-locations.conf', 'kms-demo-proxy.conf.template') | Sort-Object -Unique
foreach ($f in @('demo-server.conf.template', '30-kms-demo.sh')) {
    if (-not ($tarList | Where-Object { $_ -match "nginx/$([regex]::Escape($f))$" })) { throw "包内缺少 Demo 网关配置: $f" }
}
Remove-PackageDirectory $nxDir

if (-not $need.Count) {
    Write-Warn2 '包内 nginx.conf 未 include 任何 snippet（若已改回单文件配置可忽略）'
} else {
    $missing = @()
    foreach ($s in $need) {
        if (-not ($tarList | Where-Object { $_ -match "nginx/snippets/$([regex]::Escape($s))$" })) { $missing += $s }
    }
    if ($missing.Count) { throw "包内 nginx.conf include 了缺失的 snippet: $($missing -join ', ')" }
    Write-Ok "最终产物校验通过（nginx snippets 齐全: $($need -join ', ')）"
}

# ---------------------------------------------------------------------------
# 5. 清单
# ---------------------------------------------------------------------------
Write-Step '生成 MANIFEST.txt'
$manifest = @()
$manifest += 'KMS 远端部署包清单'
$manifest += "生成时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$manifest += ''
$manifest += '【文件】'
# 按实际产物列出（而非按是否执行了本次 save），
# 避免用 -SkipImages 打包时清单漏报已存在的镜像文件。
if (Test-Path $tarPath) {
$manifest += "  kms-images.tar       $([math]::Round((Get-Item $tarPath).Length/1MB,1)) MB   $($images.Count) 个应用镜像（bash deploy.sh load 载入）"
} else {
    $manifest += '  kms-images.tar       （未生成：本次使用了 -SkipImages，请另行提供镜像）'
}
$manifest += "  kms-deploy.tar.gz    $dMb MB   配置、数据目录与部署脚本"
if (Test-Path $deltaPath) {
    $nMb2 = [math]::Round((Get-Item $deltaPath).Length / 1MB, 1)
    $manifest += "  kms-nginx-update.tar $nMb2 MB   增量包：仅 kms-gateway-nginx（前端 / 网关配置更新用）"
}
$manifest += ''
$manifest += '【增量更新】（远端已在运行，本次只改了前端产物或 nginx 配置）'
$manifest += '  前端与 nginx.conf 都打在 kms-gateway-nginx 镜像内，这类发版只有它变了，'
$manifest += '  因此不必重传 1.3GB 的 kms-images.tar：'
$manifest += '  1) 只上传 kms-nginx-update.tar 与 kms-deploy.tar.gz'
$manifest += '  2) docker load -i kms-nginx-update.tar'
$manifest += '  3) cd 部署目录 && tar -xzf kms-deploy.tar.gz'
$manifest += '  4) docker compose up -d --force-recreate nginx'
$manifest += '  5) 浏览器强制刷新一次（Ctrl+F5）：此前被浏览器缓存住的旧 index.html'
$manifest += '     不会自动失效，需手动清一次；此后 no-store 会让它每次回源。'
$manifest += ''
$manifest += '【镜像清单】'
foreach ($img in $images) {
    $manifest += "  $img"
    if (-not $SkipImages) {
        $identity = docker image inspect $img --format '{{.Id}} {{.Os}}/{{.Architecture}}'
        if ($LASTEXITCODE -ne 0) { throw "无法核对已导出镜像: $img" }
        $manifest += "    $identity"
        if ($identity -notmatch 'linux/amd64$') { throw "镜像架构不是本包要求的 linux/amd64: $img" }
    }
}
$manifest += ''
$manifest += '【远端部署步骤】'
$manifest += '  1) 上传两个文件到远端（例如 /opt/kms）:'
$manifest += '       scp kms-images.tar kms-deploy.tar.gz <user>@<host>:/opt/kms/'
$manifest += '  2) 解包:  cd /opt/kms && tar -xzf kms-deploy.tar.gz'
$manifest += '  3) 载入镜像:  bash deploy.sh load        # 约 1.3GB，需数分钟'
$manifest += '  4) 按需修改 .env（见下方注意事项）'
$manifest += '  5) 部署前检查:  bash deploy.sh check'
$manifest += '  6) 启动:  bash deploy.sh up'
$manifest += '  7) 健康检查:  bash deploy.sh verify'
$manifest += ''
$manifest += '【架构要求】'
$manifest += '  目标机必须为 linux/amd64（x86_64）。本包镜像全部由 amd64 构建，'
$manifest += '  ARM 主机无法运行。'
$manifest += ''
$manifest += '【注意事项】'
$manifest += '  - .env 内的口令为开发占位值，上线前必须轮换：'
$manifest += '      MYSQL_ROOT_PASSWORD / KMS_TOKEN_SECRET / INTERNAL_TOKEN / DRUID_LOGIN_*'
$manifest += '  - 全新部署：nodes/ 仅含二进制、节点配置及证书，不含本机链数据/日志。'
$manifest += '    输出 .env 已清空旧 FISCO 合约地址/账户私钥；远端 compose 默认暂停链写入。'
$manifest += '    新链需另行部署合约；DID/SysPid 参数确认前不提交任何交易。'
$manifest += '  - DID 默认包含镜像与内部服务，SDK 凭据不进包；参见 SERVER_DEPLOY.md。'
$manifest += '  - 运行时状态目录（mysql/data、kafka/kafka_data、redis/data、nginx/logs、'
$manifest += '    dvadmin-logs）刻意未打包，远端首次启动会自动初始化数据库与 Kafka。'
$manifest += '  - 基础 compose 已是单一 Demo 环境，无需 demo overlay；数据/项目不变。'
$manifest += '    原本地材料入口 http://127.0.0.1:8088/updatedel/demo 保持不变。'
$manifest += '    80/443/8443 与 localhost 入口只跳转到该地址，避免浏览器私钥按 origin 分裂。'
$manifest += '  - 80/443/8088/8443 网关全部只绑定回环，仅提供 Demo，不开放普通登录。'
$manifest += '    已有 .env 精确 Host/Origin 白名单须获授权核对；禁止通配/公网暴露。'
$manifest += '  - 端口占用：80/443/8088/8443(网关) 3307(MySQL) 6379(Redis) 9092(Kafka)'
$manifest += '    8545~8548(链 RPC) 20200~20203(链 channel)。Go/Java/PQKDS/验收仅容器内。'
$manifest += ''
$manifest += '【公共基础镜像：远端能不能联网，决定要不要带】'
$manifest += '  下列 5 个镜像**不是本地构建的**，kms-images.tar 里没有它们：'
foreach ($b in $baseImages) { $manifest += "      $b" }
if (Test-Path $baseTar) {
    $manifest += "  已随包导出：kms-base-images.tar（docker load -i kms-base-images.tar）"
} else {
    $manifest += '  本次**未**导出它们。若远端能访问镜像仓库，compose 会自动拉取；'
    $manifest += '  若远端不能联网（或拉取受限），请在本机重新执行：'
    $manifest += '      pwsh -File kms-ops\ship.ps1 -WithBaseImages'
    $manifest += '  并把多出来的 kms-base-images.tar 一并上传。'
}
Set-Content -Path (Join-Path $OutDir 'MANIFEST.txt') -Value ($manifest -join "`n") -Encoding utf8
if (-not $SkipImages) {
    $checksumFiles = @('kms-images.tar', 'kms-deploy.tar.gz', 'MANIFEST.txt')
    if ($WithBaseImages) { $checksumFiles += 'kms-base-images.tar' }
    $checksums = foreach ($file in $checksumFiles) {
        $hash = (Get-FileHash (Join-Path $OutDir $file) -Algorithm SHA256).Hash.ToLowerInvariant()
        "$hash  $file"
    }
    Set-Content (Join-Path $OutDir 'SHA256SUMS') -Value $checksums -Encoding utf8NoBOM
}
Write-Ok 'MANIFEST.txt 已生成'

Write-Host "`n完成。产物目录: $OutDir" -ForegroundColor Green
Get-ChildItem $OutDir -File | ForEach-Object {
    Write-Host ("  {0,-24} {1,8:N1} MB" -f $_.Name, ($_.Length / 1MB))
}
