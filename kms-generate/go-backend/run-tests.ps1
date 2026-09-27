# =============================================================================
# 运行 kms-generate Go 后端的单元测试
# -----------------------------------------------------------------------------
# 为什么要这么个脚本：
#   config 包在 **init 阶段**就校验必填环境变量（INTERNAL_TOKEN、KGC_MASTER_SECRET…），
#   缺失直接 panic。这是刻意设计——宁可起不来，也不要带着公开默认值对外服务。
#   代价是 `go test ./...` 裸跑会 panic 在 config.init 上，看起来像"测试坏了"。
#   本脚本为测试注入一次性占位值，**与生产配置无关**。
#
# 用法：pwsh -File .\run-tests.ps1
# =============================================================================
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

# 测试专用占位值：不是任何真实部署的凭证
if (-not $env:INTERNAL_TOKEN) { $env:INTERNAL_TOKEN = 'test-only-internal-token' }
# 64 位十六进制，仅用于让 KGC 校验通过；不是任何真实部署使用的主私钥
if (-not $env:KGC_MASTER_SECRET) { $env:KGC_MASTER_SECRET = ('0123456789ABCDEF' * 4) }

Write-Host "运行 go test（已注入测试专用环境变量）..."
go test -count=1 ./...
if ($LASTEXITCODE -ne 0) {
    throw "go test 失败，退出码 $LASTEXITCODE"
}
Write-Host "全部通过。"