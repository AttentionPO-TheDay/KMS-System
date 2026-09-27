$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $PSScriptRoot "runtime"
$frontRoot = Join-Path $PSScriptRoot "front"

function New-CleanDirectory {
    param(
        [string]$Path
    )

    if (Test-Path $Path) {
        Remove-Item -Recurse -Force $Path
    }

    New-Item -ItemType Directory -Path $Path | Out-Null
}

function Copy-Artifact {
    param(
        [string]$Source,
        [string]$Destination
    )

    if (-not (Test-Path $Source)) {
        throw "Build artifact not found: $Source"
    }

    $parentDir = Split-Path -Parent $Destination
    if (-not (Test-Path $parentDir)) {
        New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
    }

    if (Test-Path $Destination) {
        Remove-Item -Recurse -Force $Destination
    }

    Copy-Item -Path $Source -Destination $parentDir -Force

    $copiedPath = Join-Path $parentDir (Split-Path -Leaf $Source)
    if ($copiedPath -ne $Destination) {
        Rename-Item -Path $copiedPath -NewName (Split-Path -Leaf $Destination) -Force
    }
}

function Invoke-MavenBuild {
    param(
        [string]$ProjectDir
    )

    Write-Host "Building Maven project: $ProjectDir"
    Push-Location $ProjectDir
    try {
        # 必须带 clean：`mvn package` 不会清理 target/classes，
        # 一旦删除了某个源文件，它上一次编译出的 .class 会**残留在 target/classes
        # 并被打进 jar**，于是「代码已删、接口还在跑」。
        # 本仓库已真实踩过这个坑（generate-java 的 PermissionRequestController
        # 删除后仍能响应 /permission/request/list），因此这里固定用 clean package。
        mvn -DskipTests clean package
        if ($LASTEXITCODE -ne 0) {
            throw "Maven build failed: $ProjectDir"
        }
    }
    finally {
        Pop-Location
    }
}

function Invoke-MavenBuildWithArgs {
    param(
        [string]$ProjectDir,
        [string[]]$MavenArgs
    )

    Write-Host "Building Maven project: $ProjectDir"
    Push-Location $ProjectDir
    try {
        mvn @MavenArgs
        if ($LASTEXITCODE -ne 0) {
            throw "Maven build failed: $ProjectDir"
        }
    }
    finally {
        Pop-Location
    }
}

function Invoke-FrontendBuild {
    param(
        [string]$ProjectDir,
        [string]$BuildScript = "build:prod"
    )

    Write-Host "Building frontend project: $ProjectDir"
    Push-Location $ProjectDir
    try {
        npm install
        if ($LASTEXITCODE -ne 0) {
            throw "npm install failed: $ProjectDir"
        }

        npm run $BuildScript
        if ($LASTEXITCODE -ne 0) {
            throw "Frontend build failed: $ProjectDir"
        }
    }
    finally {
        Pop-Location
    }
}

function Invoke-GoProjectBuild {
    param(
        [string]$ProjectDir,
        [string]$OutputName
    )

    $distDir = Join-Path $ProjectDir "dist"
    if (-not (Test-Path $distDir)) {
        New-Item -ItemType Directory -Path $distDir | Out-Null
    }

    Write-Host "Building Go project: $ProjectDir"
    Push-Location $ProjectDir
    try {
        $env:GOOS = "linux"
        $env:GOARCH = "amd64"
        $env:CGO_ENABLED = "0"
        go build -o (Join-Path "dist" $OutputName) .
        if ($LASTEXITCODE -ne 0) {
            throw "Go build failed: $ProjectDir"
        }
    }
    finally {
        Remove-Item Env:GOOS -ErrorAction SilentlyContinue
        Remove-Item Env:GOARCH -ErrorAction SilentlyContinue
        Remove-Item Env:CGO_ENABLED -ErrorAction SilentlyContinue
        Pop-Location
    }
}

function Invoke-GoLinuxBuild {
    param(
        [string]$ProjectDir,
        [string]$OutputName
    )

    $distDir = Join-Path $ProjectDir "dist"
    if (-not (Test-Path $distDir)) {
        New-Item -ItemType Directory -Path $distDir | Out-Null
    }

    Write-Host "Building Go project for Linux: $ProjectDir"
    Push-Location $ProjectDir
    try {
        $env:GOOS = "linux"
        $env:GOARCH = "amd64"
        $env:CGO_ENABLED = "0"
        go build -o (Join-Path "dist" $OutputName) ./cmd/main.go
        if ($LASTEXITCODE -ne 0) {
            throw "Go build failed: $ProjectDir"
        }
    }
    finally {
        Remove-Item Env:GOOS -ErrorAction SilentlyContinue
        Remove-Item Env:GOARCH -ErrorAction SilentlyContinue
        Remove-Item Env:CGO_ENABLED -ErrorAction SilentlyContinue
        Pop-Location
    }
}

