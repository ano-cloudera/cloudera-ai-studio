from __future__ import annotations

import uuid
from contextvars import ContextVar, Token

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.prompt_management.sources import DatabasePromptSource, FilePromptSource
from app.prompt_management.types import EffectivePrompt

_prompt_ctx: ContextVar[tuple[uuid.UUID | None, uuid.UUID | None] | None] = ContextVar(
    "prompt_resolution_context",
    default=None,
)

_session_var: ContextVar[Session | None] = ContextVar("prompt_resolver_session", default=None)


def get_resolver_session() -> Session | None:
    return _session_var.get()


def set_resolver_session(session: Session | None) -> Token:
    return _session_var.set(session)


def reset_resolver_session(token: Token) -> None:
    try:
        _session_var.reset(token)
    except ValueError:
        # TestClient / thread-pool handlers may exit in a different context than set().
        _session_var.set(None)


def set_prompt_resolution_context(
    workspace_id: uuid.UUID | None,
    project_id: uuid.UUID | None,
) -> Token:
    return _prompt_ctx.set((workspace_id, project_id))


def reset_prompt_resolution_context(token: Token) -> None:
    try:
        _prompt_ctx.reset(token)
    except ValueError:
        _prompt_ctx.set(None)


def get_prompt_resolution_context() -> tuple[uuid.UUID | None, uuid.UUID | None]:
    ctx = _prompt_ctx.get()
    if ctx is None:
        return None, None
    return ctx


class PromptResolver:
    def __init__(self, settings: Settings, session: Session | None = None) -> None:
        self._settings = settings
        self._session = session or get_resolver_session()
        self._files = FilePromptSource()

    def resolve(
        self,
        prompt_key: str,
        *,
        workspace_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
    ) -> EffectivePrompt:
        ws = workspace_id
        proj = project_id
        if ws is None and proj is None:
            ws, proj = get_prompt_resolution_context()

        chain: list[str] = ["project", "workspace", "global", "file"]
        if self._session is not None and self._uses_postgres():
            db = DatabasePromptSource(self._session)
            content, source = db.get_active_content(
                prompt_key=prompt_key,
                workspace_id=ws,
                project_id=proj,
            )
            if content is not None and source is not None:
                idx = chain.index(source) if source in chain else 0
                return EffectivePrompt(
                    prompt_key=prompt_key,
                    content=content,
                    source=source,
                    chain=chain[: idx + 1],
                )

        file_content = self._files.get(prompt_key)
        if file_content is None:
            file_content = ""
        return EffectivePrompt(
            prompt_key=prompt_key,
            content=file_content,
            source="file",
            chain=["project", "workspace", "global", "file"],
        )

    def _uses_postgres(self) -> bool:
        return (
            self._settings.state_store.strip().lower() == "postgres"
            and bool((self._settings.database_url or "").strip())
        )


def resolve_prompt_text(
    settings: Settings,
    prompt_key: str,
    *,
    session: Session | None = None,
    workspace_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
) -> str:
    resolver = PromptResolver(settings, session=session)
    return resolver.resolve(prompt_key, workspace_id=workspace_id, project_id=project_id).content
