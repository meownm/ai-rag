# Keycloak token lifecycle and client flows

Этот документ фиксирует настройки Keycloak для короткоживущих access-токенов,
ротации refresh-токенов и механизмов отзыва при смене пароля/ролей, а также
обязательные шаги для веб-клиента и Telegram-бота.

## Настройки в Keycloak
1. **Realm → Tokens**
   - `Access Token Lifespan`: 15m (короткие access-токены).
   - `Client Session Idle`: 30m, `Client Session Max`: 8h — ограничивает время
     жизни refresh-токенов (обычный интерактивный сценарий).
   - `Offline Session Idle`: 30d, `Offline Session Max`: 60d — только если нужны
     долгоживущие офлайн-сессии для фоновых задач.
2. **Clients → <app> → Advanced**
   - Включить `Revoke Refresh Token` и `Refresh Token Max Reuse = 0` для ротации
     refresh-токенов и защиты от повторного использования.
   - `Logout Session Required` = ON, чтобы фронты дергали backchannel logout.
   - `Frontchannel Logout URL`/`Backchannel Logout URL` задать на веб и API
     (соответственно `https://<web>/auth/logout` и `https://<api>/oidc/logout`).
3. **Пароль / отзыв доступа**
   - При смене пароля: `Users → <user> → Logout All Sessions` мгновенно
     инвалидирует refresh-токены и offline-сессии.
   - При отзыве роли/клиента: `Clients → <app> → Sessions → Logout all` для
     конкретного клиента или `Realms → Sessions → Logout all` для массового
     отзыва.
   - Опционально включить `Realm → Security Defenses → Brute Force Detection` и
     `User action tokens` (5–10 минут) для безопасной смены пароля.

## Веб: login/refresh/logout
- **Login (PKCE):** использовать Authorization Code Flow c PKCE; хранить
  `access_token` в памяти, `refresh_token` в `httpOnly`/`Secure` cookie с
  `SameSite=Lax`.
- **Refresh:** при получении 401/403 или за 2 минуты до `exp` отправлять
  `/protocol/openid-connect/token` с `grant_type=refresh_token`. Учитывать, что
  Keycloak при `Revoke Refresh Token` отдаёт новый refresh-токен — перезаписывать
  cookie.
- **Logout:**
  1. Отправить POST на `end_session_endpoint` с `refresh_token`.
  2. Очистить локальное состояние (in-memory access token + cookie) и редирект
     на публичный экран. При Backchannel logout Keycloak сам дергает URL, который
     должен удалить cookies/sessions на фронте через API.

## Telegram-бот
- **Хранение токенов:** при линковке Telegram ↔ пользователь сохранять пару
  (`access_token`, `refresh_token`, `refresh_expires_at`) в Redis или Postgres,
  привязав к `telegram_id`. В бот-коде использовать refresh-токен с запасом 60 с
  до истечения `exp` (см. `KnowledgeBaseAPI`).
- **Автообновление:** перед каждым вызовом API проверять `exp`; если access
  истёк, вызвать refresh. При ошибке 400/401 на refresh — сбросить связку и
  перелогиниться по паролю/Device Code.
- **Инвалидация при разлинковке:** команда `/unlink` (или webhook из веба)
  удаляет запись в хранилище и вызывает `KnowledgeBaseAPI.invalidate_tokens()`,
  чтобы старые access/refresh-токены больше не использовались. Также можно
  дернуть Keycloak backchannel logout для пользователя, если известен его
  `session_state`.
