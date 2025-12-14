# Быстрый запуск инфраструктуры на Windows

Этот каталог содержит минимальный набор ресурсов для поднятия инфраструктурных сервисов (PostgreSQL, Keycloak и MinIO) через **Docker Desktop** на Windows. Ниже приведены шаги для подготовки окружения и запуска контейнеров.

## Требования
- Windows 10/11 с включенным WSL2.
- Установленный [Docker Desktop](https://www.docker.com/products/docker-desktop/).
- PowerShell 7+.

## Подготовка
1. Склонируйте репозиторий и перейдите в каталог `windows-install/`.
2. Скопируйте пример переменных окружения и отредактируйте его под ваше окружение:
   ```powershell
   Copy-Item .env.example .env
   # Откройте .env и задайте уникальные пароли, пути к volume и OIDC-настройки.
   ```
   Обязательно проверьте:
   - Пути к директориям `POSTGRES_DATA_PATH`, `KEYCLOAK_DATA_PATH` и `MINIO_DATA_PATH` указывают на существующие или создаваемые папки на диске Windows (например, `C:/ai-rag/data/...`).
   - OIDC-настройки (`OIDC_ISSUER_URI`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_REDIRECT_URI`, `OIDC_LOGOUT_REDIRECT_URI`) соответствуют вашим приложениям.

## Запуск
1. Откройте PowerShell в каталоге `windows-install/`.
2. Выполните скрипт подготовки и запуска:
   ```powershell
   ./setup.ps1
   ```
   Скрипт:
   - Подгрузит переменные из `.env` в текущую сессию.
   - Создаст каталоги для volume, если их еще нет.
   - Скачает необходимые образы (PostgreSQL, Keycloak, MinIO).
   - Запустит `docker compose up -d` с текущими настройками.

## Проверка
После успешного выполнения скрипта сервисы будут доступны по адресам:
- PostgreSQL: `localhost:${POSTGRES_PORT}` (по умолчанию 5432)
- Keycloak: `http://localhost:${KEYCLOAK_HTTP_PORT}` (по умолчанию 8080)
- MinIO API: `http://localhost:${MINIO_API_PORT}` (по умолчанию 9000)
- MinIO Console: `http://localhost:${MINIO_CONSOLE_PORT}` (по умолчанию 9001)

## Остановка
Чтобы остановить инфраструктуру, выполните:
```powershell
docker compose down
```
(команда должна выполняться из каталога `windows-install/` или с флагом `-f` на соответствующий файл `docker-compose.yml`).
