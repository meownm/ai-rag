# run-docker.ps1

function Write-Host-Colored {
    param([string]$Message, [string]$Color)
    Write-Host $Message -ForegroundColor $Color
}

Write-Host-Colored "===================================================" "Cyan"
Write-Host-Colored "     Knowledge Base API - Docker Setup (External Mode) " "Cyan"
Write-Host-Colored "===================================================" "Cyan"
Write-Host ""

# 1. Проверка статуса Docker
Write-Host-Colored "[*] 1/3: Проверка статуса Docker..." "Yellow"
docker info > $null
if ($? -ne 0) {
    Write-Host-Colored "[!] Docker Desktop не запущен. Пожалуйста, запустите его и повторите попытку." "Red"
    exit 1
}
Write-Host-Colored "[V] Docker Desktop запущен." "Green"
Write-Host ""

# 2. Сборка Docker-образа
Write-Host-Colored "[*] 2/3: Сборка Docker-образа для API... (Может занять время при первом запуске)" "Yellow"
docker-compose build
if ($? -ne 0) {
    Write-Host-Colored "[!] Ошибка при сборке Docker-образа. Проверьте вывод выше." "Red"
    exit 1
}
Write-Host-Colored "[V] Сборка успешно завершена." "Green"
Write-Host ""

# 3. Запуск API сервиса
Write-Host-Colored "[*] 3/3: Запуск API сервиса..." "Yellow"
docker-compose up -d
if ($? -ne 0) {
    Write-Host-Colored "[!] Ошибка при запуске контейнера." "Red"
    exit 1
}
Write-Host-Colored "[V] Сервис API запущен в фоновом режиме." "Green"
Write-Host ""

Write-Host-Colored "===================================================" "Cyan"
Write-Host-Colored "          ✨ УСТАНОВКА УСПЕШНО ЗАВЕРШЕНА ✨         " "Cyan"
Write-Host-Colored "===================================================" "Cyan"
Write-Host ""
Write-Host-Colored "Сервис API подключается к вашим существующим контейнерам." "White"
Write-Host-Colored "  -  FastAPI API:           http://localhost:8001" "White"
Write-Host-Colored "  - Документация (Swagger):    http://localhost:8001/docs" "White"
Write-Host ""
Write-Host-Colored "Полезные команды:" "White"
Write-Host-Colored "  - Посмотреть логи API:      docker logs -f kb_api" "White"
Write-Host-Colored "  - Остановить API сервис:    docker-compose down" "White"
Write-Host ""