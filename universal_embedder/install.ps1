# install.ps1
# Скрипт для установки зависимостей проекта через Poetry, включая специфику PyTorch.
# Для запуска требуется Windows PowerShell в режиме администратора.

$ErrorActionPreference = "Stop"

# Проверка установки Poetry
try {
    Write-Host "Проверка установки Poetry..."
    poetry --version
} catch {
    Write-Host "Poetry не найден. Установите Poetry, затем повторите. (pip install poetry)" -ForegroundColor Red
    exit 1
}

# --- Получение текущей версии Python ---
try {
    # Получаем версию Python, которую использует Poetry
    $pythonVersion = (poetry run python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
    Write-Host "Обнаружена версия Python: $pythonVersion" -ForegroundColor Cyan
} catch {
    Write-Host "Не удалось определить версию Python. Проверьте, что Poetry настроен корректно." -ForegroundColor Red
    exit 1
}

# --- 1. Установка базовых зависимостей ---
Write-Host "`nУстановка базовых зависимостей (Poetry install)..." -ForegroundColor Yellow
poetry install --no-root

# --- 2. Выбор версии PyTorch и Scipy ---
Write-Host "`nВыберите версию PyTorch для установки (группа: local-ml):" -ForegroundColor Yellow
Write-Host "1. PyTorch CPU (Надежность)."
Write-Host "2. PyTorch CUDA (Для дискретных GPU NVIDIA)."
Write-Host "3. PyTorch DirectML (Рекомендуется для AMD/Intel iGPU)."
$choice = Read-Host "Введите номер выбора (по умолчанию 3)"

if (-not $choice) { $choice = 3 }

# Массив пакетов, которые нужно удалить перед установкой PyTorch/DML
$packagesToUninstall = "torch", "torchvision", "torchaudio", "scipy", "torch-directml"

switch ($choice) {
    "1" {
        Write-Host "Выбран PyTorch CPU. Установка..." -ForegroundColor Green
        
        poetry run pip uninstall $packagesToUninstall -y | Out-Null
        poetry run pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
        # Установка оставшихся ML-зависимостей
        poetry install --no-root --only local-ml
    }
    "2" {
        Write-Host "Выбран PyTorch CUDA. Проверьте версию CUDA (должна быть установлена)!" -ForegroundColor Green
        $cuda_version = Read-Host "Введите версию CUDA (например, 'cu121' для CUDA 12.1):"
        if (-not $cuda_version) { $cuda_version = "cu121" }
        
        Write-Host "Установка PyTorch с поддержкой CUDA $cuda_version..." -ForegroundColor Green
        poetry run pip uninstall $packagesToUninstall -y | Out-Null
        poetry run pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/$cuda_version
        poetry install --no-root --only local-ml
    }
    "3" {
        # --- ПРОВЕРКА СОВМЕСТИМОСТИ PYTHON ДЛЯ DIRECTML ---
        if ($pythonVersion -ne "3.9" -and $pythonVersion -ne "3.10") {
             Write-Host "!!! КРИТИЧЕСКАЯ ОШИБКА: DirectML официально поддерживает только Python 3.9 и 3.10. !!!" -ForegroundColor Red
             Write-Host "Ваша версия ($pythonVersion) несовместима. Пожалуйста, создайте виртуальное окружение с Python 3.10 и запустите скрипт снова." -ForegroundColor Red
             exit 1 # БЛОКИРУЕМ УСТАНОВКУ
        }
        
        Write-Host "Выбран PyTorch DirectML. Рекомендуется для AMD iGPU (8945HS)!" -ForegroundColor Green
        
        Write-Host "Удаление существующего PyTorch-стека..."
        poetry run pip uninstall $packagesToUninstall -y | Out-Null
        
        Write-Host "Установка совместимого PyTorch-стека (с torch-directml)..." -ForegroundColor Green
        # Установка torch, torchvision, torchaudio, и torch-directml в одной команде 
        poetry run pip install torch torchvision torchaudio torch-directml --extra-index-url https://download.pytorch.org/whl/cpu
        
        # Установка оставшихся ML-зависимостей
        poetry install --no-root --only local-ml

        
        Write-Host "Проверка установки DirectML..."
        try {
            poetry run python -c "import torch; print('DirectML Status:', hasattr(torch, 'dml') and torch.dml.is_available())"
        } catch {
            Write-Host "Не удалось проверить DirectML. (Проверьте, что вы используете Python 3.10.)" -ForegroundColor Red
        }
    }
    default {
        Write-Host "Неверный выбор. Повторите запуск скрипта." -ForegroundColor Red
        exit 1
    }
}

Write-Host "`nУстановка завершена. Готово к запуску." -ForegroundColor Green