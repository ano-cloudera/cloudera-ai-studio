# Source monorepo extraction policy

**Source (reference / archive):** `~/Documents/Works/cloudera/enterprise-ai-poc`  
**Standalone copy:** `~/Documents/Works/cloudera/cloudera-ai-studio`

## Semantics

- Cloudera AI Studio was extracted with **copy semantics only**.
- Required application assets were **copied** into `cloudera-ai-studio` (`backend-dev` → `backend/`, `frontend-dev` → `frontend/`, plus shared `config/`, `deployment/`, `docs/`, `scripts/`, etc.).
- The source monorepo must **remain intact**. It hosts other workloads and shared assets unrelated to Cloudera AI Studio.

## Forbidden without explicit user approval

- Moving or renaming the entire `enterprise-ai-poc` tree (including temporary “isolation” `mv` tricks).
- Deleting or reorganizing unrelated root folders in `enterprise-ai-poc`.
- Broad `git restore .`, `git reset --hard`, or cleanup passes on the source repo.
- Symlinking standalone runtime (`.venv`, `node_modules`, app code) back into the monorepo.

## Isolation proof

Proving standalone independence must use **non-destructive** checks (path audits, process `cwd`, `sys.path`, grep of runtime trees).  
Do **not** hide the source repo by renaming its directory.

## Local secrets

- `.env` files are local-only and must not be copied blindly between repos.
- Restore or create `.env` from `.env.example` / `config/examples/` per environment.

## Audit (2026-10-18)

Source repo verification:

- `git ls-files --deleted`: empty
- All tracked paths present on disk (`ALL_TRACKED_FILES_PRESENT`)
- No `git status` deletions (`D`)
- Root and key directories (`backend-dev`, `frontend-dev`, `projects`, etc.) present
- Standalone copy directories present under `cloudera-ai-studio`

No selective git restoration was required; no extraction-related tracked deletions were found.
