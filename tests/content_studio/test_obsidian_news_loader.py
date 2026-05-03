"""Tests for the Obsidian daily-note parser + ingest hookup."""

from __future__ import annotations

import textwrap

import pytest

from api.schemas.content_studio import ContentFormat
from pixelle_video.services.content_studio import NewsIngestService
from pixelle_video.services.content_studio.obsidian_news_loader import (
    DailyNoteNotFound,
    daily_note_path,
    items_to_candidates,
    load_candidates_for_date,
    parse_daily_note,
)


# A sample that mirrors the real vault layout we ship against.
_SAMPLE_NOTE = textwrap.dedent(
    """\
    ---
    kind: meeting
    slug: 2026-05-03-daily-project-ai-sync
    ---

    # 2026-05-03 Daily Project & AI Sync

    ## 今日總覽

    - 日期：2026-05-03

    ## AI 工程情報早報

    ### 1) Open Design 爆紅：把 coding agent 直接當設計引擎
    - 類型：GitHub / 論壇
    - 重點：`nexu-io/open-design` 成為 Hacker News 熱門話題，定位為 Claude Design 的開源替代品。
    - 為什麼重要：這代表設計原型、品牌系統與 agent workflow 正在快速收斂。
    - 連結：
      - GitHub: https://github.com/nexu-io/open-design
      - Hacker News 討論： https://news.ycombinator.com/
    - 備註：這一條來自今天已送達的早報內容。

    ### 2) 新的 prompt-eval 工具
    - 類型：論文
    - 重點：研究人員開源了一個小型 prompt evaluation harness。
    - 為什麼重要：把 prompt 改動的回歸測試成本從天級壓到分鐘級。

    ## AI 工程情報晚報

    - 待今日晚報自動補上

    ## 今日專案 / 功能紀錄

    - Project：unrelated section, must NOT be picked up
    """
)


def test_parse_extracts_morning_items_and_skips_evening_placeholder():
    items = parse_daily_note(_SAMPLE_NOTE)

    titles = [it.title for it in items]
    assert "Open Design 爆紅：把 coding agent 直接當設計引擎" in titles
    assert "新的 prompt-eval 工具" in titles
    # Evening placeholder must not become a topic.
    assert not any("待今日晚報" in t for t in titles)
    # The "今日專案" section is not an AI-news section and must be ignored.
    assert not any("unrelated" in t for t in titles)


def test_parse_extracts_per_field_values():
    items = parse_daily_note(_SAMPLE_NOTE)
    by_title = {it.title: it for it in items}
    open_design = by_title["Open Design 爆紅：把 coding agent 直接當設計引擎"]
    assert "Claude Design 的開源替代品" in open_design.summary
    assert "agent workflow" in open_design.why_it_matters
    assert open_design.section == "morning"
    assert "https://github.com/nexu-io/open-design" in open_design.links
    assert open_design.item_type.startswith("GitHub")


def test_items_to_candidates_uses_github_link_as_source_url():
    items = parse_daily_note(_SAMPLE_NOTE)
    candidates = items_to_candidates(items, target_date="2026-05-03", source_ref="sample.md")

    assert all(c.source.source_type == "obsidian" for c in candidates)
    assert all(c.date == "2026-05-03" for c in candidates)

    open_design = next(c for c in candidates if c.title.startswith("Open Design"))
    assert open_design.source.source_url == "https://github.com/nexu-io/open-design"
    assert open_design.source.source_ref == "sample.md"
    # GitHub items get VIDEO added because they tend to make better video material.
    assert ContentFormat.VIDEO in open_design.recommended_formats


def test_load_candidates_raises_when_note_missing(tmp_path):
    with pytest.raises(DailyNoteNotFound):
        load_candidates_for_date("1999-01-01", vault_root=tmp_path)


def test_load_candidates_reads_from_disk(tmp_path):
    meetings = tmp_path / "meetings"
    meetings.mkdir()
    note_path = meetings / "2026-05-03-daily-project-ai-sync.md"
    note_path.write_text(_SAMPLE_NOTE, encoding="utf-8")

    candidates = load_candidates_for_date("2026-05-03", vault_root=tmp_path)
    assert len(candidates) == 2
    assert any("Open Design" in c.title for c in candidates)


def test_daily_note_path_uses_default_vault_when_unspecified():
    p = daily_note_path("2026-05-03")
    assert p.name == "2026-05-03-daily-project-ai-sync.md"
    assert p.parent.name == "meetings"


def test_ingest_from_daily_note_persists_topics(tmp_path, storage):
    meetings = tmp_path / "meetings"
    meetings.mkdir()
    (meetings / "2026-05-03-daily-project-ai-sync.md").write_text(_SAMPLE_NOTE, encoding="utf-8")

    service = NewsIngestService(storage)
    topics = service.ingest_from_daily_note(
        target_date="2026-05-03",
        vault_root=tmp_path,
    )
    assert len(topics) == 2
    saved = storage.list_topics(date="2026-05-03")
    assert {t.title for t in saved} == {t.title for t in topics}
    assert all(t.source.source_type == "obsidian" for t in saved)


def test_ingest_from_daily_note_is_idempotent(tmp_path, storage):
    meetings = tmp_path / "meetings"
    meetings.mkdir()
    (meetings / "2026-05-03-daily-project-ai-sync.md").write_text(_SAMPLE_NOTE, encoding="utf-8")

    service = NewsIngestService(storage)
    service.ingest_from_daily_note(target_date="2026-05-03", vault_root=tmp_path)
    service.ingest_from_daily_note(target_date="2026-05-03", vault_root=tmp_path)

    # Re-running must replace, not stack — we expect exactly the parsed count.
    rows = storage.list_topics(date="2026-05-03")
    assert len(rows) == 2


def test_ingest_from_daily_note_raises_when_missing(tmp_path, storage):
    service = NewsIngestService(storage)
    with pytest.raises(DailyNoteNotFound):
        service.ingest_from_daily_note(target_date="1999-01-01", vault_root=tmp_path)
