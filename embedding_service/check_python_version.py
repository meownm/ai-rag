# check_python_version.py
import sys

# --- Configuration ---
# Эти значения передаются как аргументы командной строки из .bat файла.
# sys.argv[0] - это имя самого скрипта.
# sys.argv[1] - первый аргумент (MIN_MINOR_VERSION).
# sys.argv[2] - второй аргумент (MAX_EXCLUSIVE_MINOR_VERSION).
try:
    MIN_MINOR_VERSION = int(sys.argv[1])
    MAX_EXCLUSIVE_MINOR_VERSION = int(sys.argv[2])
except (IndexError, ValueError):
    # Эта ошибка не должна появляться при правильном вызове из .bat,
    # но это хорошая практика для защиты от некорректного использования.
    print("[ERROR] Internal script error: Missing or invalid version arguments for check_python_version.py.")
    sys.exit(2) # Используем код ошибки 2 для диагностики проблем с самим скриптом.

# --- Check Logic ---
current_version = sys.version_info

# Проверяем, что основная версия Python - 3
is_major_ok = (current_version.major == 3)

# Проверяем, что минорная версия находится в заданном диапазоне.
# Например, >= 10 и < 12, что означает 10 или 11.
is_minor_ok = (current_version.minor >= MIN_MINOR_VERSION and current_version.minor < MAX_EXCLUSIVE_MINOR_VERSION)

# Если обе проверки прошли успешно, выходим с кодом 0 (успех).
if is_major_ok and is_minor_ok:
    sys.exit(0)
# В противном случае, выходим с кодом 1 (ошибка).
else:
    sys.exit(1)