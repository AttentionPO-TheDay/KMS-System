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

    Copy-Item -Path $Source -Destination $Destination -Force
}

function Invoke-MavenBuild {
    param(
        [string]$ProjectDir
    )

    Write-Host "Building Maven project: $ProjectDir"
    Push-Location $ProjectDir
    try {
        mvn -DskipTests package
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
        [string]$ProjectDir
    )

    Write-Host "Building frontend project: $ProjectDir"
    Push-Location $ProjectDir
    try {
        npm install
        if ($LASTEXITCODE -ne 0) {
            throw "npm install failed: $ProjectDir"
        }

        npm run build:prod
        if ($LASTEXITCODE -ne 0) {
            throw "Frontend build failed: $ProjectDir"
        }
    }
    finally {
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
$distributeJavaDir = Join-Path $repoRoot "kms-distribute\java-backend"
$generateGoDir = Join-Path $repoRoot "kms-generate\go-backend"
$updatedelGoDir = Join-Path $repoRoot "kms-updatedel\go-backend"
$generateFrontDir = Join-Path $repoRoot "kms-generate\front"
$updatedelFrontDir = Join-Path $repoRoot "kms-updatedel\front"

New-CleanDirectory $runtimeRoot
New-CleanDirectory (Join-Path $frontRoot "generate")
New-CleanDirectory (Join-Path $frontRoot "updatedel")

Invoke-MavenBuild $generateJavaDir
Invoke-MavenBuild $updatedelJavaDir
Invoke-MavenBuild $distributeJavaDir

Invoke-GoLinuxBuild -ProjectDir $generateGoDir -OutputName "kms-generate-service"
Invoke-GoLinuxBuild -ProjectDir $updatedelGoDir -OutputName "kms-updatedel-service"

Invoke-FrontendBuild $generateFrontDir
Invoke-FrontendBuild $updatedelFrontDir

Copy-Artifact -Source (Join-Path $generateJavaDir "ruoyi-admin\target\kms-generate.jar") -Destination (Join-Path $runtimeRoot "generate-java\kms-generate.jar")
Copy-Artifact -Source (Join-Path $generateJavaDir "config-fisco.toml") -Destination (Join-Path $runtimeRoot "generate-java\config-fisco.toml")
Copy-Artifact -Source (Join-Path $updatedelJavaDir "ruoyi-admin\target\kms-updatedel.jar") -Destination (Join-Path $runtimeRoot "updatedel-java\kms-updatedel.jar")
Copy-Artifact -Source (Join-Path $updatedelJavaDir "ruoyi-admin\src\main\resources\config-fisco.toml") -Destination (Join-Path $runtimeRoot "updatedel-java\config-fisco.toml")
Copy-Artifact -Source (Join-Path $distributeJavaDir "ruoyi-admin\target\kms-distribute.jar") -Destination (Join-Path $runtimeRoot "distribute-java\kms-distribute.jar")

Copy-Artifact -Source (Join-Path $generateGoDir "dist\kms-generate-service") -Destination (Join-Path $runtimeRoot "generate-go\kms-generate-service")
Copy-Artifact -Source (Join-Path $updatedelGoDir "dist\kms-updatedel-service") -Destination (Join-Path $runtimeRoot "updatedel-go\kms-updatedel-service")

Copy-Item -Path (Join-Path $generateFrontDir "dist\*") -Destination (Join-Path $frontRoot "generate") -Recurse -Force
Copy-Item -Path (Join-Path $updatedelFrontDir "dist\*") -Destination (Join-Path $frontRoot "updatedel") -Recurse -Force

Write-Host "Local build artifacts are ready under kms-ops/runtime and kms-ops/front."
Write-Host "Run 'docker compose up -d' in kms-ops/."
