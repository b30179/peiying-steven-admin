from __future__ import annotations

import hashlib
import os
from pathlib import Path
from threading import RLock
from typing import Protocol


class DocumentFileStorage(Protocol):
    def put(self, storage_key: str, content: bytes, expected_sha256: str) -> None: ...

    def read(self, storage_key: str) -> bytes | None: ...


class InMemoryDocumentFileStorage:
    def __init__(self) -> None:
        self._content: dict[str, bytes] = {}
        self._lock = RLock()

    def put(self, storage_key: str, content: bytes, expected_sha256: str) -> None:
        _verify_hash(content, expected_sha256)
        with self._lock:
            existing = self._content.get(storage_key)
            if existing is not None and existing != content:
                raise FileExistsError("document_storage_key_conflict")
            self._content[storage_key] = bytes(content)

    def read(self, storage_key: str) -> bytes | None:
        with self._lock:
            content = self._content.get(storage_key)
            return bytes(content) if content is not None else None


class LocalAppendOnlyDocumentFileStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def put(self, storage_key: str, content: bytes, expected_sha256: str) -> None:
        _verify_hash(content, expected_sha256)
        target = self._target(storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest() != expected_sha256:
                raise FileExistsError("document_storage_key_conflict")
            return
        temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != expected_sha256:
                raise ValueError("document_storage_hash_mismatch")
            os.link(temporary, target)
        except FileExistsError:
            if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != expected_sha256:
                raise FileExistsError("document_storage_key_conflict")
        finally:
            temporary.unlink(missing_ok=True)

    def read(self, storage_key: str) -> bytes | None:
        target = self._target(storage_key)
        return target.read_bytes() if target.is_file() else None

    def _target(self, storage_key: str) -> Path:
        target = (self.root / storage_key).resolve()
        if target == self.root or self.root not in target.parents:
            raise ValueError("document_storage_key_outside_root")
        return target


def _verify_hash(content: bytes, expected_sha256: str) -> None:
    if hashlib.sha256(content).hexdigest() != expected_sha256:
        raise ValueError("document_storage_hash_mismatch")
