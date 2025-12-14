# Knowledge Search API

Сервис FastAPI для поиска по базе знаний с поддержкой векторного поиска, графа знаний и истории диалогов.

## Аутентификация OIDC
* Эндпоинты `/v1/answer` и `/v1/history` требуют `Authorization: Bearer <token>`.
* Токен валидируется по JWKS и проверяется на аудиторию и issuer.
* Поддерживаемые переменные окружения:
  - `OIDC_AUDIENCE` — идентификатор клиента (aud) для проверки токена.
  - `OIDC_ISSUER` — URL issuer (realm) Identity Provider.
  - `OIDC_JWKS_URL` — ссылка на JWKS с открытыми ключами.
  - `OIDC_JWKS_TTL` — (опционально) TTL кеша JWKS в секундах, по умолчанию `300`.
  - `OIDC_USER_ID_CLAIM` — (опционально) claim с идентификатором пользователя, по умолчанию `sub`.
  - `OIDC_ORG_ID_CLAIM` — (опционально) claim с идентификатором организации, по умолчанию `org_id`.

## Идентификаторы пользователя и организации
`user_id` и `org_id` извлекаются из токена и сохраняются в таблицах `conversations`, `search_queries` и `search_results`. Они используются для:
* проверки владения перед продолжением диалога по `conversation_id`;
* фильтрации истории запросов по пользователю/организации;
* логирования результатов поиска с привязкой к пользователю и организации.

## CORS для web-клиента (PKCE)
Используйте переменную `CORS_ALLOWED_ORIGINS` (список через запятую), чтобы указать домены SPA-клиента. По умолчанию разрешены все источники (`*`). Пример:

```env
CORS_ALLOWED_ORIGINS=https://app.example.com,https://app.example.org
```

## Пример env для OIDC+PKCE
```env
OIDC_AUDIENCE=knowledge-search-api
OIDC_ISSUER=http://localhost:8080/realms/ai-rag
OIDC_JWKS_URL=http://localhost:8080/realms/ai-rag/protocol/openid-connect/certs
OIDC_USER_ID_CLAIM=sub
OIDC_ORG_ID_CLAIM=org_id
CORS_ALLOWED_ORIGINS=http://localhost:3000
```
