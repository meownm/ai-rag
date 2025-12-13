import logging
import uuid
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any, Callable, Coroutine, Optional

import httpx
from jose import jwt
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from telegram import (BotCommand, InlineKeyboardButton, InlineKeyboardMarkup,
                      Update)
from telegram.error import TimedOut
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, MessageHandler, filters)

# --- Настройка логирования и конфигурация ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    telegram_bot_token: str
    kb_api_base_url: str
    kb_api_username: str
    kb_api_password: str
    class Config: env_file = ".env"
settings = Settings()

# --- Определяем статусы, чтобы не хардкодить строки ---
class StatusType:
    NEW = "new"; PROCESSING = "processing"; DONE = "done"; FAILED = "failed"
    ALL = [NEW, PROCESSING, DONE, FAILED]

# ===============================================================================
# Pydantic модели для ответов API
# ===============================================================================
class ItemResponse(BaseModel):
    item_uuid: uuid.UUID
    item_name: str
    item_type: str
    size: Optional[int] = None
    status: str
    operation: str
    operation_time: datetime

class FileDownloadResponse(BaseModel):
    download_url: str

class StatusResponse(BaseModel):
    files_uploaded_by_user: int
    documents_in_tenant: int
    chunks_in_tenant: int
    chunks_with_embedding: int
    chunks_with_metadata: int

# ===============================================================================
# Улучшенный КЛИЕНТ ДЛЯ KB API
# ===============================================================================
class BearerAuth(httpx.Auth):
    """Кастомный класс аутентификации для httpx для автоматического обновления токена."""
    def __init__(self, client: 'KnowledgeBaseAPI'):
        self._client = client

    async def async_auth_flow(self, request: httpx.Request):
        if not self._client.is_token_valid():
            await self._client._refresh_token()
        
        request.headers["Authorization"] = f"Bearer {self._client._token}"
        yield request

