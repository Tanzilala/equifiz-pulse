"""Tiny TTL file cache for JSON payloads.

Disk layout: <root>/<sha1(key)>.json with metadata header line.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Optional


class JsonFileCache:
    def __init__(self, root: Path, *, default_ttl: float = 300.0) -> None:
        self.root = Path(root)
        self.default_ttl = default_ttl
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        h = hashlib.sha1(key.encode("utf-8")).hexdigest()
        return self.root / f"{h}.json"

    def get(self, key: str, *, ttl: Optional[float] = None) -> Optional[Any]:
        ttl = self.default_ttl if ttl is None else ttl
        p = self._path(key)
        if not p.exists():
            return None
        try:
            with p.open("r", encoding="utf-8") as f:
                meta = json.loads(f.readline())
                if time.time() - float(meta["t"]) > ttl:
                    return None
                return json.load(f)
        except (OSError, ValueError, KeyError):
            return None

    def set(self, key: str, value: Any) -> None:
        p = self._path(key)
        with p.open("w", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.time(), "k": key}) + "\n")
            json.dump(value, f)
