"""HTTP-level tests for the Topics router."""

from __future__ import annotations

import textwrap


_DAILY_NOTE_SAMPLE = textwrap.dedent(
    """\
    ## AI 工程情報早報

    ### 1) 一個今天值得看的 AI 工具
    - 類型：GitHub
    - 重點：開源工具，把某個工作流自動化。
    - 為什麼重要：壓低工程師每天的重複性勞動。
    - 連結:
      - GitHub: https://github.com/example/example

    ## AI 工程情報晚報

    - 待今日晚報自動補上
    """
)


def _ingest_payload(title="Open Design", date="2026-05-03"):
    return {
        "candidates": [
            {
                "title": title,
                "summary": "A new way to ship UI",
                "why_it_matters": "Lowers iteration cost",
                "source": {"source_type": "hermes"},
                "recommended_formats": ["substack", "video"],
                "priority": 80,
                "date": date,
            }
        ]
    }


def test_ingest_then_today_returns_candidate(client):
    resp = client.post("/api/topics/ingest", json=_ingest_payload())
    assert resp.status_code == 200
    body = resp.json()
    assert body["ingested"] == 1
    topic_id = body["topics"][0]["id"]

    resp2 = client.get("/api/topics/today", params={"date": "2026-05-03"})
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["date"] == "2026-05-03"
    assert any(t["id"] == topic_id for t in body2["topics"])


def test_get_topic_404_when_missing(client):
    resp = client.get("/api/topics/does-not-exist")
    assert resp.status_code == 404


def test_select_then_skip_409_due_to_state(client):
    resp = client.post("/api/topics/ingest", json=_ingest_payload())
    topic_id = resp.json()["topics"][0]["id"]

    sel = client.post(f"/api/topics/{topic_id}/select")
    assert sel.status_code == 200
    assert sel.json()["topic"]["status"] == "selected"

    # Skip is reserved for the initial triage decision (CANDIDATE only).
    # Once a topic has been selected, backing out goes via ARCHIVED, not
    # SKIPPED — so the state machine must reject this with 409.
    skip = client.post(f"/api/topics/{topic_id}/skip")
    assert skip.status_code == 409


def test_today_excludes_skipped_by_default(client):
    resp = client.post("/api/topics/ingest", json=_ingest_payload(title="Skipping"))
    topic_id = resp.json()["topics"][0]["id"]
    skip = client.post(f"/api/topics/{topic_id}/skip")
    assert skip.status_code == 200

    today = client.get("/api/topics/today", params={"date": "2026-05-03"}).json()
    assert all(t["id"] != topic_id for t in today["topics"])

    today_with_skipped = client.get(
        "/api/topics/today",
        params={"date": "2026-05-03", "include_skipped": "true"},
    ).json()
    assert any(t["id"] == topic_id for t in today_with_skipped["topics"])


def test_priority_clamped(client):
    resp = client.post("/api/topics/ingest", json=_ingest_payload())
    topic_id = resp.json()["topics"][0]["id"]

    out = client.post(f"/api/topics/{topic_id}/priority", params={"priority": 999})
    assert out.status_code == 200
    assert out.json()["topic"]["priority"] == 100


def test_ingest_daily_note_404_when_missing(client, tmp_path):
    resp = client.post(
        "/api/topics/ingest/daily",
        json={"date": "1999-01-01", "vault_root": str(tmp_path)},
    )
    assert resp.status_code == 404


def test_ingest_daily_note_round_trip(client, tmp_path):
    meetings = tmp_path / "meetings"
    meetings.mkdir()
    (meetings / "2026-05-03-daily-project-ai-sync.md").write_text(
        _DAILY_NOTE_SAMPLE, encoding="utf-8"
    )

    resp = client.post(
        "/api/topics/ingest/daily",
        json={"date": "2026-05-03", "vault_root": str(tmp_path)},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ingested"] == 1
    assert body["date"] == "2026-05-03"
    assert body["note_path"].endswith("2026-05-03-daily-project-ai-sync.md")
    assert body["topics"][0]["source"]["source_type"] == "obsidian"

    # Topic should now appear in /today.
    today = client.get("/api/topics/today", params={"date": "2026-05-03"}).json()
    assert any("AI 工具" in t["title"] for t in today["topics"])


def test_ingest_daily_note_replaces_previous_run(client, tmp_path):
    meetings = tmp_path / "meetings"
    meetings.mkdir()
    note = meetings / "2026-05-03-daily-project-ai-sync.md"
    note.write_text(_DAILY_NOTE_SAMPLE, encoding="utf-8")

    payload = {"date": "2026-05-03", "vault_root": str(tmp_path)}
    client.post("/api/topics/ingest/daily", json=payload)
    client.post("/api/topics/ingest/daily", json=payload)

    today = client.get("/api/topics/today", params={"date": "2026-05-03"}).json()
    # Idempotent: re-running must not duplicate.
    assert len(today["topics"]) == 1


def test_replace_for_date_drops_existing(client):
    client.post("/api/topics/ingest", json=_ingest_payload(title="A"))
    client.post("/api/topics/ingest", json=_ingest_payload(title="B"))

    payload = _ingest_payload(title="Fresh")
    payload["replace_for_date"] = True
    resp = client.post("/api/topics/ingest", json=payload)
    assert resp.status_code == 200

    today = client.get("/api/topics/today", params={"date": "2026-05-03"}).json()
    titles = {t["title"] for t in today["topics"]}
    assert titles == {"Fresh"}
