param([switch]$ReuseSavedTar)
$ErrorActionPreference = 'Stop'
$ops = Split-Path $PSScriptRoot -Parent
$release = Join-Path $ops 'releases/node-workbench-20261014'
$tar = Join-Path $release 'kms-node-workbench-images.tar'
$gz = "$tar.gz"
$checksum = Join-Path $release 'SHA256SUMS-node-workbench'
foreach ($target in @($gz, $checksum)) {
    if (Test-Path -LiteralPath $target) { throw "Refusing to overwrite existing artifact: $target" }
}
if (-not $ReuseSavedTar) {
    if (Test-Path -LiteralPath $tar) { throw "Refusing to overwrite existing tar: $tar" }
    docker save -o $tar kms-dvadmin3-django:local kms-gateway-nginx:local
    if ($LASTEXITCODE -ne 0) { throw 'docker save failed' }
}
$inputStream = [IO.File]::OpenRead($tar)
$outputStream = [IO.File]::Open($gz, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
$gzipStream = [IO.Compression.GZipStream]::new($outputStream, [IO.Compression.CompressionLevel]::Optimal)
try { $inputStream.CopyTo($gzipStream) }
finally { $gzipStream.Dispose(); $outputStream.Dispose(); $inputStream.Dispose() }
docker load -i $gz
if ($LASTEXITCODE -ne 0) { throw 'Final gzip failed docker load; do not upload' }
$names = @('kms-node-workbench-images.tar.gz', 'README-node-workbench.md')
$lines = foreach ($name in $names) {
    (Get-FileHash -LiteralPath (Join-Path $release $name) -Algorithm SHA256).Hash.ToLowerInvariant() + '  ' + $name
}
[IO.File]::WriteAllLines($checksum, $lines, [Text.UTF8Encoding]::new($false))
$resolvedTar = (Resolve-Path -LiteralPath $tar).Path
if ((Split-Path $resolvedTar -Parent) -ne (Resolve-Path -LiteralPath $release).Path) { throw 'Unexpected tar location' }
Remove-Item -LiteralPath $resolvedTar
Get-ChildItem -LiteralPath $release | Select-Object Name,Length
