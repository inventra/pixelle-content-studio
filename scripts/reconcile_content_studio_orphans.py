#!/usr/bin/env python3
"""Repair orphaned Content Studio artifacts after topic IDs changed.

Typical recovery case: a daily re-ingest replaced a topic with a new UUID,
leaving drafts/scripts/storyboards/renders on the old topic_id. This script
matches orphaned records back to a live topic, renames files, updates the
embedded ``topic_id`` field, and optionally advances the topic status to match
recovered artifacts.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TOPIC_STATUS_ORDER = {
    "candidate": 0,
    "selected": 1,
    "drafted": 2,
    "draft_approved": 3,
    "script_ready": 4,
    "storyboard_ready": 5,
    "render_queued": 6,
    "render_running": 7,
    "render_completed": 8,
    "render_failed": 8,
    "archived": 9,
}


@dataclass
class TopicRecord:
    path: Path
    data: dict[str, Any]

    @property
    def id(self) -> str:
        return self.data["id"]

    @property
    def title(self) -> str:
        return str(self.data.get("title") or "")

    @property
    def date(self) -> str:
        return str(self.data.get("date") or "")

    @property
    def status(self) -> str:
        return str(self.data.get("status") or "candidate")


@dataclass
class ArtifactRecord:
    kind: str
    path: Path
    data: dict[str, Any]

    @property
    def topic_id(self) -> str:
        return str(self.data.get("topic_id") or self.path.stem)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text("utf-8"))


def _save_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _extract_title(artifact: ArtifactRecord) -> str | None:
    if artifact.kind == "drafts":
        text = str(artifact.data.get("substack_draft") or "")
        m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        if m:
            return m.group(1).strip()
    if artifact.kind == "scripts":
        angle = str(artifact.data.get("angle") or "").strip()
        if angle:
            return angle
    if artifact.kind == "renders":
        maybe = artifact.data.get("title") or artifact.data.get("topic_title")
        if maybe:
            return str(maybe).strip()
    return None


def _normalize(s: str | None) -> str:
    return (s or "").strip().casefold()


def _artifact_rank(kind: str, data: dict[str, Any]) -> int:
    if kind == "drafts":
        return TOPIC_STATUS_ORDER["draft_approved" if data.get("approved_for_video") else "drafted"]
    if kind == "scripts":
        return TOPIC_STATUS_ORDER["script_ready"]
    if kind == "storyboards":
        return TOPIC_STATUS_ORDER["storyboard_ready"]
    if kind == "renders":
        status = str(data.get("status") or "render_queued")
        return TOPIC_STATUS_ORDER.get(status, TOPIC_STATUS_ORDER["render_queued"])
    return 0


def _rank_to_status(rank: int) -> str:
    pairs = sorted(TOPIC_STATUS_ORDER.items(), key=lambda kv: kv[1])
    best = "candidate"
    for status, value in pairs:
        if value <= rank:
            best = status
    return best


def _match_topic(artifact: ArtifactRecord, topics: list[TopicRecord]) -> TopicRecord | None:
    title = _normalize(_extract_title(artifact))
    if title:
        exact = [t for t in topics if _normalize(t.title) == title]
        if len(exact) == 1:
            return exact[0]
        return None
    if len(topics) == 1:
        return topics[0]
    return None


def _repair(base_dir: Path, apply: bool) -> dict[str, Any]:
    topics_dir = base_dir / "topics"
    topics = [TopicRecord(p, _load_json(p)) for p in sorted(topics_dir.glob("*.json"))]
    live_topic_ids = {t.id for t in topics}

    artifacts: list[ArtifactRecord] = []
    for kind in ["drafts", "scripts", "storyboards", "renders"]:
        for p in sorted((base_dir / kind).glob("*.json")):
            artifacts.append(ArtifactRecord(kind, p, _load_json(p)))

    groups: dict[str, list[ArtifactRecord]] = {}
    for a in artifacts:
        if a.topic_id in live_topic_ids:
            continue
        groups.setdefault(a.topic_id, []).append(a)

    repaired = []
    unmatched = []
    for orphan_topic_id, group in groups.items():
        target = None
        for artifact in group:
            target = _match_topic(artifact, topics)
            if target:
                break
        if not target:
            unmatched.append({"orphan_topic_id": orphan_topic_id, "artifacts": [a.path.name for a in group]})
            continue

        highest_rank = TOPIC_STATUS_ORDER.get(target.status, 0)
        item_summary = {
            "orphan_topic_id": orphan_topic_id,
            "target_topic_id": target.id,
            "target_title": target.title,
            "artifacts": [],
        }
        for artifact in group:
            old_path = artifact.path
            new_path = old_path.with_name(f"{target.id}.json")
            artifact.data["topic_id"] = target.id
            item_summary["artifacts"].append({"kind": artifact.kind, "from": old_path.name, "to": new_path.name})
            highest_rank = max(highest_rank, _artifact_rank(artifact.kind, artifact.data))
            if apply:
                _save_json(old_path, artifact.data)
                if old_path != new_path:
                    if new_path.exists():
                        new_path.unlink()
                    shutil.move(str(old_path), str(new_path))

        desired_status = _rank_to_status(highest_rank)
        item_summary["status_before"] = target.status
        item_summary["status_after"] = desired_status
        if apply and TOPIC_STATUS_ORDER.get(desired_status, 0) > TOPIC_STATUS_ORDER.get(target.status, 0):
            target.data["status"] = desired_status
            _save_json(target.path, target.data)
        repaired.append(item_summary)

    return {
        "ok": True,
        "base_dir": str(base_dir),
        "apply": apply,
        "topics": len(topics),
        "orphan_groups": len(groups),
        "repaired_groups": len(repaired),
        "unmatched_groups": len(unmatched),
        "repaired": repaired,
        "unmatched": unmatched,
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Repair orphaned Pixelle Content Studio records")
    p.add_argument("--base-dir", default="data/content_studio", help="Content Studio data directory")
    p.add_argument("--apply", action="store_true", help="Write changes instead of dry-run")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = _repair(Path(args.base_dir), apply=args.apply)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["unmatched_groups"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
