# =============================================================================
# rebuild-fisco-chain.ps1 —— 重建 KMS 用的 4 节点 FISCO BCOS 链
# -----------------------------------------------------------------------------
# 为什么需要这个脚本（2026-09-24 的教训）
# --------------------------------------
# 上一轮的 4 节点链"进程活着、peer 全连、创世一致"，但 KMS 写不了链。
# 真因不是共识，而是**PKI 不是同一次 build 的产物**：
#   * 链在跑 CA = CN=chain(98:EB:D5:…)，节点身份证书由 CN=agency 签发；
#   * 而 fisco/console/conf 里那份 SDK 证书来自**旧单节点链**（CN=agency, OU=chain），
#     工作区里又没有那条链的 CA 私钥 —— 谁都签不出能被这条链接受的客户端证书；
#   * 于是任何 SDK 连接都在 TLS 握手阶段被拒（实测 ssl handshake failed），
#     而 KMS 只会把它记成 FISCO_NOT_READY，看起来像"链没出块"。
#
# 本脚本用官方 build_chain.sh 一次性生成 CA / agency / 节点 / SDK 四类材料，
# 保证它们出自同一条 PKI，并把 SDK 证书分发到 console 与 Java 后端要用的位置。
#
# 前置：WSL 里有 Ubuntu-22.04（build_chain.sh 需要 Linux + openssl）。
# 用法：pwsh -File kms-ops\scripts\rebuild-fisco-chain.ps1 [-Nodes 4] [-SkipBuild]
# =============================================================================
[CmdletBinding()]
param(
    [int]$Nodes = 4,
    [switch]$SkipBuild,          # 已有 .rebuild/out 时跳过构建，只做换链与分发
    [switch]$KeepBroken          # 保留被替换掉的旧链目录（默认为保留，见下）
)

$ErrorActionPreference = 'Stop'

$OpsDir   = Split-Path -Parent $PSScriptRoot                 # kms-ops
$FiscoDir = Join-Path $OpsDir 'fisco'
$Rebuild  = Join-Path $FiscoDir '.rebuild'
$OutDir   = Join-Path $Rebuild 'out'
$NewTree  = Join-Path $OutDir '127.0.0.1'
$LiveTree = Join-Path $OpsDir 'nodes\127.0.0.1'
$WslPath  = '/mnt/c/Users/AllenR/Desktop/kms-code/kms-ops/fisco'

function Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "  [OK]   $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "  [WARN] $msg" -ForegroundColor Yellow }

# ---------------------------------------------------------------------------
Step "0. 前置检查"
# ---------------------------------------------------------------------------
if (-not (Test-Path (Join-Path $FiscoDir 'build_chain.sh'))) { throw "缺少 $FiscoDir\build_chain.sh" }
if (-not (Test-Path (Join-Path $FiscoDir 'fisco-bcos.bin'))) { throw "缺少 $FiscoDir\fisco-bcos.bin" }
Ok "build_chain.sh 与 fisco-bcos 二进制就位"

# ---------------------------------------------------------------------------
Step "1. 生成链材料（build_chain.sh，在 WSL 里跑）"
# ---------------------------------------------------------------------------
if (-not $SkipBuild) {
    New-Item -ItemType Directory -Force -Path $Rebuild | Out-Null
    Copy-Item (Join-Path $FiscoDir 'fisco-bcos.bin') (Join-Path $Rebuild 'fisco-bcos') -Force
    if (Test-Path $OutDir) { Remove-Item $OutDir -Recurse -Force }

    # -e 用本地二进制（不联网下载）；-p 端口布局必须与 docker-compose.yml 一致：
    #   p2p 30300+ / channel 20200+ / jsonrpc 8545+
    $cmd = "cd $WslPath && chmod +x .rebuild/fisco-bcos build_chain.sh && " +
           "bash build_chain.sh -l '127.0.0.1:$Nodes' -p 30300,20200,8545 -e ./.rebuild/fisco-bcos -o ./.rebuild/out"
    $out = & wsl -d Ubuntu-22.04 -- bash -lc $cmd 2>&1
    $out | Select-Object -Last 8 | ForEach-Object { "    $_" }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $NewTree)) { throw "build_chain.sh 失败" }
    Ok "链材料已生成：$NewTree"
} else {
    if (-not (Test-Path $NewTree)) { throw "-SkipBuild 但 $NewTree 不存在" }
    Ok "复用已有构建产物"
}

