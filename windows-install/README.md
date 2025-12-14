# Windows Docker Desktop Setup for User Management Stack

This folder contains assets to run the identity-enabled stack on Windows with Docker Desktop (WSL2 backend). It pulls Keycloak, Postgres, MinIO, and service images, then starts them with sensible defaults for local development.

## Prerequisites
1. **Windows 10/11** with **WSL2** enabled and Docker Desktop installed.
2. At least **8 GB RAM** allocated to Docker Desktop and **4 CPUs**.
3. PowerShell 7+ (or Windows Terminal) to run the setup script.
4. Optional: `git` to clone this repository; otherwise download the release archive.

## Contents
- `setup.ps1` — downloads images, prepares volumes, and runs `docker compose`.
- `.env.example` — environment variables for Keycloak, Postgres, MinIO, and service OIDC settings.
- `compose.yml` — Docker Compose file targeting Docker Desktop with Windows paths.

## Quick Start
1. Copy `.env.example` to `.env` and adjust secrets as needed.
2. From PowerShell (Run as Administrator if required for file permissions), execute:

   ```powershell
   ./setup.ps1
   ```

3. After containers start, open Keycloak at http://localhost:8080, log in with the admin credentials from `.env`, and import or create the realm/clients for:
   - knowledge_base_api (resource server)
   - knowledge-search-api (resource server)
   - rag-search-ui (public PKCE client)
   - knowledge_base_bot (device/deep link client)

4. Seed a default organization/admin using your service migrations/seed scripts; ensure the admin account matches the Keycloak admin user.

## Volumes and Paths
The compose file stores data under `${USERPROFILE}\.rag\volumes\`. Adjust `compose.yml` if you prefer different locations.

## Troubleshooting
- If ports 8080 or 5432 are in use, update them in `.env` and `compose.yml` consistently.
- Run `wsl --shutdown` and restart Docker Desktop if volume mounts fail.
- Ensure virtualization is enabled in BIOS/UEFI for WSL2.
