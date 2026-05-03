"""JSON-file backed persistence for the Content Studio.

The MVP plan calls for a simple file-backed store that we can swap for
SQLite later. Each entity is one JSON file under ``base_dir`` so the
state is easy to inspect and version-control during development.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

from api.schemas.content_studio import (
    DraftSet,
    RenderRecord,
    Script,
    Storyboard,
    Topic,
    TopicStatus,
)

_DEFAULT_BASE_DIR = Path(os.environ.get("PIXELLE_CONTENT_STUDIO_DATA_DIR", "data/content_studio"))


def _isoformat(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


class ContentStudioStorage:
    """Thread-safe JSON-file storage.

    All entities are keyed by ``topic_id`` except topics themselves which
    are keyed by their own ``id``. Reads return new model instances, so
    callers may mutate without disturbing on-disk state.
    """

    def __init__(self, base_dir: Path | str | None = None):
        self.base_dir = Path(base_dir) if base_dir else _DEFAULT_BASE_DIR
        self._lock = threading.RLock()
        self._ensure_dirs()

    # ----- internal helpers -------------------------------------------------

    def _ensure_dirs(self) -> None:
        for sub in ("topics", "drafts", "scripts", "storyboards", "renders"):
            (self.base_dir / sub).mkdir(parents=True, exist_ok=True)

    def _path(self, kind: str, key: str) -> Path:
        # Sanitize the key so we never escape the base_dir.
        safe = key.replace("/", "_").replace("\\", "_")
        return self.base_dir / kind / f"{safe}.json"

    def _write(self, path: Path, model) -> None:
        payload = model.model_dump(mode="json")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with self._lock:
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2, default=_json_default)
            tmp.replace(path)

    def _read(self, path: Path, model_cls):
        if not path.exists():
            return None
        with self._lock:
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        return model_cls.model_validate(data)

    def _list(self, kind: str, model_cls) -> List:
        directory = self.base_dir / kind
        if not directory.exists():
            return []
        items = []
        for path in sorted(directory.glob("*.json")):
            try:
                items.append(model_cls.model_validate(json.loads(path.read_text("utf-8"))))
            except Exception:
                # Skip malformed files but keep loading the rest.
                continue
        return items

    # ----- topics -----------------------------------------------------------

    def save_topic(self, topic: Topic) -> Topic:
        topic.updated_at = datetime.utcnow()
        self._write(self._path("topics", topic.id), topic)
        return topic

    def get_topic(self, topic_id: str) -> Optional[Topic]:
        return self._read(self._path("topics", topic_id), Topic)

    def list_topics(
        self,
        date: Optional[str] = None,
        statuses: Optional[Iterable[TopicStatus]] = None,
    ) -> List[Topic]:
        topics = self._list("topics", Topic)
        if date is not None:
            topics = [t for t in topics if t.date == date]
        if statuses is not None:
            allow = {TopicStatus(s) for s in statuses}
            topics = [t for t in topics if t.status in allow]
        topics.sort(key=lambda t: (t.priority, t.created_at), reverse=True)
        return topics

    def delete_topics_for_date(self, date: str) -> int:
        count = 0
        for topic in self.list_topics(date=date):
            path = self._path("topics", topic.id)
            if path.exists():
                path.unlink()
                count += 1
        return count

    # ----- drafts -----------------------------------------------------------

    def save_drafts(self, drafts: DraftSet) -> DraftSet:
        drafts.updated_at = datetime.utcnow()
        self._write(self._path("drafts", drafts.topic_id), drafts)
        return drafts

    def get_drafts(self, topic_id: str) -> Optional[DraftSet]:
        return self._read(self._path("drafts", topic_id), DraftSet)

    # ----- scripts ----------------------------------------------------------

    def save_script(self, script: Script) -> Script:
        self._write(self._path("scripts", script.topic_id), script)
        return script

    def get_script(self, topic_id: str) -> Optional[Script]:
        return self._read(self._path("scripts", topic_id), Script)

    # ----- storyboards ------------------------------------------------------

    def save_storyboard(self, storyboard: Storyboard) -> Storyboard:
        self._write(self._path("storyboards", storyboard.topic_id), storyboard)
        return storyboard

    def get_storyboard(self, topic_id: str) -> Optional[Storyboard]:
        return self._read(self._path("storyboards", topic_id), Storyboard)

    # ----- renders ----------------------------------------------------------

    def save_render(self, render: RenderRecord) -> RenderRecord:
        render.updated_at = datetime.utcnow()
        self._write(self._path("renders", render.topic_id), render)
        return render

    def get_render(self, topic_id: str) -> Optional[RenderRecord]:
        return self._read(self._path("renders", topic_id), RenderRecord)

    def list_renders(self) -> List[RenderRecord]:
        return self._list("renders", RenderRecord)


# Module-level singleton for use by routers / pages.
_storage_singleton: Optional[ContentStudioStorage] = None
_singleton_lock = threading.Lock()


def get_storage() -> ContentStudioStorage:
    global _storage_singleton
    if _storage_singleton is None:
        with _singleton_lock:
            if _storage_singleton is None:
                _storage_singleton = ContentStudioStorage()
    return _storage_singleton


def set_storage(storage: ContentStudioStorage) -> None:
    """Replace the singleton (for tests)."""
    global _storage_singleton
    with _singleton_lock:
        _storage_singleton = storage


def reset_storage() -> None:
    global _storage_singleton
    with _singleton_lock:
        _storage_singleton = None
