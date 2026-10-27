"""SQLAlchemy models for M1 metadata (PostgreSQL)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class WorkspaceRow(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    settings_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    projects: Mapped[list["ProjectRow"]] = relationship(back_populates="workspace")


class ProjectRow(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("workspace_id", "slug", name="uq_projects_workspace_slug"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    ossie_root_path: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    default_connector_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    workspace: Mapped[WorkspaceRow] = relationship(back_populates="projects")
    conversations: Mapped[list["ConversationRow"]] = relationship(back_populates="project")
    libraries: Mapped[list["LibraryRow"]] = relationship(back_populates="project")


class LibraryRow(Base):
    __tablename__ = "libraries"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_libraries_project_name"),
        Index("ix_libraries_workspace_project", "workspace_id", "project_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    project: Mapped[ProjectRow] = relationship(back_populates="libraries")
    documents: Mapped[list["DocumentRow"]] = relationship(back_populates="library")


class DocumentChunkRow(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        Index("ix_document_chunks_document", "document_id", "chunk_index"),
        Index("ix_document_chunks_library", "library_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    library_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("libraries.id"), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(String(512), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vector_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    document: Mapped["DocumentRow"] = relationship(back_populates="chunks")


class DocumentRow(Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_library", "library_id"),
        Index("ix_documents_project", "project_id"),
        Index("ix_documents_workspace", "workspace_id"),
        Index("ix_documents_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    library_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("libraries.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="UPLOADED", nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    library: Mapped[LibraryRow] = relationship(back_populates="documents")
    chunks: Mapped[list["DocumentChunkRow"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class ChatAttachmentRow(Base):
    __tablename__ = "chat_attachments"
    __table_args__ = (Index("ix_chat_attachments_project_session", "project_id", "session_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    session_id: Mapped[str] = mapped_column(String(128), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    display_name: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    processing_type: Mapped[str] = mapped_column(String(32), default="unstructured", nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ConversationRow(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("project_id", "external_session_id", name="uq_conversations_project_session"),
        Index("ix_conversations_last_message", "last_message_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    external_session_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    project: Mapped[ProjectRow] = relationship(back_populates="conversations")
    messages: Mapped[list["MessageRow"]] = relationship(back_populates="conversation")


class MessageRow(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation_created", "conversation_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="assistant", nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    route: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    strategy: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    conversation: Mapped[ConversationRow] = relationship(back_populates="messages")


class PromptRow(Base):
    __tablename__ = "prompts"
    __table_args__ = (
        Index("ix_prompts_key", "key"),
        Index("ix_prompts_scope", "scope"),
        Index("ix_prompts_workspace", "workspace_id"),
        Index("ix_prompts_project", "project_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workspaces.id"), nullable=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("prompt_versions.id", ondelete="SET NULL", use_alter=True, name="fk_prompts_active_version"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    versions: Mapped[list["PromptVersionRow"]] = relationship(
        back_populates="prompt",
        foreign_keys="PromptVersionRow.prompt_id",
        cascade="all, delete-orphan",
    )


class PromptVersionRow(Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (
        UniqueConstraint("prompt_id", "version_number", name="uq_prompt_versions_prompt_version"),
        Index("ix_prompt_versions_prompt", "prompt_id"),
        Index("ix_prompt_versions_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prompt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prompts.id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    prompt: Mapped[PromptRow] = relationship(
        back_populates="versions",
        foreign_keys=[prompt_id],
    )


class SkillRow(Base):
    __tablename__ = "skills"
    __table_args__ = (
        Index("ix_skills_key", "key"),
        Index("ix_skills_scope", "scope"),
        Index("ix_skills_workspace", "workspace_id"),
        Index("ix_skills_project", "project_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("skill_versions.id", ondelete="SET NULL", use_alter=True, name="fk_skills_active_version"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    versions: Mapped[list["SkillVersionRow"]] = relationship(
        back_populates="skill",
        foreign_keys="SkillVersionRow.skill_id",
        cascade="all, delete-orphan",
    )


class SkillVersionRow(Base):
    __tablename__ = "skill_versions"
    __table_args__ = (
        UniqueConstraint("skill_id", "version_number", name="uq_skill_versions_skill_version"),
        Index("ix_skill_versions_skill", "skill_id"),
        Index("ix_skill_versions_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    skill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    prompt_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    input_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    allowed_tools: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    skill: Mapped[SkillRow] = relationship(
        back_populates="versions",
        foreign_keys=[skill_id],
    )


class SemanticModelRow(Base):
    __tablename__ = "semantic_models"
    __table_args__ = (
        UniqueConstraint("project_id", "key", name="uq_semantic_models_project_key"),
        Index("ix_semantic_models_workspace", "workspace_id"),
        Index("ix_semantic_models_project", "project_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "semantic_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_semantic_models_active_version",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    versions: Mapped[list["SemanticVersionRow"]] = relationship(
        back_populates="semantic_model",
        foreign_keys="SemanticVersionRow.semantic_model_id",
        cascade="all, delete-orphan",
    )


class SemanticVersionRow(Base):
    __tablename__ = "semantic_versions"
    __table_args__ = (
        UniqueConstraint("semantic_model_id", "version_number", name="uq_semantic_versions_model_version"),
        Index("ix_semantic_versions_model", "semantic_model_id"),
        Index("ix_semantic_versions_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    semantic_model_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("semantic_models.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    runtime_adapter: Mapped[str | None] = mapped_column(String(64), nullable=True)
    runtime_artifact_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    runtime_artifact_checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    runtime_artifact_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_validation_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("semantic_validation_runs.id", use_alter=True, name="fk_semantic_versions_last_validation_run"),
        nullable=True,
    )
    activation_readiness: Mapped[str | None] = mapped_column(String(32), nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    semantic_model: Mapped[SemanticModelRow] = relationship(
        back_populates="versions",
        foreign_keys=[semantic_model_id],
    )


class SemanticEntityRow(Base):
    __tablename__ = "semantic_entities"
    __table_args__ = (
        UniqueConstraint("semantic_version_id", "key", name="uq_semantic_entities_version_key"),
        Index("ix_semantic_entities_version", "semantic_version_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    semantic_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("semantic_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    catalog: Mapped[str | None] = mapped_column(String(128), nullable=True)
    schema: Mapped[str | None] = mapped_column("schema", String(128), nullable=True)
    table_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    view_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    primary_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    connection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("connectors.id", ondelete="RESTRICT"),
        nullable=True,
    )
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)


class SemanticMetricRow(Base):
    __tablename__ = "semantic_metrics"
    __table_args__ = (
        UniqueConstraint("semantic_version_id", "key", name="uq_semantic_metrics_version_key"),
        Index("ix_semantic_metrics_version", "semantic_version_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    semantic_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("semantic_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_definition: Mapped[str | None] = mapped_column(Text, nullable=True)
    expression: Mapped[str] = mapped_column(Text, nullable=False)
    aggregation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_entity_key: Mapped[str] = mapped_column(String(128), nullable=False)
    format: Mapped[str | None] = mapped_column(String(64), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    synonyms: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)


class SemanticDimensionRow(Base):
    __tablename__ = "semantic_dimensions"
    __table_args__ = (
        UniqueConstraint("semantic_version_id", "key", name="uq_semantic_dimensions_version_key"),
        Index("ix_semantic_dimensions_version", "semantic_version_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    semantic_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("semantic_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_entity_key: Mapped[str] = mapped_column(String(128), nullable=False)
    source_column: Mapped[str] = mapped_column(String(256), nullable=False)
    data_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    synonyms: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)


class SemanticRelationshipRow(Base):
    __tablename__ = "semantic_relationships"
    __table_args__ = (
        UniqueConstraint("semantic_version_id", "key", name="uq_semantic_relationships_version_key"),
        Index("ix_semantic_relationships_version", "semantic_version_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    semantic_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("semantic_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    from_entity_key: Mapped[str] = mapped_column(String(128), nullable=False)
    to_entity_key: Mapped[str] = mapped_column(String(128), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(32), nullable=False)
    join_type: Mapped[str] = mapped_column(String(32), nullable=False)
    join_expression: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)


class SemanticTermRow(Base):
    __tablename__ = "semantic_terms"
    __table_args__ = (
        UniqueConstraint("semantic_version_id", "key", name="uq_semantic_terms_version_key"),
        Index("ix_semantic_terms_version", "semantic_version_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    semantic_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("semantic_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    term: Mapped[str] = mapped_column(String(256), nullable=False)
    definition: Mapped[str | None] = mapped_column(Text, nullable=True)
    synonyms: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    related_metric_keys: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    related_dimension_keys: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    related_entity_keys: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)


class SemanticValidationRunRow(Base):
    __tablename__ = "semantic_validation_runs"
    __table_args__ = (Index("ix_semantic_validation_runs_version", "semantic_version_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    semantic_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("semantic_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="full")
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    validator_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(256), nullable=True)


class SemanticValidationIssueRow(Base):
    __tablename__ = "semantic_validation_issues"
    __table_args__ = (Index("ix_semantic_validation_issues_run", "validation_run_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    validation_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("semantic_validation_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    object_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    object_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    remediation: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)


class SemanticRuntimeDeploymentRow(Base):
    __tablename__ = "semantic_runtime_deployments"
    __table_args__ = (
        Index("ix_semantic_runtime_deployments_model", "semantic_model_id"),
        Index("ix_semantic_runtime_deployments_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    semantic_model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("semantic_models.id", ondelete="CASCADE"), nullable=False)
    semantic_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("semantic_versions.id"), nullable=False)
    runtime_adapter: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_uri: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    previous_deployment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("semantic_runtime_deployments.id"),
        nullable=True,
    )
    source_validation_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    registry_version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    generator_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    health_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    manifest: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class SemanticRuntimeStateRow(Base):
    __tablename__ = "semantic_runtime_state"

    semantic_model_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("semantic_models.id", ondelete="CASCADE"),
        primary_key=True,
    )
    active_deployment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("semantic_runtime_deployments.id"),
        nullable=True,
    )
    previous_deployment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("semantic_runtime_deployments.id"),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class SemanticRuntimeEventRow(Base):
    __tablename__ = "semantic_runtime_events"
    __table_args__ = (Index("ix_semantic_runtime_events_deployment", "deployment_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deployment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("semantic_runtime_deployments.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SemanticTestCaseRow(Base):
    __tablename__ = "semantic_test_cases"
    __table_args__ = (Index("ix_semantic_test_cases_version", "semantic_version_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    semantic_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("semantic_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_metric_keys: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    expected_dimension_keys: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    expected_entity_keys: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    enabled: Mapped[bool] = mapped_column(default=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)


class ConnectorRow(Base):
    __tablename__ = "connectors"
    __table_args__ = (
        UniqueConstraint("workspace_id", "project_id", "key", name="uq_connectors_workspace_project_key"),
        Index("ix_connectors_workspace_project", "workspace_id", "project_id"),
        Index("ix_connectors_type", "connector_type"),
        Index("ix_connectors_status", "status"),
        Index("ix_connectors_enabled", "enabled"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    connector_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    enabled: Mapped[bool] = mapped_column(default=True)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    secret_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_test_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)


class AiProviderRow(Base):
    __tablename__ = "ai_providers"
    __table_args__ = (
        UniqueConstraint("workspace_id", "project_id", "key", name="uq_ai_providers_workspace_project_key"),
        Index("ix_ai_providers_workspace_project", "workspace_id", "project_id"),
        Index("ix_ai_providers_type", "provider_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(32), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    secret_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    enabled: Mapped[bool] = mapped_column(default=True)
    config_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_test_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    models: Mapped[list["AiModelRow"]] = relationship(back_populates="provider")


class AiModelRow(Base):
    __tablename__ = "ai_models"
    __table_args__ = (
        UniqueConstraint("workspace_id", "project_id", "key", name="uq_ai_models_workspace_project_key"),
        Index("ix_ai_models_provider", "provider_id"),
        Index("ix_ai_models_type", "model_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_providers.id", ondelete="RESTRICT"), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    model_id: Mapped[str] = mapped_column(String(256), nullable=False)
    model_type: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True)
    context_window: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    supports_streaming: Mapped[bool | None] = mapped_column(nullable=True)
    supports_tools: Mapped[bool | None] = mapped_column(nullable=True)
    supports_json_mode: Mapped[bool | None] = mapped_column(nullable=True)
    supports_vision: Mapped[bool | None] = mapped_column(nullable=True)
    config_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_test_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    provider: Mapped[AiProviderRow] = relationship(back_populates="models")


class ModelAssignmentRow(Base):
    __tablename__ = "model_assignments"
    __table_args__ = (
        UniqueConstraint("workspace_id", "project_id", "capability", name="uq_model_assignments_scope_capability"),
        Index("ix_model_assignments_model", "model_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    capability: Mapped[str] = mapped_column(String(64), nullable=False)
    model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_models.id", ondelete="RESTRICT"), nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class ModelTestRunRow(Base):
    __tablename__ = "model_test_runs"
    __table_args__ = (Index("ix_model_test_runs_created", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    provider_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_providers.id", ondelete="SET NULL"), nullable=True)
    model_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True)
    test_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    safe_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class UsageEventRow(Base):
    __tablename__ = "usage_events"
    __table_args__ = (Index("ix_usage_events_created", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    strategy: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    llm_calls: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
