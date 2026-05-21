# Run Docker Compose with BuildKit enabled (pip cache mounts, faster builds).
# Usage (from repo root): .\compose.ps1 up -d --build
$ErrorActionPreference = "Stop"
$env:DOCKER_BUILDKIT = "1"
$env:COMPOSE_DOCKER_CLI_BUILD = "1"
docker compose @args
exit $LASTEXITCODE
