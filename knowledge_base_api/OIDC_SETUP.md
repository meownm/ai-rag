# OIDC / Keycloak configuration

Эти настройки добавляют OIDC-аутентификацию через Keycloak и позволяют маппить `org_id` из JWT в `tenant_id` приложения.

## Переменные окружения

| Переменная | Описание |
| --- | --- |
| `OIDC_CLIENT_ID` | Идентификатор клиента Keycloak, указанного в настройках клиента. |
| `OIDC_ISSUER` | Полный адрес реалма Keycloak (например, `http://localhost:8080/realms/ai-rag`). |
| `OIDC_JWKS_URL` | Ссылка на документ JWKS клиента (`{issuer}/protocol/openid-connect/certs`). |

## Пример docker-compose для локального запуска

```yaml
version: "3.9"
services:
  keycloak:
    image: quay.io/keycloak/keycloak:24.0
    command: start-dev
    environment:
      KEYCLOAK_ADMIN: admin
      KEYCLOAK_ADMIN_PASSWORD: admin
    ports:
      - "8080:8080"

  api:
    build: .
    ports:
      - "8001:8001"
    env_file:
      - .env.docker
    environment:
      OIDC_CLIENT_ID: knowledge-base-api
      OIDC_ISSUER: http://keycloak:8080/realms/ai-rag
      OIDC_JWKS_URL: http://keycloak:8080/realms/ai-rag/protocol/openid-connect/certs
    depends_on:
      - keycloak
```

## Настройка клиента Keycloak
1. Создайте realm `ai-rag`.
2. Добавьте клиент `knowledge-base-api` типа `public` (или `confidential` с соответствующими секретами).
3. Разрешите поток `Standard Flow` и включите `Direct Access Grants` при необходимости.
4. В разделе `Client scopes` добавьте маппер claim `org_id` (String) и обеспечьте выдачу `roles`.
5. Убедитесь, что адреса `Valid Redirect URIs` и `Web origins` включают URL вашего API/UI.

JWT, который выдает Keycloak, должен содержать `sub` (используется как `User.idp_subject`) и claim `org_id` для выбора нужного тенанта.
