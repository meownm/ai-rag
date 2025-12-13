param(
  [string]$PgHost = "host.docker.internal",
  [int]$PgPort = 5432,
  [string]$PgDb = "observability",
  [string]$PgUser = "postgres",
  [string]$PgPassword = "",
  [switch]$SkipPgRoleCheck
)
function Test-Docker { try { docker version | Out-Null; $true } catch { $false } }
if (-not (Test-Docker)) { Write-Error "Docker не найден"; exit 1 }
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" -ErrorAction Stop; Write-Host "Создан .env из .env.example" }
$content = Get-Content ".env" -Raw
if ($content -notmatch "FASTAPI_PORT=") { Add-Content ".env" "`nFASTAPI_PORT=8101" }

# docker.sock check for Docker SD
if (-not (Test-Path "\\.\pipe\docker_engine") -and -not (Test-Path "/var/run/docker.sock")) {
  Write-Warning "Не найден docker.sock. Prometheus Docker Service Discovery может не работать.
Убедитесь, что Docker Desktop запущен и перезапустите стек после включения доступа к сокету."
}

# Roles
if (-not $SkipPgRoleCheck) {
  $env:PGPASSWORD = $PgPassword
  $ro = & psql -h $PgHost -p $PgPort -U $PgUser -d $PgDb -t -c "SELECT 1 FROM pg_roles WHERE rolname='phoenix_ro';" 2>$null
  $wr = & psql -h $PgHost -p $PgPort -U $PgUser -d $PgDb -t -c "SELECT 1 FROM pg_roles WHERE rolname='rag_writer';" 2>$null
  if ($LASTEXITCODE -ne 0) { Write-Warning "psql недоступен — пропускаю проверку ролей"; }
  else {
    if (-not ($ro -match "1") -or -not ($wr -match "1")) {
      Write-Host "Создаю роли phoenix_ro / rag_writer..."
      & psql -h $PgHost -p $PgPort -U $PgUser -d $PgDb -f "sql/create_roles.sql"
    } else { Write-Host "Роли уже существуют — ок." }
  }
  Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
}

docker compose build nginx-proxy
docker compose up -d

Write-Host "`nПанели:"
Write-Host "  Nginx proxy:  http://localhost:8080  (admin/admin123)"
Write-Host "  Grafana:      http://localhost:8080/grafana"
Write-Host "  Phoenix:      http://localhost:8080/phoenix"
Write-Host "  Helicone:     http://localhost:8080/helicone"
Write-Host "  Traceloop:    http://localhost:8080/traceloop"
