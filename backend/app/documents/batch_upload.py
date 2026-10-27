"""Shared validation for multi-file upload batches."""

from __future__ import annotations

from dataclasses import dataclass

from app.documents.validation import UploadValidationError, validate_upload


@dataclass(frozen=True)
class BatchFileInput:
    filename: str
    data: bytes


@dataclass(frozen=True)
class AcceptedBatchItem:
    filename: str
    data: bytes
    mime_type: str
    size_bytes: int


@dataclass(frozen=True)
class RejectedBatchItem:
    filename: str
    code: str
    message: str


@dataclass(frozen=True)
class BatchValidationResult:
    accepted: list[AcceptedBatchItem]
    rejected: list[RejectedBatchItem]


def validate_file_batch(
    files: list[BatchFileInput],
    *,
    max_files: int,
    max_file_bytes: int,
    max_batch_bytes: int,
    allowed_types: set[str],
) -> BatchValidationResult:
    accepted: list[AcceptedBatchItem] = []
    rejected: list[RejectedBatchItem] = []

    if len(files) > max_files:
        rejected.append(
            RejectedBatchItem(
                filename="",
                code="ATTACHMENT_FILE_LIMIT_REACHED" if max_files <= 5 else "BATCH_FILE_LIMIT_REACHED",
                message=f"A maximum of {max_files} files can be uploaded at once.",
            )
        )
        return BatchValidationResult(accepted=[], rejected=rejected)

    running = 0
    for item in files:
        name = item.filename or "upload"
        try:
            validated = validate_upload(
                filename=name,
                data=item.data,
                max_bytes=max_file_bytes,
                allowed_types=allowed_types,
            )
        except UploadValidationError as exc:
            code = exc.code
            if code == "unsupported_type":
                code = "ATTACHMENT_TYPE_UNSUPPORTED"
            elif code == "file_too_large":
                code = "ATTACHMENT_FILE_TOO_LARGE"
            rejected.append(RejectedBatchItem(filename=name, code=code, message=exc.message))
            continue

        if running + validated.size_bytes > max_batch_bytes:
            rejected.append(
                RejectedBatchItem(
                    filename=name,
                    code="BATCH_SIZE_LIMIT_REACHED",
                    message="Total batch size exceeds the configured limit.",
                )
            )
            continue

        running += validated.size_bytes
        accepted.append(
            AcceptedBatchItem(
                filename=name,
                data=item.data,
                mime_type=validated.mime_type,
                size_bytes=validated.size_bytes,
            )
        )

    return BatchValidationResult(accepted=accepted, rejected=rejected)
