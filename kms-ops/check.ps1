$ErrorActionPreference = "Stop"

Push-Location $PSScriptRoot
try {

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
        [string]$TableName
    )

    $result = docker exec kms_mysql mysql -N -uroot -proot123456 -D kms -e "SHOW TABLES LIKE '$TableName';"
    if ($result -match "^$TableName$") {
        Write-Host "[OK] MySQL table exists -> $TableName"
        return
    }

    throw "MySQL table missing: $TableName"
}

Write-Host "== Docker Compose Status =="
docker compose ps

Write-Host "`n== HTTP Checks =="
Test-HttpEndpoint -Name "generate-go ping" -Url "http://localhost:8081/generate/ping"
Test-HttpEndpoint -Name "updatedel-go ping" -Url "http://localhost:8082/lifecycle/ping"

Write-Host "`n== Database Checks =="
Test-MySqlTable -TableName "sys_user"
Test-MySqlTable -TableName "keymanage"
Test-MySqlTable -TableName "permission_request"
Test-MySqlTable -TableName "key_distribute_record"

Write-Host "`nAll checks passed."
}
finally {
    Pop-Location
}
