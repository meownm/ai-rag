import logging
import shelve
import uuid
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional

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
    kb_web_login_url: str
    token_store_path: str = "telegram_tokens.db"

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


class StoredTokens(BaseModel):
    access_token: str
    refresh_token: str
    access_expires_at: datetime


class TokenStorage:
    def __init__(self, path: str):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def get(self, telegram_id: int) -> Optional[StoredTokens]:
        with shelve.open(self._path.as_posix()) as db:
            raw = db.get(str(telegram_id))
            return StoredTokens(**raw) if raw else None

    def set(self, telegram_id: int, tokens: StoredTokens):
        with shelve.open(self._path.as_posix()) as db:
            db[str(telegram_id)] = tokens.model_dump()

    def delete(self, telegram_id: int):
        with shelve.open(self._path.as_posix()) as db:
            db.pop(str(telegram_id), None)


class MissingTokensError(Exception):
    """Поднявается, когда для пользователя нет сохранённых токенов."""


class TokenRefreshError(Exception):
    """Ошибка обновления токена."""


class KnowledgeBaseAPI:
    def __init__(self, base_url: str, token_store_path: str):
        self._base_url = base_url.rstrip("/")
        self._api_client = httpx.AsyncClient(timeout=30.0)
        self._token_store = TokenStorage(token_store_path)

    @staticmethod
    def _decode_exp(token: str) -> datetime:
        payload = jwt.decode(token, "", options={"verify_signature": False, "verify_aud": False})
        return datetime.fromtimestamp(payload["exp"], tz=timezone.utc)

    async def save_tokens(self, telegram_id: int, access_token: str, refresh_token: str) -> StoredTokens:
        tokens = StoredTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            access_expires_at=self._decode_exp(access_token),
        )
        self._token_store.set(telegram_id, tokens)
        return tokens

    def has_tokens(self, telegram_id: int) -> bool:
        return self._token_store.get(telegram_id) is not None

    async def start_link(self, telegram_id: int, username: Optional[str]) -> str:
        response = await self._api_client.post(
            f"{self._base_url}/telegram/links/start",
            json={"telegram_id": telegram_id, "username": username},
        )
        response.raise_for_status()
        # Обнуляем сохранённые токены, чтобы форсировать повторную авторизацию
        self._token_store.delete(telegram_id)
        return response.json()["state_token"]

    async def exchange_state_for_tokens(self, telegram_id: int, state_token: str) -> StoredTokens:
        response = await self._api_client.post(f"{self._base_url}/telegram/links/{state_token}/exchange")
        response.raise_for_status()
        data = response.json()
        return await self.save_tokens(
            telegram_id=telegram_id,
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
        )

    async def _refresh_tokens(self, telegram_id: int, refresh_token: str) -> StoredTokens:
        try:
            response = await self._api_client.post(
                f"{self._base_url}/token/refresh", json={"refresh_token": refresh_token}
            )
            response.raise_for_status()
            data = response.json()
            return await self.save_tokens(
                telegram_id=telegram_id,
                access_token=data["access_token"],
                refresh_token=data["refresh_token"],
            )
        except httpx.HTTPStatusError as exc:
            self._token_store.delete(telegram_id)
            logger.error("Could not refresh token for %s: %s", telegram_id, exc.response.text)
            raise TokenRefreshError from exc

    async def _get_valid_tokens(self, telegram_id: int) -> StoredTokens:
        tokens = self._token_store.get(telegram_id)
        if not tokens:
            raise MissingTokensError()

        if tokens.access_expires_at <= datetime.now(timezone.utc) + timedelta(seconds=60):
            tokens = await self._refresh_tokens(telegram_id, tokens.refresh_token)
        return tokens

    async def _authorized_request(self, method: str, path: str, telegram_id: int, **kwargs):
        tokens = await self._get_valid_tokens(telegram_id)
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {tokens.access_token}"
        return await self._api_client.request(method, f"{self._base_url}{path}", headers=headers, **kwargs)

    async def ensure_tokens(self, telegram_id: int) -> StoredTokens:
        return await self._get_valid_tokens(telegram_id)

    # --- CRUD методы для API ---
    async def get_status(self, telegram_id: int) -> StatusResponse:
        r = await self._authorized_request("GET", "/status", telegram_id)
        r.raise_for_status(); return StatusResponse.model_validate(r.json())

    async def get_all_items(self, telegram_id: int) -> list[ItemResponse]:
        r = await self._authorized_request("GET", "/items", telegram_id)
        r.raise_for_status(); return [ItemResponse.model_validate(item) for item in r.json()]

    async def search_items(self, query: str, telegram_id: int) -> list[ItemResponse]:
        r = await self._authorized_request("GET", "/items/search", telegram_id, params={"q": query})
        r.raise_for_status(); return [ItemResponse.model_validate(item) for item in r.json()]

    async def get_item(self, item_uuid: str, telegram_id: int) -> Optional[ItemResponse]:
        try:
            r = await self._authorized_request("GET", f"/items/{item_uuid}", telegram_id)
            r.raise_for_status()
            return ItemResponse.model_validate(r.json())
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def add_file(self, file_name: str, file_content: bytes, telegram_id: int) -> ItemResponse:
        files = {'file': (file_name, BytesIO(file_content), 'application/octet-stream')}
        r = await self._authorized_request("POST", "/files", telegram_id, files=files)
        r.raise_for_status(); return ItemResponse.model_validate(r.json())

    async def get_download_url(self, item_uuid: str, telegram_id: int) -> FileDownloadResponse:
        r = await self._authorized_request("GET", f"/files/{item_uuid}/download", telegram_id)
        r.raise_for_status(); return FileDownloadResponse.model_validate(r.json())

    async def delete_item(self, item_uuid: str, telegram_id: int):
        r = await self._authorized_request("DELETE", f"/items/{item_uuid}", telegram_id)
        r.raise_for_status()

    async def set_status(self, item_uuid: str, new_status: str, telegram_id: int):
        r = await self._authorized_request("PATCH", f"/items/{item_uuid}/status", telegram_id, json={"status": new_status})
        r.raise_for_status()

    async def close(self):
        await self._api_client.aclose()


