# User Management and Organization Integration Plan

This plan documents how to introduce centralized authentication/authorization, Telegram linking, and Windows installation assets given the clarified requirements.

## Clarified Requirements
- Implement in stages (phase-by-phase rollout) while keeping services aligned for eventual convergence.
- Web login and Telegram linking are developed in parallel.
- Each user belongs to exactly one tenant/organization (no multi-tenancy per user).
- For Telegram linking, capture `telegram_id` and `username` only.
- Provide a default admin account for initial bootstrap.

## Architecture Overview
- **Identity Provider**: Keycloak acting as the single OIDC provider for all services (knowledge base API, search API, web UI for answers, Telegram bot via device/deep link flow).
- **Tenant Model**: `Organization` maps 1:1 to a Keycloak realm or realm+client role namespace. Users have `idp_subject` and a foreign key to a single `organization_id`.
- **Authorization**: Roles stored as Keycloak client roles; JWT contains `org_id` and role claims. Services map `org_id` → internal `tenant_id` and enforce RBAC middleware.
- **Default Admin**: Seed script creates a Keycloak realm admin and a corresponding internal admin user tied to the bootstrap tenant.

## Implementation Phases
### Phase 1: OIDC Core and Organizations (knowledge_base_api)
- Add models/migrations: `Organization`, `User.idp_subject`, `UserOrganizationRole` (single-org constraint enforced), admin seeding.
- Middleware to validate Keycloak JWT, map `org_id` to tenant, and expose `current_user` with roles.
- Admin endpoints for creating an organization, inviting a user, and role assignment.

### Phase 2: Web Login & Telegram Linking (parallel)
- **Web**: PKCE login against Keycloak; session/token storage with `org_id` propagation on API requests.
- **Telegram Bot**: `/link` command issues a state token; deep link/web confirms the state and stores `telegram_id` + `username` in `user_telegram_links`; bot exchanges for user JWT to call APIs under the user context.

### Phase 3: Search API User Binding
- Add bearer-token validation; propagate `user_id`/`org_id` through conversations, history, and logging.
- Align CORS and OIDC client settings for the web answer UI.

## Data and Security Considerations
- Tokens must include `org_id`, `roles`, and `sub` (`idp_subject`).
- Enforce single-tenant membership at database and API levels.
- Audit trails log `user_id` and `organization_id` for all mutations and search interactions.
- Store only `telegram_id` and `username` from Telegram; no phone numbers or chats are persisted.

## Operational Scenarios and Runbooks
### Restore Access for Admin
1. Verify outage scope: check if the Keycloak admin UI is unreachable or only specific admin credentials fail.
2. If only credentials fail, use Keycloak CLI or pod exec to reset the admin password:
   - `kubectl exec -it <keycloak-pod> -- /opt/keycloak/bin/kc.sh set-password --username admin --new-password <new>`
   - Alternatively, set `KEYCLOAK_ADMIN` and `KEYCLOAK_ADMIN_PASSWORD` env vars and restart the pod/statefulset to re-seed the admin account.
3. Validate login to the master realm admin console and rotate the password immediately with a secure manager.
4. Review audit logs for suspicious activity and invalidate active sessions for the admin user.
5. Confirm downstream services can still obtain tokens (OIDC discovery and JWKS reachable) before closing the incident.

### Client Secret Rotation
1. Initiate a maintenance window and inventory the affected clients (knowledge_base_api, knowledge_search_api, rag-search-ui, Telegram bot linker).
2. In Keycloak, navigate to **Clients → <client> → Credentials → Regenerate Secret**. Record the new secret securely.
3. Update deployments per service:
   - API services: update `OIDC_CLIENT_SECRET` (or equivalent) in the secret/helm values, then roll pods.
   - Web PKCE clients: prefer public clients without secrets; if a confidential client is still used, update the backend gateway only.
   - Telegram linker: update the secret in the bot deployment/worker.
4. Deploy sequentially: update non-user-facing backends first, then UI/bot entry points.
5. Validate by performing a fresh login flow per client and checking token issuance + role claims.
6. Revoke the old secret in Keycloak and close the maintenance window.

### Certificate Updates
1. Determine certificate scope (public ingress TLS vs. internal mTLS). Export the new cert/key/CA bundle to the deployment repo or secret manager.
2. For ingress certificates, update the Kubernetes secret (e.g., `kubectl create secret tls ... --dry-run=client -o yaml | kubectl apply -f -`) and restart ingress pods if required.
3. For Keycloak signing keys (JWT), prefer key rotation via new active keys instead of replacement:
   - Add the new keypair in **Realm Settings → Keys → Providers → rsa-generated**.
   - Mark the new key as **Active**; keep the previous key as **Passive** for overlap until all services refresh JWKS.
4. For mutual TLS between services, update the truststore/keystore mounts and restart the corresponding pods.
5. Validate OIDC discovery (`/.well-known/openid-configuration`), JWKS propagation, and HTTPS termination from a client cluster node.

## Login FAQ (Common Errors)
- **"Invalid client" or `unauthorized_client`**: Check the client ID/secret match the realm config and that redirect URIs include the deployed domain (with correct scheme/port).
- **"Invalid redirect_uri"**: Ensure the exact callback URL is registered in Keycloak, including trailing slashes. For localhost testing, add both `http://localhost:<port>/callback` and `http://127.0.0.1:<port>/callback`.
- **PKCE code verifier mismatch**: Clear browser storage and retry; confirm the frontend stores the transient verifier and that proxies do not strip cookies/headers.
- **Clock skew / token expired immediately**: Sync time on cluster nodes and clients (NTP). Check that token TTLs are not overly short and that caches invalidate JWKS correctly.
- **"User not found in organization" after login**: Verify `org_id` claim exists in the JWT, the user is mapped to the organization in the DB, and that service-side org mapping tables are populated.
- **Telegram link fails after auth**: Confirm the bot state token is still valid, that the user has an existing account in the same org, and that the bot can reach the auth callback URL.

## New Organization Onboarding Checklist
- [ ] Create Keycloak realm/client for the organization with correct redirect URIs and roles.
- [ ] Seed default admin user for the realm and store credentials in the password manager.
- [ ] Create `Organization` entry in the primary database and map it to the realm/client identifiers.
- [ ] Configure OIDC client secrets (if confidential) and apply them to API/worker deployments via secrets management.
- [ ] Set up ingress/HTTPS endpoints for the organization domain; upload TLS certificates and validate.
- [ ] Configure Telegram bot linking (state token callback URL, allowed domains) if applicable.
- [ ] Run a full login flow (web UI + API token exchange) and verify role claims and org scoping in downstream services.
- [ ] Enable audit logging and verify log entries contain `user_id` and `organization_id` for mutations.
- [ ] Hand off a runbook and support contacts to the organization admins.

## Deliverables
- Code changes in each service per phase.
- Seed/default admin for bootstrap.
- Windows Docker Desktop setup assets under `windows-install/` (see new folder) to deploy Keycloak + dependencies quickly.
