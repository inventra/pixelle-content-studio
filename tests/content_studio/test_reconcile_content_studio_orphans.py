from __future__ import annotations

import json
from pathlib import Path

from scripts.reconcile_content_studio_orphans import _repair


def _write(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_repair_relinks_orphaned_draft_and_script_and_advances_status(tmp_path):
    base = tmp_path / "content_studio"
    _write(
        base / "topics/live-topic.json",
        {
            "id": "live-topic",
            "date": "2026-05-03",
            "title": "Open Design 爆紅：把 coding agent 直接當設計引擎",
            "summary": "x",
            "why_it_matters": "y",
            "source": {"source_type": "obsidian"},
            "recommended_formats": ["substack", "video"],
            "priority": 70,
            "status": "candidate",
            "notes": None,
            "created_at": "2026-05-03T00:00:00",
            "updated_at": "2026-05-03T00:00:00",
        },
    )
    _write(
        base / "drafts/orphan-topic.json",
        {
            "topic_id": "orphan-topic",
            "substack_draft": "# Open Design 爆紅：把 coding agent 直接當設計引擎\n\nbody",
            "facebook_draft": "fb",
            "line_draft": "line",
            "editor_notes": "",
            "approved_for_video": True,
            "created_at": "2026-05-03T00:00:00",
            "updated_at": "2026-05-03T00:00:00",
        },
    )
    _write(
        base / "scripts/orphan-topic.json",
        {
            "topic_id": "orphan-topic",
            "angle": "Open Design 爆紅：把 coding agent 直接當設計引擎",
            "duration_target": 45,
            "hook": "hook",
            "body": "body",
            "cta": "cta",
            "voice_style": "calm-narrator",
            "created_at": "2026-05-03T00:00:00",
        },
    )

    result = _repair(base, apply=True)
    assert result["repaired_groups"] == 1
    assert result["unmatched_groups"] == 0

    repaired_draft = json.loads((base / "drafts/live-topic.json").read_text("utf-8"))
    repaired_script = json.loads((base / "scripts/live-topic.json").read_text("utf-8"))
    topic = json.loads((base / "topics/live-topic.json").read_text("utf-8"))

    assert repaired_draft["topic_id"] == "live-topic"
    assert repaired_script["topic_id"] == "live-topic"
    assert topic["status"] == "script_ready"
    assert not (base / "drafts/orphan-topic.json").exists()
    assert not (base / "scripts/orphan-topic.json").exists()


def test_repair_reports_unmatched_orphans_without_writing(tmp_path):
    base = tmp_path / "content_studio"
    _write(
        base / "topics/live-topic.json",
        {
            "id": "live-topic",
            "date": "2026-05-03",
            "title": "Different Title",
            "summary": "x",
            "why_it_matters": "y",
            "source": {"source_type": "obsidian"},
            "recommended_formats": [],
            "priority": 50,
            "status": "candidate",
            "notes": None,
            "created_at": "2026-05-03T00:00:00",
            "updated_at": "2026-05-03T00:00:00",
        },
    )
    _write(
        base / "scripts/orphan-topic.json",
        {
            "topic_id": "orphan-topic",
            "angle": "Unmatched Title",
            "duration_target": 45,
            "hook": "hook",
            "body": "body",
            "cta": "cta",
            "voice_style": "calm-narrator",
            "created_at": "2026-05-03T00:00:00",
        },
    )

    result = _repair(base, apply=False)
    assert result["repaired_groups"] == 0
    assert result["unmatched_groups"] == 1
    assert (base / "scripts/orphan-topic.json").exists()
