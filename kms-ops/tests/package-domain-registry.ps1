$ErrorActionPreference = 'Stop'
$ops = Split-Path $PSScriptRoot -Parent
$release = Join-Path $ops 'releases/domain-registry-20261014'
$tar = Join-Path $release 'kms-domain-registry-images.tar'
$gz = "$tar.gz"
$checksum = Join-Path $release 'SHA256SUMS-domain-registry'
foreach ($target in @($tar, $gz, $checksum)) {
    if (Test-Path -LiteralPath $target) { throw "Refusing to overwrite artifact: $target" }
}
foreach ($name in @('55_restore_domain_management.sql', '56_domain_registry_cross_distribution.sql')) {
    Copy-Item -LiteralPath (Join-Path $ops "mysql/init/$name") -Destination $release
}
docker save -o $tar kms-dvadmin3-django:local kms-updatedel-java:local kms-gateway-nginx:local
if ($LASTEXITCODE -ne 0) { throw 'docker save failed' }
$inputStream = [IO.File]::OpenRead($tar)
$outputStream = [IO.File]::Open($gz, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
$gzipStream = [IO.Compression.GZipStream]::new($outputStream, [IO.Compression.CompressionLevel]::Optimal)
try { $inputStream.CopyTo($gzipStream) }
finally { $gzipStream.Dispose(); $outputStream.Dispose(); $inputStream.Dispose() }
docker load -i $gz
if ($LASTEXITCODE -ne 0) { throw 'final docker load failed' }
$names = @('kms-domain-registry-images.tar.gz', '55_restore_domain_management.sql', '56_domain_registry_cross_distribution.sql', 'apply-domain-registry.sh', 'README-domain-registry.md')
$lines = foreach ($name in $names) { (Get-FileHash -LiteralPath (Join-Path $release $name)).Hash.ToLowerInvariant() + '  ' + $name }
[IO.File]::WriteAllLines($checksum, $lines, [Text.UTF8Encoding]::new($false))
$resolvedTar = (Resolve-Path -LiteralPath $tar).Path
if ((Split-Path $resolvedTar -Parent) -ne (Resolve-Path -LiteralPath $release).Path) { throw 'Unexpected tar target' }
Remove-Item -LiteralPath $resolvedTar
Get-ChildItem -LiteralPath $release | Select-Object Name,Length