class KnowledgeBaseAPI:
    def __init__(self, base_url, username, password):
        self._base_url = base_url
        self._username = username
        self._password = password

        self._auth_client = httpx.AsyncClient(timeout=10.0)
        self._api_client = httpx.AsyncClient(timeout=30.0, auth=BearerAuth(self))

        self._token: Optional[str] = None
        self._token_expires: Optional[datetime] = None

    def is_token_valid(self) -> bool:
        """Проверяет, действителен ли токен, с запасом в 60 секунд."""
        return (
            self._token is not None and
            self._token_expires is not None and
            self._token_expires > (datetime.now(timezone.utc) + timedelta(seconds=60))
        )

    async def _refresh_token(self):
        """Обновляет токен, используя отдельный, простой HTTP-клиент."""
        logger.info("Refreshing auth token from KB API")
        try:
            response = await self._auth_client.post(f"{self._base_url}/token", data={"username": self._username, "password": self._password})
            response.raise_for_status()
            token_data = response.json()
            self._token = token_data["access_token"]
            payload = jwt.decode(self._token, "", options={"verify_signature": False, "verify_aud": False})
            self._token_expires = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
            logger.info(f"Token refreshed, valid until {self._token_expires}")
        except httpx.HTTPStatusError as e:
            logger.critical(f"FATAL: Could not get auth token: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.critical(f"FATAL: Could not get auth token due to network error: {e}")
            raise

    # --- CRUD методы для API ---
    async def get_status(self) -> StatusResponse:
        r = await self._api_client.get(f"{self._base_url}/status")
        r.raise_for_status(); return StatusResponse.model_validate(r.json())
        
    async def get_all_items(self) -> list[ItemResponse]:
        r = await self._api_client.get(f"{self._base_url}/items")
        r.raise_for_status(); return [ItemResponse.model_validate(item) for item in r.json()]

    async def search_items(self, query: str) -> list[ItemResponse]:
        r = await self._api_client.get(f"{self._base_url}/items/search", params={"q": query})
        r.raise_for_status(); return [ItemResponse.model_validate(item) for item in r.json()]

    async def get_item(self, item_uuid: str) -> Optional[ItemResponse]:
        try:
            r = await self._api_client.get(f"{self._base_url}/items/{item_uuid}")
            r.raise_for_status()
            return ItemResponse.model_validate(r.json())
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def add_file(self, file_name: str, file_content: bytes) -> ItemResponse:
        files = {'file': (file_name, BytesIO(file_content), 'application/octet-stream')}
        r = await self._api_client.post(f"{self._base_url}/files", files=files)
        r.raise_for_status(); return ItemResponse.model_validate(r.json())
        
    async def get_download_url(self, item_uuid: str) -> FileDownloadResponse:
        r = await self._api_client.get(f"{self._base_url}/files/{item_uuid}/download")
        r.raise_for_status(); return FileDownloadResponse.model_validate(r.json())

    async def delete_item(self, item_uuid: str):
        r = await self._api_client.delete(f"{self._base_url}/items/{item_uuid}")
        r.raise_for_status()

    async def set_status(self, item_uuid: str, new_status: str):
        r = await self._api_client.patch(f"{self._base_url}/items/{item_uuid}/status", json={"status": new_status})
        r.raise_for_status()

    async def close(self):
        await self._auth_client.aclose()
        await self._api_client.aclose()

kb_api = KnowledgeBaseAPI(settings.kb_api_base_url, settings.kb_api_username, settings.kb_api_password)

# ===============================================================================
# ОБРАБОТЧИКИ КОМАНД И СООБЩЕНИЙ
# ===============================================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я бот для управления базой знаний. Используйте 'Меню' для просмотра команд.")

async def list_items_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Получаю список элементов...")
    items = await kb_api.get_all_items()
    await show_item_list_with_buttons(update.message, items, "Текущие элементы в базе знаний:")

async def search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query: await update.message.reply_text("Укажите запрос: /search <запрос>"); return
    await update.message.reply_text(f"Ищу элементы по запросу '{query}'...")
    items = await kb_api.search_items(query)
    await show_item_list_with_buttons(update.message, items, f"Результаты поиска по запросу '{query}':")

async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    await update.message.reply_text("Загружаю файл в базу знаний...")
    tg_file = await document.get_file()
    file_content = await tg_file.download_as_bytearray()
    result = await kb_api.add_file(file_name=document.file_name, file_content=bytes(file_content))
    await update.message.reply_text(f"✅ Файл '{result.item_name}' успешно добавлен!")

async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Собираю статистику...")
    stats = await kb_api.get_status()
    message = (
        f"📊 **Статистика Базы Знаний**\n\n"
        f"🗂️ Документов в тенанте: *{stats.documents_in_tenant}*\n"
        f"🧩 Всего чанков в тенанте: *{stats.chunks_in_tenant}*\n"
        f"✨ Чанков с эмбеддингами: *{stats.chunks_with_embedding}*\n"
        f"📝 Чанков с метаданными: *{stats.chunks_with_metadata}*\n\n"
        f"👤 **Ваша личная статистика**\n"
        f"📤 Файлов загружено вами: *{stats.files_uploaded_by_user}*"
    )
    await update.message.reply_text(message, parse_mode='Markdown')

# ===============================================================================
# ОБРАБОТЧИК НАЖАТИЙ НА КНОПКИ (CALLBACKS)
# ===============================================================================
async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, *data = query.data.split(':')
    item_uuid = data[0] if data else None

    item = await kb_api.get_item(item_uuid) if item_uuid else None

    if not item and action not in ["delete_execute"]:
        await query.edit_message_text(text="Элемент был удален или изменен.", reply_markup=None)
        return

    if action == "view":
        keyboard = get_item_actions_keyboard(item.item_uuid, item.item_type)
        await query.edit_message_text(text=f"Действия для:\n`{item.item_name}`", reply_markup=keyboard, parse_mode='Markdown')
    elif action == "get_link":
        response = await kb_api.get_download_url(item_uuid)
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("‹‹ Назад", callback_data=f"view:{item_uuid}")]])
        await query.edit_message_text(text=f"🔗 [Ссылка для скачивания]({response.download_url})\n_(действительна 1 час)_", reply_markup=keyboard, parse_mode='Markdown')
    elif action == "delete_confirm":
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Да, удалить", callback_data=f"delete_execute:{item_uuid}"), InlineKeyboardButton("❌ Отмена", callback_data=f"view:{item_uuid}")]])
        await query.edit_message_text(text="Вы уверены?", reply_markup=keyboard)
    elif action == "delete_execute":
        item = item or await kb_api.get_item(item_uuid)
        if not item:
            await query.edit_message_text(text="Элемент уже удалён или не найден.", reply_markup=None)
        else:
            await kb_api.delete_item(item_uuid)
            await query.edit_message_text(text="✅ Элемент удален.", reply_markup=None)
    elif action == "change_status_menu":
        buttons = [[InlineKeyboardButton(s.capitalize(), callback_data=f"set_status:{item_uuid}:{s}")] for s in StatusType.ALL]
        buttons.append([InlineKeyboardButton("‹‹ Назад", callback_data=f"view:{item_uuid}")])
        await query.edit_message_text(text="Выберите новый статус:", reply_markup=InlineKeyboardMarkup(buttons))
    elif action == "set_status":
        new_status = data[1]
        await kb_api.set_status(item_uuid, new_status)
        await query.edit_message_text(text=f"✅ Статус изменен на '{new_status}'.", reply_markup=None)

