from __future__ import annotations

import json
import textwrap

from scripts.ingest_daily_topics import run
from pixelle_video.services.content_studio import ContentStudioStorage


_SAMPLE_NOTE = textwrap.dedent(
    """\
    ## AI 工程情報早報

    ### 1) Open Design 爆紅：把 coding agent 直接當設計引擎
    - 類型：GitHub / 論壇
    - 重點：開源專案讓設計流程直接接上 agent。
    - 為什麼重要：讓 PM、設計、前端協作更快。
    - 連結：
      - GitHub: https://github.com/nexu-io/open-design
    """
)


def test_run_ingests_daily_note_and_prints_json(tmp_path, capsys):
    meetings = tmp_path / "meetings"
    meetings.mkdir()
    (meetings / "2026-05-03-daily-project-ai-sync.md").write_text(_SAMPLE_NOTE, encoding="utf-8")

    data_dir = tmp_path / "data"
    exit_code = run([
        "--date",
        "2026-05-03",
        "--vault-root",
        str(tmp_path),
        "--base-dir",
        str(data_dir),
    ])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["ingested"] == 1
    assert any("Open Design" in title for title in payload["titles"])

    storage = ContentStudioStorage(base_dir=data_dir)
    topics = storage.list_topics(date="2026-05-03")
    assert len(topics) == 1


def test_run_returns_nonzero_when_note_missing(tmp_path, capsys):
    exit_code = run([
        "--date",
        "1999-01-01",
        "--vault-root",
        str(tmp_path),
        "--base-dir",
        str(tmp_path / "data"),
    ])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert '"ok": false' in captured.err.lower()
