function Get-FrontendToolchain {
    param([string]$NodeHome)
    if (-not $NodeHome) {
        $NodeHome = Split-Path -Parent (Get-Command node -CommandType Application -ErrorAction Stop).Source
    }
    $NodeHome = [System.IO.Path]::GetFullPath($NodeHome)
    $nodeExe = Join-Path $NodeHome 'node.exe'
    $npmCli = Join-Path $NodeHome 'node_modules/npm/bin/npm-cli.js'
    $installModule = Join-Path $NodeHome 'node_modules/npm/lib/commands/install.js'
    if (-not (Test-Path $nodeExe) -or -not (Test-Path $npmCli)) {
        throw "NodeHome 必须是包含 node.exe 和完整 npm 的 Node 安装目录: $NodeHome"
    }
    # --version 不会加载 npm install 所需模块，不能证明 npm 安装完整。
    $check = & $nodeExe -e 'try { require(process.argv[1]); console.log(process.version); } catch(e) { console.error(e.code + ": " + e.message); process.exit(1); }' $installModule 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "npm 安装不完整，尚未开始构建。请修复 Node/npm 或用 -NodeHome 指定可用安装。诊断: $($check -join ' ')"
    }
    Write-Host "Frontend toolchain: Node $($check -join '') ($NodeHome)"
    return @{ NodeExe = $nodeExe; NpmCli = $npmCli; Home = $NodeHome }
}