# ===============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ И ОБРАБОТЧИКИ ОШИБОК
# ===============================================================================
async def show_item_list_with_buttons(message: Update.message, items: list[ItemResponse], title: str):
    if not items: await message.reply_text("Ничего не найдено."); return
    keyboard = []
    for item in items:
        emoji = "📄" if item.item_type == 'file' else "🔗"
        keyboard.append([InlineKeyboardButton(f"{emoji} {item.item_name}", callback_data=f"view:{item.item_uuid}")])
    await message.reply_text(title, reply_markup=InlineKeyboardMarkup(keyboard))

def get_item_actions_keyboard(item_uuid: uuid.UUID, item_type: str) -> InlineKeyboardMarkup:
    buttons = []
    if item_type == "file":
        buttons.append([InlineKeyboardButton("🔗 Получить ссылку", callback_data=f"get_link:{item_uuid}")])
    buttons.extend([
        [InlineKeyboardButton("🔄 Изменить статус", callback_data=f"change_status_menu:{item_uuid}")],
        [InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_confirm:{item_uuid}")],
    ])
    return InlineKeyboardMarkup(buttons)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Глобальный обработчик ошибок."""
    error = context.error
    logger.error("Exception while handling an update:", exc_info=error)
    
    update_obj = update if isinstance(update, Update) else None
    if not update_obj: return

    message_target = None
    if update_obj.message: message_target = update_obj.message
    elif update_obj.callback_query: message_target = update_obj.callback_query.message

    text = "Произошла непредвиденная ошибка. Администратор уже уведомлен."
    if isinstance(error, TimedOut):
        text = "❌ Не удалось получить ответ от серверов Telegram. Пожалуйста, попробуйте еще раз."
    elif isinstance(error, httpx.HTTPStatusError):
        text = f"❌ Ошибка при обращении к нашему API: {error.response.status_code}\n`{error.response.text}`"
    elif isinstance(error, httpx.RequestError):
        text = "❌ Не удалось подключиться к нашему API. Сервис может быть временно недоступен."

    if message_target:
        await message_target.reply_text(text, parse_mode='Markdown')

async def post_init(application: Application):
    """Устанавливает меню команд после старта бота."""
    commands = [
        BotCommand("start", "Начало работы"),
        BotCommand("list", "Показать все элементы"),
        BotCommand("search", "Искать элемент"),
        BotCommand("status", "Показать статистику")
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands menu has been set.")

async def post_shutdown(application: Application):
    """Закрывает HTTP-клиенты после остановки бота."""
    await kb_api.close()
    logger.info("HTTP clients closed.")

# ===============================================================================
# ТОЧКА ВХОДА
# ===============================================================================
def main():
    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .connect_timeout(10.0)
        .read_timeout(30.0)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("list", list_items_handler))
    application.add_handler(CommandHandler("search", search_handler))
    application.add_handler(CommandHandler("status", status_handler))
    application.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    
    application.add_error_handler(error_handler)
    
    logger.info("Starting bot...")
    application.run_polling()

if __name__ == "__main__":
    main()
