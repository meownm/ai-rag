# scripts/setup-dev-windows.ps1
# Этот скрипт нужно запускать в PowerShell от имени администратора.

Write-Host "--- Шаг 1: Проверка и установка WSL (Windows Subsystem for Linux) ---" -ForegroundColor Green

# Проверяем, установлен ли WSL
if ($LASTEXITCODE -ne 0) 
{
    Write-Host "WSL не найден. Устанавливаем WSL с Ubuntu..." -ForegroundColor Yellow
    wsl --install -d Ubuntu
    Write-Host "WSL установлен. Пожалуйста, ПЕРЕЗАГРУЗИТЕ компьютер, а затем запустите этот скрипт снова." -ForegroundColor Cyan
    exit
} 
else {    Write-Host "WSL уже установлен."}

Write-Host "`n--- Шаг 2: Установка драйверов AMD для WSL ---" -ForegroundColor Green
Write-Host "Для работы GPU в WSL необходимы специальные драйверы." -ForegroundColor Yellow
Write-Host "Пожалуйста, скачайте и установите их с официального сайта AMD:" -ForegroundColor Yellow
Write-Host "https://www.amd.com/en/support/kb/release-notes/rn-rad-win-wsl-support" -ForegroundColor Cyan
Read-Host "Нажмите Enter, когда установите драйверы..."

Write-Host "`n--- Шаг 3: Завершение установки внутри WSL ---" -ForegroundColor Green
Write-Host "Отлично! Теперь откройте терминал Ubuntu (из меню 'Пуск')."
Write-Host "Внутри терминала Ubuntu перейдите в папку проекта и выполните следующую команду:" -ForegroundColor Cyan
Write-Host "./scripts/setup-dev-wsl.sh"