kb_api = KnowledgeBaseAPI(settings.kb_api_base_url, settings.token_store_path)


def _message_target(update: Update):
    if update.message:
        return update.message
    if update.callback_query:
        return update.callback_query.message
    return None


async def ensure_tokens_available(update: Update) -> Optional[int]:
    telegram_id = update.effective_user.id if update.effective_user else None
    target = _message_target(update)
    if telegram_id is None:
        if target:
            await target.reply_text("Не удалось определить пользователя Telegram для привязки.")
        return None

    try:
        await kb_api.ensure_tokens(telegram_id)
        return telegram_id
    except MissingTokensError:
        if target:
            await target.reply_text(
                "Ваш Telegram ещё не привязан к аккаунту. Используйте команду /link для связывания."
            )
    except TokenRefreshError:
        if target:
            await target.reply_text(
                "Не удалось обновить авторизацию. Пожалуйста, выполните привязку заново через /link."
            )
    return None

# ===============================================================================
# ОБРАБОТЧИКИ КОМАНД И СООБЩЕНИЙ
# ===============================================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я бот для управления базой знаний. Используйте 'Меню' для просмотра команд.")


async def link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_user = update.effective_user
    if not telegram_user:
        await update.message.reply_text("Не удалось определить пользователя Telegram.")
        return

    state_token = await kb_api.start_link(telegram_user.id, telegram_user.username)
    login_link = f"{settings.kb_web_login_url}?state={state_token}"
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔑 Открыть страницу входа", url=login_link)],
            [InlineKeyboardButton("✅ Проверить подтверждение", callback_data=f"check_link:{state_token}")],
        ]
    )
    await update.message.reply_text(
        "Связываем ваш аккаунт с базой знаний. Перейдите по ссылке, авторизуйтесь и нажмите 'Проверить подтверждение'.",
        reply_markup=keyboard,
    )

async def list_items_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = await ensure_tokens_available(update)
    if not telegram_id:
        return

    await update.message.reply_text("Получаю список элементов...")
    items = await kb_api.get_all_items(telegram_id)
    await show_item_list_with_buttons(update.message, items, "Текущие элементы в базе знаний:")

