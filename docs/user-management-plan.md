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

## Deliverables
- Code changes in each service per phase.
- Seed/default admin for bootstrap.
- Windows Docker Desktop setup assets under `windows-install/` (see new folder) to deploy Keycloak + dependencies quickly.
