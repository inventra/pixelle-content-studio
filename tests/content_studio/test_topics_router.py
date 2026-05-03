"""HTTP-level tests for the Topics router."""

from __future__ import annotations


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
