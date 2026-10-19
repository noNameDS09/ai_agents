"""Evidence storage adapter — local filesystem with S3-compatible interface.

Provides store/retrieve/hash operations for evidence files. Designed to be
swappable with an S3-compatible backend (boto3) without changing callers.

Storage layout:
  {storage_path}/{org_id}/{evidence_id}/{filename}
  Content hash (SHA-256) stored alongside for tamper detection.
"""

from __future__ import annotations

import hashlib
import logging
import os
import uuid
from pathlib import Path
from typing import BinaryIO, Optional

from ..config import compliance_settings

logger = logging.getLogger("compliance.services.evidence_store")

MAX_FILE_SIZE = compliance_settings.max_evidence_size_bytes


class EvidenceStore:
    """Local filesystem evidence store with S3-compatible interface."""

    def __init__(self, base_path: Optional[str] = None):
        self.base_path = Path(base_path or compliance_settings.evidence_storage_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _org_dir(self, org_id: uuid.UUID) -> Path:
        d = self.base_path / str(org_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _evidence_dir(self, org_id: uuid.UUID, evidence_id: uuid.UUID) -> Path:
        d = self._org_dir(org_id) / str(evidence_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def store(
        self,
        org_id: uuid.UUID,
        evidence_id: uuid.UUID,
        filename: str,
        data: bytes | BinaryIO,
        mime_type: Optional[str] = None,
    ) -> dict:
        """Store an evidence file. Returns storage metadata.

        Raises ValueError if file exceeds max size.
        """
        if hasattr(data, "read"):
            data = data.read()

        if len(data) > MAX_FILE_SIZE:
            raise ValueError(
                f"File size {len(data)} exceeds maximum {MAX_FILE_SIZE} bytes"
            )

        content_hash = hashlib.sha256(data).hexdigest()
        evidence_dir = self._evidence_dir(org_id, evidence_id)
        file_path = evidence_dir / filename
        file_path.write_bytes(data)

        # Store hash alongside
        (evidence_dir / f"{filename}.sha256").write_text(content_hash)

        logger.info(
            "Stored evidence %s (%d bytes, sha256=%s)",
            evidence_id, len(data), content_hash[:12],
        )
        return {
            "storage_uri": str(file_path),
            "content_sha256": content_hash,
            "size_bytes": len(data),
            "mime_type": mime_type,
        }

    def retrieve(self, org_id: uuid.UUID, evidence_id: uuid.UUID, filename: str) -> bytes:
        """Retrieve an evidence file by org, evidence ID, and filename."""
        file_path = self._evidence_dir(org_id, evidence_id) / filename
        if not file_path.exists():
            raise FileNotFoundError(f"Evidence file not found: {file_path}")
        return file_path.read_bytes()

    def verify_hash(self, org_id: uuid.UUID, evidence_id: uuid.UUID, filename: str) -> bool:
        """Verify that the stored file matches its recorded hash."""
        evidence_dir = self._evidence_dir(org_id, evidence_id)
        file_path = evidence_dir / filename
        hash_path = evidence_dir / f"{filename}.sha256"

        if not file_path.exists() or not hash_path.exists():
            return False

        data = file_path.read_bytes()
        stored_hash = hash_path.read_text().strip()
        computed_hash = hashlib.sha256(data).hexdigest()
        return stored_hash == computed_hash

    def delete(self, org_id: uuid.UUID, evidence_id: uuid.UUID) -> None:
        """Delete an evidence directory. Use with caution."""
        import shutil
        evidence_dir = self._evidence_dir(org_id, evidence_id)
        if evidence_dir.exists():
            shutil.rmtree(evidence_dir)
            logger.info("Deleted evidence %s", evidence_id)

    def list_files(self, org_id: uuid.UUID, evidence_id: uuid.UUID) -> list[str]:
        """List files in an evidence directory."""
        evidence_dir = self._evidence_dir(org_id, evidence_id)
        if not evidence_dir.exists():
            return []
        return [f.name for f in evidence_dir.iterdir() if not f.name.endswith(".sha256")]