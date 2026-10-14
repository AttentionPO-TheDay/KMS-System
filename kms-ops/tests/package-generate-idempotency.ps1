$ErrorActionPreference = 'Stop'
$ops = Split-Path $PSScriptRoot -Parent
$release = Join-Path $ops 'releases/generate-idempotency-20261014'
$tar = Join-Path $release 'kms-generate-idempotency-image.tar'
$gz = "$tar.gz"
foreach ($path in @($tar, $gz, (Join-Path $release 'SHA256SUMS-generate-idempotency'))) {
  if (Test-Path -LiteralPath $path) { [IO.File]::Delete($path) }
}
docker save -o $tar kms-generate-java:local
if ($LASTEXITCODE -ne 0) { throw 'docker save failed' }
$inputStream = [IO.File]::OpenRead($tar)
$outputStream = [IO.File]::Create($gz)
$gzipStream = [IO.Compression.GZipStream]::new($outputStream, [IO.Compression.CompressionLevel]::Optimal)
try { $inputStream.CopyTo($gzipStream) }
finally { $gzipStream.Dispose(); $outputStream.Dispose(); $inputStream.Dispose() }
docker load -i $gz
if ($LASTEXITCODE -ne 0) { throw 'final docker load failed' }
$lines = @(
  ((Get-FileHash -LiteralPath $gz -Algorithm SHA256).Hash.ToLowerInvariant() + '  kms-generate-idempotency-image.tar.gz'),
  ((Get-FileHash -LiteralPath (Join-Path $release 'README-generate-idempotency.md') -Algorithm SHA256).Hash.ToLowerInvariant() + '  README-generate-idempotency.md')
)
[IO.File]::WriteAllLines((Join-Path $release 'SHA256SUMS-generate-idempotency'), $lines, [Text.UTF8Encoding]::new($false))
[IO.File]::Delete($tar)
Get-ChildItem -LiteralPath $release | Select-Object Name,Length
