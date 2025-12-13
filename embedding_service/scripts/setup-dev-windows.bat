@ECHO OFF
REM Устанавливаем кодировку UTF-8 для корректного отображения кириллицы
CHCP 65001 > NUL

ECHO --- Шаг 1: Проверка и установка WSL (Windows Subsystem for Linux) ---

REM Проверяем статус WSL. Перенаправляем вывод в NUL, чтобы скрыть его.
wsl --status > NUL 2>&1

REM Проверяем код ошибки последней команды. Если не 0, значит wsl не установлен.
IF %ERRORLEVEL% NEQ 0 (
    ECHO WSL не найден. Устанавливаем WSL с Ubuntu...
    wsl --install -d Ubuntu
    ECHO.
    ECHO WSL установлен. Пожалуйста, ПЕРЕЗАГРУЗИТЕ компьютер.
    ECHO После перезагрузки запустите этот скрипт снова.
    ECHO.
    PAUSE
    EXIT /B
) ELSE (
    ECHO WSL уже установлен.
)

ECHO.
ECHO --- Шаг 2: Установка драйверов AMD для WSL ---
ECHO Для работы GPU в WSL необходимы специальные драйверы.
ECHO Пожалуйста, скачайте и установите их с официального сайта AMD:
ECHO https://www.amd.com/en/support/kb/release-notes/rn-rad-win-wsl-support
ECHO.
ECHO Нажмите любую клавишу, когда установите драйверы...
PAUSE > NUL

ECHO.
ECHO --- Шаг 3: Завершение установки внутри WSL ---
ECHO Отлично! Теперь откройте терминал Ubuntu (из меню "Пуск").
ECHO Внутри терминала Ubuntu перейдите в папку проекта и выполните следующую команду:
ECHO ./scripts/setup-dev-wsl.sh
ECHO.
PAUSE