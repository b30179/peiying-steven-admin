from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
from uuid import uuid4


@dataclass(frozen=True)
class PublishedFile:
    path: Path
    storage_key: str
    sha256: str
    size_bytes: int


class LocalAppendOnlyFileStorage:
    def __init__(self, data_root: Path, namespace: str, extension: str, verifier) -> None:
        self.data_root = data_root.resolve()
        self.namespace = namespace.strip("/")
        self.extension = extension.lstrip(".")
        self.verifier = verifier
        self.temp_root = self.data_root / ".tmp" / self.namespace
        self.final_root = self.data_root / "generated" / self.namespace

    @staticmethod
    def safe_segment(value: str) -> str:
        segment = re.sub(r'[\\/:*?"<>|]+', "_", value.strip())
        segment = re.sub(r"\s+", "_", segment)
        return segment[:80] or "document"

    def storage_template(self, object_id: str, filename_template: str) -> str:
        return f"generated/{self.namespace}/{object_id}/{filename_template}"

    def publish(self, *, object_id: str, version_number: int, filename: str, render) -> PublishedFile:
        temporary = self.temp_root / object_id / f"v{version_number}-{uuid4()}.{self.extension}"
        target = self.final_root / object_id / filename
        temporary.parent.mkdir(parents=True, exist_ok=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            render(temporary)
            self.verifier(temporary)
            digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
            size_bytes = temporary.stat().st_size
            if target.exists():
                raise FileExistsError(f"版本文件已存在，拒绝覆盖：{target}")
            os.link(temporary, target)
            temporary.unlink()
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return PublishedFile(target, target.relative_to(self.data_root).as_posix(), digest, size_bytes)

    def resolve(self, storage_key: str) -> Path:
        target = (self.data_root / storage_key).resolve()
        if target != self.data_root and self.data_root not in target.parents:
            raise ValueError("storage_key_outside_root")
        return target

    def inspect_existing(self, storage_key: str) -> PublishedFile:
        target = self.resolve(storage_key)
        if not target.is_file():
            raise FileNotFoundError(target)
        self.verifier(target)
        return PublishedFile(
            target,
            storage_key,
            hashlib.sha256(target.read_bytes()).hexdigest(),
            target.stat().st_size,
        )