async def search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query: await update.message.reply_text("Укажите запрос: /search <запрос>"); return
    await update.message.reply_text(f"Ищу элементы по запросу '{query}'...")
    telegram_id = await ensure_tokens_available(update)
    if not telegram_id:
        return

    items = await kb_api.search_items(query, telegram_id)
    await show_item_list_with_buttons(update.message, items, f"Результаты поиска по запросу '{query}':")

async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = await ensure_tokens_available(update)
    if not telegram_id:
        return
    document = update.message.document
    await update.message.reply_text("Загружаю файл в базу знаний...")
    tg_file = await document.get_file()
    file_content = await tg_file.download_as_bytearray()
    result = await kb_api.add_file(file_name=document.file_name, file_content=bytes(file_content), telegram_id=telegram_id)
    await update.message.reply_text(f"✅ Файл '{result.item_name}' успешно добавлен!")

async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = await ensure_tokens_available(update)
    if not telegram_id:
        return
    await update.message.reply_text("🔍 Собираю статистику...")
    stats = await kb_api.get_status(telegram_id)
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

    if action == "check_link":
        state_token = item_uuid
        try:
            await kb_api.exchange_state_for_tokens(query.from_user.id, state_token)
            await query.edit_message_text(
                text="✅ Аккаунт подтвержден! Теперь можно использовать команды бота.",
                reply_markup=None,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                await query.edit_message_text(
                    text="Привязка еще не подтверждена. Завершите вход в веб-приложении и повторите проверку.",
                    reply_markup=query.message.reply_markup,
                )
            else:
                raise
        except TokenRefreshError:
            await query.edit_message_text(
                text="Не удалось получить токены. Попробуйте создать новую ссылку командой /link.",
                reply_markup=None,
            )
        return

    telegram_id = await ensure_tokens_available(update)
    if not telegram_id:
        return

    item = await kb_api.get_item(item_uuid, telegram_id) if item_uuid else None

    if not item and action not in ["delete_execute"]:
        await query.edit_message_text(text="Элемент был удален или изменен.", reply_markup=None)
        return

    if action == "view":
        keyboard = get_item_actions_keyboard(item.item_uuid, item.item_type)
        await query.edit_message_text(text=f"Действия для:\n`{item.item_name}`", reply_markup=keyboard, parse_mode='Markdown')
    elif action == "get_link":
        response = await kb_api.get_download_url(item_uuid, telegram_id)
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("‹‹ Назад", callback_data=f"view:{item_uuid}")]])
        await query.edit_message_text(text=f"🔗 [Ссылка для скачивания]({response.download_url})\n_(действительна 1 час)_", reply_markup=keyboard, parse_mode='Markdown')
    elif action == "delete_confirm":
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Да, удалить", callback_data=f"delete_execute:{item_uuid}"), InlineKeyboardButton("❌ Отмена", callback_data=f"view:{item_uuid}")]])
        await query.edit_message_text(text="Вы уверены?", reply_markup=keyboard)
    elif action == "delete_execute":
        item = item or await kb_api.get_item(item_uuid, telegram_id)
        if not item:
            await query.edit_message_text(text="Элемент уже удалён или не найден.", reply_markup=None)
        else:
            await kb_api.delete_item(item_uuid, telegram_id)
            await query.edit_message_text(text="✅ Элемент удален.", reply_markup=None)
    elif action == "change_status_menu":
        buttons = [[InlineKeyboardButton(s.capitalize(), callback_data=f"set_status:{item_uuid}:{s}")] for s in StatusType.ALL]
        buttons.append([InlineKeyboardButton("‹‹ Назад", callback_data=f"view:{item_uuid}")])
        await query.edit_message_text(text="Выберите новый статус:", reply_markup=InlineKeyboardMarkup(buttons))
    elif action == "set_status":
        new_status = data[1]
        await kb_api.set_status(item_uuid, new_status, telegram_id)
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
        BotCommand("link", "Привязать аккаунт"),
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
    application.add_handler(CommandHandler("link", link))
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