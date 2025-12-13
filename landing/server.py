import http.server
import socketserver
import os

# Настройки
PORT = 9090
WEB_DIR = os.path.join(os.path.dirname(__file__), 'dist')

# Переходим в каталог с файлами
os.chdir(WEB_DIR)

# Запуск сервера
handler = http.server.SimpleHTTPRequestHandler

with socketserver.TCPServer(("", PORT), handler) as httpd:
    print(f"Сервер запущен на http://localhost:{PORT}")
    print(f"Каталог: {WEB_DIR}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановка сервера...")
        httpd.server_close()
