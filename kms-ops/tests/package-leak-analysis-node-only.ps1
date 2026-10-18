$ErrorActionPreference = 'Stop'
$ops = Split-Path $PSScriptRoot -Parent
$release = Join-Path $ops 'releases/leak-analysis-node-only-20261014'
$tar = Join-Path $release 'kms-leak-analysis-nginx.tar'
$gz = "$tar.gz"
$checksum = Join-Path $release 'SHA256SUMS-leak-analysis'
foreach ($target in @($tar, $gz, $checksum)) {
    if (Test-Path -LiteralPath $target) { throw "Refusing to overwrite artifact: $target" }
}
docker save -o $tar kms-gateway-nginx:local
if ($LASTEXITCODE -ne 0) { throw 'docker save failed' }
$inputStream = [IO.File]::OpenRead($tar)
$outputStream = [IO.File]::Open($gz, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
$gzipStream = [IO.Compression.GZipStream]::new($outputStream, [IO.Compression.CompressionLevel]::Optimal)
try { $inputStream.CopyTo($gzipStream) }
finally { $gzipStream.Dispose(); $outputStream.Dispose(); $inputStream.Dispose() }
docker load -i $gz
if ($LASTEXITCODE -ne 0) { throw 'final docker load failed' }
$names = @('kms-leak-analysis-nginx.tar.gz', 'apply-leak-analysis.sh', 'README-leak-analysis.md')
$lines = foreach ($name in $names) { (Get-FileHash -LiteralPath (Join-Path $release $name)).Hash.ToLowerInvariant() + '  ' + $name }
[IO.File]::WriteAllText($checksum, ($lines -join "`n") + "`n", [Text.UTF8Encoding]::new($false))
$resolvedTar = (Resolve-Path -LiteralPath $tar).Path
if ((Split-Path $resolvedTar -Parent) -ne (Resolve-Path -LiteralPath $release).Path) { throw 'Unexpected tar target' }
Remove-Item -LiteralPath $resolvedTar
Get-ChildItem -LiteralPath $release | Select-Object Name,Length
