$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$desktop = [Environment]::GetFolderPath('Desktop')
$folder = Join-Path $desktop 'KMS旧入口恢复'
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut((Join-Path $desktop 'KMS旧入口恢复.lnk'))
$link.TargetPath = (Get-Command pwsh.exe -ErrorAction Stop).Source
$link.Arguments = '-NoLogo -NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $folder 'launch-old-origin.ps1') + '" -AllNodes'
$link.WorkingDirectory = $folder
$link.IconLocation = 'C:\Program Files\Google\Chrome\Application\chrome.exe,0'
$link.Save()
$saved = $shell.CreateShortcut((Join-Path $desktop 'KMS旧入口恢复.lnk'))
if ($saved.Arguments -ne $link.Arguments) { throw 'Shortcut argument verification failed' }
if (-not (Test-Path -LiteralPath $saved.TargetPath)) { throw 'Shortcut PowerShell target does not exist' }
Write-Output 'DESKTOP_SHORTCUT_VERIFIED'
