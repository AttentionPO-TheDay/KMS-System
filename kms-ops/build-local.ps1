$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot

function Invoke-MavenBuild {
    param(
        [string]$ProjectDir
    )

    Write-Host "Building Maven project: $ProjectDir"
    Push-Location $ProjectDir
    try {
        mvn -DskipTests package
    }
    finally {
        Pop-Location
    }
}

function Invoke-GoLinuxBuild {
    param(
        [string]$ProjectDir
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
        go build -o dist/key-service ./cmd/main.go
    }
    finally {
        Remove-Item Env:GOOS -ErrorAction SilentlyContinue
        Remove-Item Env:GOARCH -ErrorAction SilentlyContinue
        Remove-Item Env:CGO_ENABLED -ErrorAction SilentlyContinue
        Pop-Location
    }
}

Invoke-MavenBuild (Join-Path $repoRoot "kms-generate\java-backend")
Invoke-MavenBuild (Join-Path $repoRoot "kms-updatedel\java-backend")
Invoke-MavenBuild (Join-Path $repoRoot "kms-distribute\java-backend")

Invoke-GoLinuxBuild (Join-Path $repoRoot "kms-generate\go-backend")
Invoke-GoLinuxBuild (Join-Path $repoRoot "kms-updatedel\go-backend")

Write-Host "Local build artifacts are ready. Run 'docker compose up -d' in kms-ops/."
