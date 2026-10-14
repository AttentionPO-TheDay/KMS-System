$ErrorActionPreference = 'Stop'
$ops = Split-Path $PSScriptRoot -Parent
$release = Join-Path $ops 'releases/acceptance-lifecycle-20261014'
$tar = Join-Path $release 'kms-acceptance-lifecycle-images.tar'
$gz = "$tar.gz"
if (Test-Path -LiteralPath $tar) { [IO.File]::Delete($tar) }
if (Test-Path -LiteralPath $gz) { [IO.File]::Delete($gz) }
if (Test-Path -LiteralPath (Join-Path $release 'SHA256SUMS-acceptance-lifecycle')) { [IO.File]::Delete((Join-Path $release 'SHA256SUMS-acceptance-lifecycle')) }
Copy-Item -LiteralPath (Join-Path $ops 'install-lifecycle-audit.py') -Destination $release
docker save -o $tar kms-updatedel-java:local kms-acceptance-backend:local kms-gateway-nginx:local
if ($LASTEXITCODE -ne 0) { throw 'docker save failed' }
$inputStream = [IO.File]::OpenRead($tar)
$outputStream = [IO.File]::Create($gz)
$gzipStream = [IO.Compression.GZipStream]::new($outputStream, [IO.Compression.CompressionLevel]::Optimal)
try { $inputStream.CopyTo($gzipStream) }
finally { $gzipStream.Dispose(); $outputStream.Dispose(); $inputStream.Dispose() }
docker load -i $gz
if ($LASTEXITCODE -ne 0) { throw 'Final gzip failed docker load; do not upload' }
$names = @('kms-acceptance-lifecycle-images.tar.gz', 'install-lifecycle-audit.py', 'README-acceptance-lifecycle.md')
$lines = foreach ($name in $names) { (Get-FileHash -LiteralPath (Join-Path $release $name) -Algorithm SHA256).Hash.ToLowerInvariant() + '  ' + $name }
[IO.File]::WriteAllLines((Join-Path $release 'SHA256SUMS-acceptance-lifecycle'), $lines, [Text.UTF8Encoding]::new($false))
$resolvedTar = (Resolve-Path -LiteralPath $tar).Path
if ((Split-Path $resolvedTar -Parent) -ne (Resolve-Path -LiteralPath $release).Path) { throw 'Unexpected tar location' }
Remove-Item -LiteralPath $resolvedTar
Get-ChildItem -LiteralPath $release | Select-Object Name,Length
