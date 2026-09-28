param(
    [string[]]$Paths,
    [switch]$PushExisting
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Engine = Join-Path $RepoRoot "scripts\checkpoint_closeout.py"

if (-not (Test-Path $Python)) {
    throw "Repository virtual environment not found at $Python"
}

if (-not (Test-Path $Engine)) {
    throw "Checkpoint closeout engine not found at $Engine"
}

$Arguments = @($Engine)

if ($PushExisting) {
    $Arguments += "--push-existing"
}

if ($Paths -and $Paths.Count -gt 0) {
    $Arguments += "--paths"
    $Arguments += $Paths
}

Push-Location $RepoRoot
try {
    & $Python @Arguments
    $ExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

exit $ExitCode
