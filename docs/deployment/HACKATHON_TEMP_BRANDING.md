# Temporary hackathon branding — Anywhere AI Studio

**Anywhere AI Studio** is a temporary hackathon branding layer. The underlying product, repository, APIs, and persistence remain **Cloudera AI Studio**.

## Enable (local / frontend CAI build)

1. Logo asset (committed): `frontend/public/branding/anywhere-ai-logo.png`
2. Merge into `frontend/.env.local` from [`config/examples/hackathon-branding.frontend.env`](../../config/examples/hackathon-branding.frontend.env)
3. Restart Next dev server (`npm run dev`) or rebuild for production.

## Revert after hackathon

In `frontend/.env.local`, restore Cloudera defaults from `frontend/.env.example`:

- `NEXT_PUBLIC_PRODUCT_NAME=Cloudera AI Studio`
- `NEXT_PUBLIC_APP_NAME=Cloudera AI Studio`
- `NEXT_PUBLIC_PRODUCT_LOGO` / `NEXT_PUBLIC_APP_LOGO` → `/Logo.png` (or remove keys to use code defaults)

No backend or repo rename required.

## CAI frontend application

Set the same `NEXT_PUBLIC_*` variables on the **Frontend** CAI Application environment (build-time for Next.js). Keep backend env unchanged.

## What was NOT changed

- Repository name, Python packages, DB tables, API routes, internal config keys, deployment topology.
