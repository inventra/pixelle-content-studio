"""HTTP-level tests for the Storyboards + render-bridge router."""

from __future__ import annotations

from api.tasks import task_manager


def _approved_topic(client) -> str:
    """Walk the topic through ingest -> select -> drafts -> approve."""
    resp = client.post(
        "/api/topics/ingest",
        json={
            "candidates": [
                {
                    "title": "Pixelle Studio",
                    "summary": "A new content studio on top of Pixelle-Video.",
                    "why_it_matters": "Independent of LazyOffice.",
                    "source": {"source_type": "manual"},
                    "priority": 70,
                    "date": "2026-05-03",
                }
            ]
        },
    )
    topic_id = resp.json()["topics"][0]["id"]
    client.post(f"/api/topics/{topic_id}/select")
    client.post("/api/drafts/generate", json={"topic_id": topic_id})
    client.post(f"/api/drafts/{topic_id}/approve", json={"approved": True})
    return topic_id


def test_script_endpoint_blocked_without_approval(client):
    resp = client.post(
        "/api/topics/ingest",
        json={"candidates": [{"title": "x", "date": "2026-05-03"}]},
    )
    topic_id = resp.json()["topics"][0]["id"]
    out = client.post("/api/storyboards/script", json={"topic_id": topic_id})
    # 404 because drafts don't exist yet
    assert out.status_code == 404


def test_script_then_storyboard_then_render(client):
    topic_id = _approved_topic(client)

    script_resp = client.post(
        "/api/storyboards/script",
        json={"topic_id": topic_id, "duration_target": 45, "angle": "Why now"},
    )
    assert script_resp.status_code == 200
    script = script_resp.json()["script"]
    assert script["duration_target"] == 45
    assert script["hook"]
    assert script["body"]

    sb_resp = client.post(
        "/api/storyboards/generate",
        json={"topic_id": topic_id, "n_scenes": 4, "visual_style": "vintage-print"},
    )
    assert sb_resp.status_code == 200
    storyboard = sb_resp.json()["storyboard"]
    assert len(storyboard["scenes"]) == 4
    assert storyboard["visual_style"] == "vintage-print"

    # Cost gate must reject submissions without confirm_cost.
    bad = client.post(
        "/api/storyboards/render",
        json={"topic_id": topic_id, "confirm_cost": False},
    )
    assert bad.status_code == 409

    good = client.post(
        "/api/storyboards/render",
        json={
            "topic_id": topic_id,
            "frame_template": "1080x1920/image_default.html",
            "confirm_cost": True,
        },
    )
    assert good.status_code == 200
    record = good.json()["render"]
    assert record["topic_id"] == topic_id
    assert record["status"] == "queued"
    assert record["pixelle_task_id"]
    assert record["submit_params"]["mode"] == "fixed"

    # The bridge must register a Pixelle-Video task.
    task = task_manager.get_task(record["pixelle_task_id"])
    assert task is not None
    assert task.task_type.value == "video_generation"

    # Topic state has advanced to render_queued.
    topic = client.get(f"/api/topics/{topic_id}").json()["topic"]
    assert topic["status"] == "render_queued"


def test_render_blocked_before_storyboard(client):
    topic_id = _approved_topic(client)
    # Skip the storyboard step.
    out = client.post(
        "/api/storyboards/render",
        json={"topic_id": topic_id, "confirm_cost": True},
    )
    assert out.status_code == 404


def test_get_storyboard_returns_both_script_and_storyboard(client):
    topic_id = _approved_topic(client)
    client.post("/api/storyboards/script", json={"topic_id": topic_id})
    client.post(
        "/api/storyboards/generate",
        json={"topic_id": topic_id, "n_scenes": 3},
    )
    out = client.get(f"/api/storyboards/{topic_id}").json()
    assert out["script"] is not None
    assert out["storyboard"] is not None
    assert len(out["storyboard"]["scenes"]) == 3


def test_get_storyboard_returns_nulls_if_absent(client):
    topic_id = _approved_topic(client)
    out = client.get(f"/api/storyboards/{topic_id}").json()
    assert out["script"] is None
    assert out["storyboard"] is None
