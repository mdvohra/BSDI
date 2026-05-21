<#
.SYNOPSIS
  Copies this repo to D:\Braein\BSDI_Docker for deployment testing (skips heavy dirs).

.EXAMPLE
  .\copy-to-BSDI_Docker.ps1
.EXAMPLE
  .\copy-to-BSDI_Docker.ps1 -Dest "D:\somewhere\else"
#>
param(
    [string]$Source = $PSScriptRoot,
    [string]$Dest = "D:\Braein\BSDI_Docker"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $Source)) {
    Write-Error "Source not found: $Source"
    exit 1
}

Write-Host "Copying:"
Write-Host "  From: $Source"
Write-Host "  To:   $Dest"
Write-Host "Skipping directories named: .venv, node_modules"
Write-Host ""

New-Item -ItemType Directory -Force -Path $Dest | Out-Null

# /E     : all subfolders (including empty)
# /XD    : exclude any directory with these names at any depth
# /R:2   : retry twice on locked files
# /W:2   : wait 2s between retries
# Robocopy exit codes 0–7 mean success (partial copy still OK); 8+ is failure
robocopy $Source $Dest /E /XD ".venv" "node_modules" /R:2 /W:2

$exitCode = $LASTEXITCODE
if ($exitCode -ge 8) {
    Write-Error "robocopy failed with exit code $exitCode"
    exit $exitCode
}

Write-Host ""
Write-Host "Finished (robocopy code $exitCode — 0–7 is OK)."
Write-Host "Open: $Dest"
