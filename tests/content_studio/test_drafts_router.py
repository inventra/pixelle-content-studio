"""HTTP-level tests for the Drafts router."""

from __future__ import annotations


def _ingest_one(client, title="Open Design"):
    resp = client.post(
        "/api/topics/ingest",
        json={
            "candidates": [
                {
                    "title": title,
                    "summary": "Composable UI",
                    "why_it_matters": "Lowers iteration cost",
                    "source": {"source_type": "manual"},
                    "priority": 60,
                    "date": "2026-05-03",
                }
            ]
        },
    )
    assert resp.status_code == 200
    return resp.json()["topics"][0]["id"]


def test_generate_drafts_blocked_until_topic_selected(client):
    topic_id = _ingest_one(client)
    resp = client.post("/api/drafts/generate", json={"topic_id": topic_id})
    assert resp.status_code == 409


def test_generate_then_update_then_approve_flow(client):
    topic_id = _ingest_one(client)
    sel = client.post(f"/api/topics/{topic_id}/select")
    assert sel.status_code == 200

    gen = client.post("/api/drafts/generate", json={"topic_id": topic_id})
    assert gen.status_code == 200
    body = gen.json()["draft_set"]
    assert body["substack_draft"]
    assert body["facebook_draft"]
    assert body["line_draft"]
    assert body["approved_for_video"] is False

    upd = client.put(
        f"/api/drafts/{topic_id}",
        json={"substack_draft": "Hand-edited", "editor_notes": "tweaked"},
    )
    assert upd.status_code == 200
    assert upd.json()["draft_set"]["substack_draft"] == "Hand-edited"
    assert upd.json()["draft_set"]["editor_notes"] == "tweaked"

    apr = client.post(
        f"/api/drafts/{topic_id}/approve", json={"approved": True}
    )
    assert apr.status_code == 200
    assert apr.json()["draft_set"]["approved_for_video"] is True

    topic_state = client.get(f"/api/topics/{topic_id}").json()["topic"]["status"]
    assert topic_state == "draft_approved"


def test_get_drafts_404_when_missing(client):
    resp = client.get("/api/drafts/missing")
    assert resp.status_code == 404


def test_revoke_approval_drops_topic_back_to_drafted(client):
    topic_id = _ingest_one(client)
    client.post(f"/api/topics/{topic_id}/select")
    client.post("/api/drafts/generate", json={"topic_id": topic_id})
    client.post(f"/api/drafts/{topic_id}/approve", json={"approved": True})

    resp = client.post(f"/api/drafts/{topic_id}/approve", json={"approved": False})
    assert resp.status_code == 200
    assert resp.json()["draft_set"]["approved_for_video"] is False

    topic = client.get(f"/api/topics/{topic_id}").json()["topic"]
    assert topic["status"] == "drafted"


def test_regenerate_overwrites_existing(client):
    topic_id = _ingest_one(client)
    client.post(f"/api/topics/{topic_id}/select")
    client.post("/api/drafts/generate", json={"topic_id": topic_id})
    client.put(
        f"/api/drafts/{topic_id}",
        json={"editor_notes": "preserve me"},
    )

    cached = client.post("/api/drafts/generate", json={"topic_id": topic_id}).json()
    assert cached["draft_set"]["editor_notes"] == "preserve me"

    fresh = client.post(
        "/api/drafts/generate",
        json={"topic_id": topic_id, "regenerate": True},
    ).json()
    assert fresh["draft_set"]["editor_notes"] == ""
