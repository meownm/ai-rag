param(
  [string]$EnvFile = ".env"
)

$ErrorActionPreference = "Stop"

if (-Not (Test-Path $EnvFile)) {
  Write-Error "Env file '$EnvFile' not found. Copy .env.example to .env and update values."
}

Write-Host "Loading environment variables from $EnvFile" -ForegroundColor Cyan
Get-Content $EnvFile | ForEach-Object {
  if ($_ -match "^#" -or -not $_) { return }
  $name, $value = $_ -split '=', 2
  [System.Environment]::SetEnvironmentVariable($name, $value)
}

$required = @('KEYCLOAK_ADMIN','KEYCLOAK_ADMIN_PASSWORD','POSTGRES_PASSWORD','MINIO_ROOT_PASSWORD','HOST_DATA_DIR')
foreach ($key in $required) {
  if (-not [System.Environment]::GetEnvironmentVariable($key)) {
    Write-Error "Missing required env variable: $key"
  }
}

$hostData = [System.Environment]::GetEnvironmentVariable('HOST_DATA_DIR')
if (-not (Test-Path $hostData)) {
  Write-Host "Creating data directory at $hostData" -ForegroundColor Yellow
  New-Item -ItemType Directory -Force -Path $hostData | Out-Null
}

Write-Host "Pulling images..." -ForegroundColor Cyan
docker compose --env-file $EnvFile -f compose.yml pull

Write-Host "Starting stack..." -ForegroundColor Cyan
docker compose --env-file $EnvFile -f compose.yml up -d

Write-Host "Containers running. Access Keycloak at http://localhost:$([System.Environment]::GetEnvironmentVariable('KEYCLOAK_HTTP_PORT'))" -ForegroundColor Green
