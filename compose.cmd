@echo off
setlocal
set DOCKER_BUILDKIT=1
set COMPOSE_DOCKER_CLI_BUILD=1
docker compose %*
exit /b %ERRORLEVEL%
