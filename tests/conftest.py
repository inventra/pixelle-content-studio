"""Shared pytest fixtures for the Content Studio MVP test suite.

The fixtures here keep tests fully offline:
- A per-test ``ContentStudioStorage`` rooted in a tmp dir, registered as
  the global singleton via ``set_storage`` so routers/services see it.
- A FastAPI ``TestClient`` mounting only the content-studio routers (we
  don't spin up the full Pixelle-Video app, which needs ComfyUI/LLM
  config to actually run).
- A deterministic stub LLM caller wired in via the dep helper.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make project root importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.content_studio import (
    drafts_router,
    storyboards_router,
    topics_router,
)
from api.routers.content_studio import _deps as cs_deps
from pixelle_video.services.content_studio import (
    ContentStudioStorage,
    reset_storage,
    set_storage,
)


@pytest.fixture
def storage(tmp_path) -> ContentStudioStorage:
    """A per-test storage rooted in a tmp dir."""
    storage = ContentStudioStorage(base_dir=tmp_path / "content_studio")
    set_storage(storage)
    yield storage
    reset_storage()


@pytest.fixture
def stub_llm():
    """An offline LLM stub that returns deterministic text per prompt.

    Tests that want richer-looking output can opt into this fixture; by
    default the services fall back to their built-in templates.
    """
    async def _llm(prompt: str) -> str:
        # Echo a marker so tests can assert the LLM path was used.
        first_line = prompt.splitlines()[0] if prompt else ""
        return f"[LLM-STUB] {first_line.strip()}"

    cs_deps.set_llm_caller_factory(lambda: _llm)
    yield _llm
    cs_deps.set_llm_caller_factory(None)


@pytest.fixture
def app(storage) -> FastAPI:
    """Minimal FastAPI app exposing only the content-studio routers."""
    app = FastAPI()
    app.include_router(topics_router, prefix="/api")
    app.include_router(drafts_router, prefix="/api")
    app.include_router(storyboards_router, prefix="/api")
    return app


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)
