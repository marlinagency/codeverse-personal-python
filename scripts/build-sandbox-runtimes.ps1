param(
    [switch]$NoCache
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) {
    $bundledDocker = "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
    if (Test-Path $bundledDocker) {
        $docker = Get-Item $bundledDocker
    }
}

if (-not $docker) {
    throw "Docker CLI was not found. Install Docker Desktop first."
}

$cacheArg = @()
if ($NoCache) {
    $cacheArg = @("--no-cache")
}

& $docker.Source build @cacheArg -t codeverse-python-runtime:3.12 "$repoRoot\docker\runtimes\python"
& $docker.Source build @cacheArg -t codeverse-sql-runtime:16 "$repoRoot\docker\runtimes\sql"

& $docker.Source image ls codeverse-python-runtime:3.12
& $docker.Source image ls codeverse-sql-runtime:16
