param([switch]$CheckOnly, [string]$ProfileDirectory, [switch]$TrustCertificate, [switch]$AllNodes)

$ErrorActionPreference = 'Stop'
$oldOrigin = 'https://10.112.125.22:8443'
$newIp = '10.129.114.144'
$expectedCertificateSha256 = '130A2051D968A46EDE55020E2AE9A5B7727F6C6CA2DDB5DE3021A6038AD038DB'
$certPath = Join-Path $PSScriptRoot 'kms-compatible-server.cer'

try {
    if ((Get-FileHash -LiteralPath $certPath -Algorithm SHA256).Hash -ne $expectedCertificateSha256) {
        throw '站点公有证书校验失败，请使用本次恢复包中的原文件。'
    }
    $cert = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($certPath)
    $trustedPath = 'Cert:\CurrentUser\Root\' + $cert.Thumbprint
    $chrome = Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'
    if (-not (Test-Path -LiteralPath $chrome)) {
        throw '未找到原 Google Chrome 安装，请确认使用的是测试时的浏览器。'
    }
    $userDataRoot = Join-Path $env:LOCALAPPDATA 'Google\Chrome\User Data'
    $state = Get-Content -LiteralPath (Join-Path $userDataRoot 'Local State') -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
    $profiles = @(foreach ($entry in $state.profile.info_cache.GetEnumerator()) {
        if ([IO.Path]::GetFileName($entry.Key) -ne $entry.Key) { continue }
        $profilePath = Join-Path $userDataRoot $entry.Key
        $database = Join-Path $profilePath 'IndexedDB\https_10.112.125.22_8443.indexeddb.leveldb'
        if (Test-Path -LiteralPath $database -PathType Container) {
            [pscustomobject]@{ Directory = $entry.Key; Display = [string]$entry.Value.name }
        }
    }) | Sort-Object Directory
    if (-not $profiles.Count) { throw '没有找到保留旧站点数据库目录的 Chrome 配置；未作任何修改。' }
    $proxy = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
    if ($ProfileDirectory -and $ProfileDirectory -notin $profiles.Directory) {
        throw '指定的原 Chrome 配置没有旧站点数据库目录。'
    }
    if ($AllNodes -and $ProfileDirectory) { throw 'AllNodes 与 ProfileDirectory 不能同时使用。' }
    $nodeDirectories = @('Profile 5', 'Profile 6', 'Profile 7')
    if ($AllNodes -and @($nodeDirectories | Where-Object { $_ -notin $profiles.Directory }).Count) {
        throw '节点A/B/C的原配置不完整，未创建或替换任何配置。'
    }
    if ($CheckOnly) {
        [pscustomobject]@{
            CertificateValid = $true
            CertificateTrusted = (Test-Path $trustedPath)
            ProfilesWithOldOrigin = $profiles.Count
            StaticSystemProxyPreserved = [bool]$proxy.ProxyEnable
            BrowserDataModified = $false
            RequestedProfiles = $(if ($AllNodes) { $nodeDirectories } elseif ($ProfileDirectory) { @($ProfileDirectory) } else { @() })
        } | ConvertTo-Json -Compress
        exit 0
    }

    Write-Host 'KMS 原浏览器入口恢复' -ForegroundColor Cyan
    Write-Host '继续使用旧网址和原 Chrome 配置，实际连接新服务器。不读取、复制或重新生成私钥。'
    Write-Host ''
    while (Get-Process chrome -ErrorAction SilentlyContinue) {
        $browsers = @(Get-CimInstance Win32_Process -Filter "Name = 'chrome.exe'" |
            Where-Object { $_.CommandLine -and $_.CommandLine -notmatch '--type=' })
        $incompatible = @($browsers | Where-Object {
            $_.CommandLine -notmatch '--host-resolver-rules="?MAP 10\.112\.125\.22 10\.129\.114\.144' -or
            $_.CommandLine -match '--ignore-certificate-errors'
        })
        if ($browsers.Count -gt 0 -and $incompatible.Count -eq 0) {
            Write-Host '复用已带旧入口映射的 Chrome，可同时打开多个节点配置。'
            break
        }
        if ($ProfileDirectory) { throw 'Chrome 尚未完全退出，请先退出所有 Chrome。' }
        Write-Host '请先退出所有 Chrome 窗口。可先保存未完成操作，再在地址栏输入 chrome://quit。' -ForegroundColor Yellow
        [void](Read-Host '退出后按回车继续；此程序不会替你关闭浏览器')
    }
    if ($TrustCertificate -and -not (Test-Path $trustedPath)) {
        Import-Certificate -FilePath $certPath -CertStoreLocation 'Cert:\CurrentUser\Root' | Out-Null
        if (-not (Test-Path $trustedPath)) { throw '当前用户证书信任安装未完成。' }
    }
    while (-not (Test-Path $trustedPath)) {
        Write-Host '需要信任本次同时覆盖新旧 IP 的站点证书：' -ForegroundColor Yellow
        Write-Host '在即将打开的证书窗口中：安装证书 -> 当前用户 -> 将所有证书放入下列存储 -> 浏览 -> 受信任的根证书颁发机构 -> 完成。'
        Write-Host ('证书 SHA-256：' + $expectedCertificateSha256)
        Start-Process -FilePath $certPath
        [void](Read-Host '完成证书安装后按回车继续')
    }

    if ($AllNodes) {
        $selectedProfiles = @($profiles | Where-Object { $_.Directory -in $nodeDirectories })
    } elseif ($ProfileDirectory) {
        $selectedProfiles = @($profiles | Where-Object Directory -EQ $ProfileDirectory)
    } else {
        Write-Host '请选择原来测试时使用的 Chrome 配置（名称与浏览器头像菜单对应）：'
        for ($i = 0; $i -lt $profiles.Count; $i++) {
            Write-Host ('  {0}. {1} [{2}]' -f ($i + 1), $profiles[$i].Display, $profiles[$i].Directory)
        }
        do {
            $choice = Read-Host '输入编号'
            $number = 0
            $valid = [int]::TryParse($choice, [ref]$number) -and $number -ge 1 -and $number -le $profiles.Count
        } until ($valid)
        $selectedProfiles = @($profiles[$number - 1])
    }
    $commonArguments = @(
        '--host-resolver-rules="MAP 10.112.125.22 10.129.114.144"'
    )
    if ($proxy.ProxyEnable -and $proxy.ProxyServer) {
        # Keep the user's current proxy. Only the two KMS IPs are sent directly.
        $commonArguments += '--proxy-server="' + $proxy.ProxyServer + '"'
        $commonArguments += '--proxy-bypass-list="' + $proxy.ProxyOverride + ';10.112.125.22;10.129.114.144"'
    } elseif ($proxy.AutoConfigURL) {
        throw '检测到系统 PAC 代理。未更改它；需先为旧 KMS IP 配置直连后再使用此入口。'
    }
    $commonArguments += @('--new-window', ('"' + $oldOrigin + '/updatedel/demo"'))
    foreach ($selected in $selectedProfiles) {
        $chromeArguments = @(('--profile-directory="' + $selected.Directory + '"')) + $commonArguments
        Start-Process -FilePath $chrome -ArgumentList $chromeArguments -WindowStyle Normal
        Write-Host ('已启动：' + $selected.Display + ' [' + $selected.Directory + ']') -ForegroundColor Green
        Start-Sleep -Milliseconds 600
    }
    Write-Host ('地址栏应保持 ' + $oldOrigin + '，连接目标是 ' + $newIp + '。')
    Write-Host '以后请继续通过这个启动器进入原测试站点。'
} catch {
    Write-Host ('未完成：' + $_.Exception.Message) -ForegroundColor Red
    if ($CheckOnly -or $ProfileDirectory) { exit 1 }
    [void](Read-Host '按回车关闭')
    exit 1
}