$generateJavaDir = Join-Path $repoRoot "kms-generate\java-backend"
$updatedelJavaDir = Join-Path $repoRoot "kms-updatedel\java-backend"
# $distributeJavaDir 已移除：旧分发 Java 服务已整体下线（Q11）。
# $distributeFrontDir 也已移除（2026-09-26）：分发自带后台
# （原 kms-distribute/extracted/ruoyi (2)/web，该目录已随本次清理删除）
# 随本次清理下线。**注意其原有的保留理由是过时的**——旧注释说"它产出的 /distribute/
# 仍被管理端 iframe 内嵌"，但 29_distribution_native_pages.sql 已把菜单 9101/9102
# 从 iframe 改成原生组件（distOverview/index、chain/index，query 清空），9103 更早
# （27_node_management_page.sql）就改了。此后没有任何脚本再把 /distribute/ 加回菜单。
$generateGoDir = Join-Path $repoRoot "kms-generate\go-backend"
$updatedelGoDir = Join-Path $repoRoot "kms-updatedel\go-backend"
$acceptanceGoDir = Join-Path $repoRoot "kms-acceptance\backend"
$updatedelFrontDir = Join-Path $repoRoot "kms-updatedel\front"
# $userFrontDir 已移除（阶段 1 前端合并）：kms-user 的业务页已迁入 kms-updatedel。
# 应用**尚未退役**（阶段 9 才删除目录），只是不再参与构建。
$acceptanceFrontDir = Join-Path $repoRoot "kms-acceptance\front"
$acceptanceSecurityDir = Join-Path $repoRoot "security"

New-CleanDirectory $runtimeRoot
New-CleanDirectory (Join-Path $frontRoot "updatedel")
New-CleanDirectory (Join-Path $frontRoot "acceptance")

Invoke-MavenBuild $generateJavaDir
Invoke-MavenBuild $updatedelJavaDir
# 旧分发 Java 服务的 Maven 构建已移除（Q11 整体下线）

Invoke-GoLinuxBuild -ProjectDir $generateGoDir -OutputName "kms-generate-service"
Invoke-GoLinuxBuild -ProjectDir $updatedelGoDir -OutputName "kms-updatedel-service"
Invoke-GoProjectBuild -ProjectDir $acceptanceGoDir -OutputName "kms-acceptance-backend"

# 说明：/generate/ 静态前端（kms-generate/front）已退役 —— 它是与统一管理端高度重复的
# 遗留应用，页面已并入 kms-updatedel。因此这里**不再构建它**，也不再往 kms-ops/front
# 投放 generate 产物；generate 只保留**后端**构建（上面的 kms-generate.jar 与
# kms-generate-service，仍供 /generate-api/ 与统一管理端使用）。
# 详见 kms-generate/front/RETIRED.md，不要在没有决策的情况下把这段构建加回来。
Invoke-FrontendBuild -ProjectDir $updatedelFrontDir -BuildScript "build:prod"
Invoke-FrontendBuild -ProjectDir $acceptanceFrontDir -BuildScript "build"

Copy-Artifact -Source (Join-Path $generateJavaDir "ruoyi-admin\target\kms-generate.jar") -Destination (Join-Path $runtimeRoot "generate-java\kms-generate.jar")
Copy-Artifact -Source (Join-Path $generateJavaDir "config-fisco.toml") -Destination (Join-Path $runtimeRoot "generate-java\config-fisco.toml")
Copy-Artifact -Source (Join-Path $updatedelJavaDir "ruoyi-admin\target\kms-updatedel.jar") -Destination (Join-Path $runtimeRoot "updatedel-java\kms-updatedel.jar")
Copy-Artifact -Source (Join-Path $updatedelJavaDir "ruoyi-admin\src\main\resources\config-fisco.toml") -Destination (Join-Path $runtimeRoot "updatedel-java\config-fisco.toml")
# 旧分发 Java 服务的 jar 拷贝已移除（Q11 整体下线）

Copy-Artifact -Source (Join-Path $generateGoDir "dist\kms-generate-service") -Destination (Join-Path $runtimeRoot "generate-go\kms-generate-service")
Copy-Artifact -Source (Join-Path $updatedelGoDir "dist\kms-updatedel-service") -Destination (Join-Path $runtimeRoot "updatedel-go\kms-updatedel-service")
Copy-Artifact -Source (Join-Path $acceptanceGoDir "dist\kms-acceptance-backend") -Destination (Join-Path $runtimeRoot "acceptance-go\kms-acceptance-backend")
Copy-Artifact -Source (Join-Path $acceptanceSecurityDir "security_test.sh") -Destination (Join-Path $runtimeRoot "acceptance-go\security\security_test.sh")

# 前端产物投放：2 个（generate / distribute / user 均已下线或随阶段 1 合并退役）
Copy-Item -Path (Join-Path $updatedelFrontDir "dist\*") -Destination (Join-Path $frontRoot "updatedel") -Recurse -Force
Copy-Item -Path (Join-Path $acceptanceFrontDir "dist\*") -Destination (Join-Path $frontRoot "acceptance") -Recurse -Force

Write-Host "Local build artifacts are ready under kms-ops/runtime and kms-ops/front."
Write-Host "Run 'docker compose up -d' in kms-ops/."
