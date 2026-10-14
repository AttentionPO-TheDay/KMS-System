#requires -Version 7.0
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$testRoot = Join-Path $root ('dist/package-test-' + [guid]::NewGuid().ToString('N'))
function Assert([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}
foreach ($withoutDid in @($false, $true)) {
    $output = Join-Path $testRoot $(if ($withoutDid) { 'base' } else { 'did' })
    & (Join-Path $root 'ship.ps1') -SkipImages -WithoutDid:$withoutDid -OutDir $output
    $compose = Join-Path $output 'docker-compose.yml'
    $json = docker compose -f $compose --profile fabric-did config --format json
    Assert ($LASTEXITCODE -eq 0) '最终 compose 无法解析'
    $config = ($json -join "`n") | ConvertFrom-Json -AsHashtable
    $images = @($config.services.Values.image | Where-Object { $_ -like 'kms-*' } | Sort-Object -Unique)
    Assert ($images.Count -eq $(if ($withoutDid) { 7 } else { 8 })) '镜像覆盖数量错误'
    Assert ($config.services.ContainsKey('fabric-did-bridge') -eq (-not $withoutDid)) 'DID 模式未正确切换'
    foreach ($name in @('generate-java', 'updatedel-java', 'dvadmin3-django', 'nginx')) {
        Assert ($config.services[$name].environment.KMS_CHAIN_WRITES_ENABLED -eq 'false') "$name 未暂停写链"
        Assert (-not $config.services[$name].ContainsKey('build')) "$name 仍依赖源码构建"
    }
    Assert ($null -eq $config.services['dvadmin3-django'].entrypoint) 'Django 正常迁移启动流程被覆盖'
    Assert (($config.services['dvadmin3-django'].command -join ' ') -eq 'bash /backend/start.sh') 'Django 迁移启动命令丢失'
    if (-not $withoutDid) {
        $bridge = $config.services['fabric-did-bridge']
        Assert (-not $bridge.ports) 'DID 内部端口被发布到宿主机'
        Assert ($bridge.environment.FABRIC_DID_WRITE_ENABLED -eq 'false') 'DID 写入被启用'
        Assert ($bridge.environment.FABRIC_DID_ENABLED -eq 'false') '待配置 SDK 被提前启用'
        Assert ($bridge.volumes[0].read_only -eq $true) 'DID 凭据挂载不是只读'
    }
    $files = @(tar -tzf (Join-Path $output 'kms-deploy.tar.gz'))
    Assert ($LASTEXITCODE -eq 0) '部署包无法读取'
    foreach ($required in @('./nginx/demo-server.conf.template', './nginx/30-kms-demo.sh', './SERVER_DEPLOY.md')) {
        Assert ($files -contains $required) "遗漏文件 $required"
    }
    Assert (-not ($files -match 'node\d+/(data|log)/|fisco/console/(accounts?|log)/|deploylog.txt')) '混入本地链状态或账户'
    Assert (-not ($files -match 'fabric-did-secrets/.+\.(pem|key|crt)$')) '混入真实 DID 凭据'
    Assert (($files -contains './WITH_DID') -eq (-not $withoutDid)) '部署脚本 DID 标记不匹配'
    $envLines = Get-Content (Join-Path $output '.env')
    Assert (-not ($envLines -match '^FISCO_(CONTRACT_ADDRESS|PRIVATE_KEY)=.+')) '混入本机旧链引用'
    Assert (-not ((Get-Content (Join-Path $root 'mysql/init/03.sql') -Raw) -match 'INSERT INTO `keymanage`')) '初始化仍注入历史示例密钥'
    Write-Host "PASS: $(if ($withoutDid) { 'base' } else { 'DID' }) final package, fresh data, write gates, migration, credential boundaries"
}
Write-Host "验证产物: $testRoot（不启动容器、不导出应用镜像、不提交交易）"