# ---------------------------------------------------------------------------
Step "2. 证书自检（同一 PKI 才算过）"
# ---------------------------------------------------------------------------
$audit = Join-Path $OpsDir 'tests\fisco_verify_newchain.sh'
if (Test-Path $audit) {
    $wslOps = '/mnt/c/Users/AllenR/Desktop/kms-code/kms-ops'
    $wslOut = $OutDir.Replace($OpsDir, $wslOps).Replace('\', '/')
    $wslAudit = $audit.Replace($OpsDir, $wslOps).Replace('\', '/')
    & wsl -d Ubuntu-22.04 -- bash $wslAudit $wslOut |
        Where-Object { $_ -match 'FAIL|同一份|SDK 证书 <- node0|在创世' } | ForEach-Object { "    $_" }
}

# ---------------------------------------------------------------------------
Step "3. 停掉旧链容器"
# ---------------------------------------------------------------------------
$containers = 0..($Nodes - 1) | ForEach-Object { "kms_fisco_node$_" }
foreach ($c in $containers) {
    $null = docker stop $c 2>&1
    Ok "已停 $c"
}

# ---------------------------------------------------------------------------
Step "4. 换链目录（旧的移走，不删）"
# ---------------------------------------------------------------------------
if (Test-Path $LiveTree) {
    $bak = "$LiveTree.broken.$(Get-Date -Format 'yyyyMMddHHmmss')"
    Move-Item $LiveTree $bak
    Warn "旧链已移到 $bak（保留现场，可对比）"
}
Copy-Item $NewTree $LiveTree -Recurse
# 各节点目录里的二进制副本不需要：compose 统一用树根的 /data/fisco-bcos
Get-ChildItem (Join-Path $LiveTree 'node*') -Filter 'fisco-bcos' -Recurse -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue
Ok "新链已就位：$LiveTree"

# ---------------------------------------------------------------------------
Step "5. 改写各节点 config.ini"
# ---------------------------------------------------------------------------
# 两处必改：
#   1. peer 地址 —— build_chain.sh 生成的是 127.0.0.1:3030N（单机同命名空间假设）。
#      拆成一节点一容器后各自的 127.0.0.1 只指向自己，节点之间**实际连不上**。
#      这里改成 compose 里写死的静态 IP，比服务名解析更不依赖 DNS。
#   2. jsonrpc_listen_ip —— 默认只监听 127.0.0.1，容器里发布到宿主的 8545 端口
#      因此永远连不上（宿主侧表现为 fetch failed）。改成 0.0.0.0，
#      宿主侧只发布到 127.0.0.1，不对外网暴露。
for ($n = 0; $n -lt $Nodes; $n++) {
    $cfgPath = Join-Path $LiveTree "node$n\config.ini"
    $cfg = Get-Content $cfgPath -Raw
    for ($k = 0; $k -lt $Nodes; $k++) {
        # 注意是 172.20.0.10N（compose 里写的静态地址），不是 172.20.0.1N。
        # 写成 172.20.0.1N 时四节点互不可达，日志表现为
        # "TCP Connection refused by node ... No route to host" + Find disconnectedNode。
        $ip = "172.20.0.10$($k + 1)"
        $cfg = $cfg -replace "node\.$k=127\.0\.0\.1:3030$k", "node.$k=${ip}:3030$k"
    }
    $cfg = $cfg -replace 'jsonrpc_listen_ip=127\.0\.0\.1', 'jsonrpc_listen_ip=0.0.0.0'
    Set-Content -Path $cfgPath -Value $cfg -NoNewline -Encoding utf8
    Ok "node${n}: peer -> 172.20.0.10x:3030x，jsonrpc 监听 0.0.0.0"
}

# 二进制放树根（compose 的 command 引用 /data/fisco-bcos）
Copy-Item (Join-Path $FiscoDir 'fisco-bcos.bin') (Join-Path $LiveTree 'fisco-bcos') -Force
Ok "树根二进制就位"

# ---------------------------------------------------------------------------
Step "6. 分发 SDK 证书与 CA 材料"
# ---------------------------------------------------------------------------
# Java 后端镜像里的 /app/conf 来自 fisco/console/conf（见 build/*.Dockerfile），
# 所以这一处必须与链同步，否则 KMS 依旧握手失败 —— 这正是上一轮漏掉的一步。
$SdkDir = Join-Path $LiveTree 'sdk'
foreach ($dest in @((Join-Path $FiscoDir 'console\conf'), (Join-Path $OpsDir 'kms-java-backend\conf'))) {
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    Copy-Item (Join-Path $SdkDir '*') $dest -Force
    Ok "SDK 证书 -> $dest"
}
# CA 私钥留档：没有它就无法再签发 SDK 证书，链条会再次变成"谁都连不上"
$CertSrc = Join-Path $OutDir 'cert'
if (Test-Path $CertSrc) {
    $CertDst = Join-Path $FiscoDir 'cert'
    if (Test-Path $CertDst) { Remove-Item $CertDst -Recurse -Force }
    Copy-Item $CertSrc $CertDst -Recurse
    Warn "CA 私钥已存到 $CertDst —— 仅限开发环境，勿随产物外发"
}
# 排障脚本放进链目录（容器里直接 `bash /data/_rpc_probe.sh`）。
# 权威副本在 tests/ 下受版本管理 —— 因为 nodes/ 整个目录会在换链时被替换掉，
# 上一次就是这样把工具一起换没了。
$probeSrc = Join-Path $OpsDir 'tests\fisco_rpc_probe.sh'
if (Test-Path $probeSrc) {
    Copy-Item $probeSrc (Join-Path $LiveTree '_rpc_probe.sh') -Force
    Ok "容器内 RPC 探针 -> $LiveTree\_rpc_probe.sh"
}

# ---------------------------------------------------------------------------
Step "7. 启动新链"
# ---------------------------------------------------------------------------
Push-Location $OpsDir
try {
    # 不吞输出：上一版把它 $null = ... 2>&1 掉之后，compose 静默失败过一次，
    # 而脚本照样打印"已重建并启动" —— 报喜不报忧比不报还糟。
    & docker compose up -d --force-recreate $containers
} finally { Pop-Location }

Start-Sleep -Seconds 12
foreach ($c in $containers) {
    $st = (docker inspect -f '{{.State.Status}}' $c 2>&1)
    Ok "$c = $st"
}

Write-Host "`n完成。下一步验证：" -ForegroundColor Cyan
Write-Host "  pwsh -File kms-ops\scripts\verify-fisco-chain.ps1" -ForegroundColor Gray
