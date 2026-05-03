#!/usr/bin/env python3
"""CLI entrypoint for importing the Obsidian daily briefing into Topics.

This is designed for cron/automation use. It reads the user's daily
Obsidian note, parses the AI-news sections, and writes candidate topics
into the Content Studio JSON store.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pixelle_video.services.content_studio import ContentStudioStorage, DailyNoteNotFound, NewsIngestService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest Obsidian daily AI-news into Pixelle Content Studio Topics")
    parser.add_argument("--date", dest="target_date", default=None, help="ISO date (YYYY-MM-DD). Defaults to today.")
    parser.add_argument(
        "--vault-root",
        default="/Users/wuwenkai/Projects/sales-wiki",
        help="Root path of the Obsidian vault that contains meetings/YYYY-MM-DD-daily-project-ai-sync.md",
    )
    parser.add_argument(
        "--base-dir",
        default=None,
        help="Content Studio storage directory. Defaults to PIXELLE_CONTENT_STUDIO_DATA_DIR or data/content_studio.",
    )
    parser.add_argument(
        "--no-replace",
        action="store_true",
        help="Append instead of replacing existing topics for the target date.",
    )
    return parser


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    storage = ContentStudioStorage(base_dir=args.base_dir)
    service = NewsIngestService(storage)
    try:
        topics = service.ingest_from_daily_note(
            target_date=args.target_date,
            vault_root=args.vault_root,
            replace_for_date=not args.no_replace,
        )
    except DailyNoteNotFound as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2

    payload = {
        "ok": True,
        "date": args.target_date,
        "vault_root": args.vault_root,
        "storage_dir": str(storage.base_dir),
        "ingested": len(topics),
        "titles": [topic.title for topic in topics],
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
