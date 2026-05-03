"""Load TopicCandidates from the user's Obsidian daily briefing note.

The daily note pattern is:

    {vault_root}/meetings/YYYY-MM-DD-daily-project-ai-sync.md

Each note has two AI-news blocks (the morning briefing and evening
briefing). Each item inside a block uses this shape (Markdown):

    ### 1) Title text
    - 類型: GitHub / 論壇
    - 重點: short summary
    - 為什麼重要: why this matters
    - 連結:
      - GitHub: https://...
      - Hacker News 討論: https://...
    - 備註: optional notes

The parser is forgiving: it tolerates bullet-prefix variations
(`- 重點：...`, `- **重點**：...`), full-width vs. half-width colons, and
arbitrary item counts. Items that look like placeholders ("待今日晚報自動補上",
"暫無 / TBD") are skipped.

The loader is fully offline and only depends on stdlib + pydantic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date as _date
from pathlib import Path
from typing import Iterable, List, Optional

from api.schemas.content_studio import (
    ContentFormat,
    TopicCandidate,
    TopicSource,
)


DEFAULT_VAULT_ROOT = Path("/Users/wuwenkai/Projects/sales-wiki")
DAILY_NOTE_SUBDIR = "meetings"
DAILY_NOTE_PATTERN = "{date}-daily-project-ai-sync.md"


# Recognised section headers ("早報" / "晚報" — morning / evening briefing).
_MORNING_HEADERS = ("AI 工程情報早報", "AI工程情報早報", "早報")
_EVENING_HEADERS = ("AI 工程情報晚報", "AI工程情報晚報", "晚報")

# Bullet-field labels we actively extract.
_FIELD_ALIASES = {
    "summary": ("重點", "摘要", "summary"),
    "why": ("為什麼重要", "為何重要", "重要性", "why it matters", "why"),
    "links": ("連結", "連接", "links", "link"),
    "type": ("類型", "type"),
    "notes": ("備註", "notes"),
}

# Placeholder phrases that indicate "no real item here yet".
_PLACEHOLDER_MARKERS = (
    "待今日晚報",
    "待補",
    "暫無",
    "TBD",
    "待今日早報",
    "尚未產生",
)

_URL_RE = re.compile(r"https?://\S+")


@dataclass
class ParsedItem:
    """An intermediate, untyped parse result for one news item."""

    title: str
    summary: str = ""
    why_it_matters: str = ""
    item_type: str = ""
    notes: str = ""
    links: List[str] = field(default_factory=list)
    section: str = ""  # "morning" / "evening"


class DailyNoteNotFound(FileNotFoundError):
    """Raised when the requested daily note doesn't exist on disk."""


def daily_note_path(target_date: str | _date, vault_root: Path | str | None = None) -> Path:
    """Resolve the on-disk path for a given date's daily note."""
    if isinstance(target_date, _date):
        target_date = target_date.isoformat()
    root = Path(vault_root) if vault_root else DEFAULT_VAULT_ROOT
    filename = DAILY_NOTE_PATTERN.format(date=target_date)
    return root / DAILY_NOTE_SUBDIR / filename


def _strip_label(text: str, aliases: Iterable[str]) -> Optional[str]:
    """If ``text`` starts with one of the field aliases (followed by a colon),
    return the remainder. Otherwise return ``None``."""
    cleaned = text.lstrip("-* \t").strip()
    # Allow optional bold/italic wrappers: **重點：** value
    cleaned = re.sub(r"^\*+|\*+$", "", cleaned).strip()
    for alias in aliases:
        for sep in (":", "：", " - ", " — "):
            prefix = f"{alias}{sep}"
            if cleaned.lower().startswith(prefix.lower()):
                return cleaned[len(prefix):].strip()
        # Bare label without colon, e.g. "連結" then nested bullets
        if cleaned.lower() == alias.lower():
            return ""
    return None


def _is_placeholder(text: str) -> bool:
    return any(marker in text for marker in _PLACEHOLDER_MARKERS)


def _parse_item_block(title: str, body_lines: List[str], section: str) -> Optional[ParsedItem]:
    item = ParsedItem(title=title.strip(), section=section)
    in_links = False
    for raw in body_lines:
        line = raw.rstrip()
        if not line.strip():
            in_links = False
            continue

        # Non-bullet trailing prose — append to summary if we don't have one yet.
        if not line.lstrip().startswith(("-", "*", "+")):
            in_links = False
            if not item.summary:
                item.summary = line.strip()
            continue

        stripped = line.lstrip()
        # Detect indentation depth (nested links live under a `連結` bullet).
        indent = len(line) - len(stripped)

        if in_links and indent >= 2:
            for url in _URL_RE.findall(stripped):
                if url not in item.links:
                    item.links.append(url)
            continue
        else:
            in_links = False

        for field_name, aliases in _FIELD_ALIASES.items():
            value = _strip_label(stripped, aliases)
            if value is None:
                continue
            if field_name == "summary":
                item.summary = value
            elif field_name == "why":
                item.why_it_matters = value
            elif field_name == "type":
                item.item_type = value
            elif field_name == "notes":
                item.notes = value
            elif field_name == "links":
                in_links = True
                for url in _URL_RE.findall(value):
                    if url not in item.links:
                        item.links.append(url)
            break
        else:
            # Unlabeled bullet — capture inline URLs but otherwise ignore.
            for url in _URL_RE.findall(stripped):
                if url not in item.links:
                    item.links.append(url)

    if _is_placeholder(item.title) or (
        not item.summary and not item.why_it_matters and _is_placeholder("\n".join(body_lines))
    ):
        return None
    return item


def parse_daily_note(text: str) -> List[ParsedItem]:
    """Parse the markdown text of a daily note into a list of items.

    The function does not need to know the date; it just walks the
    document looking for the morning/evening AI-news sections and
    splits them by ``###`` headers.
    """
    lines = text.splitlines()

    items: List[ParsedItem] = []
    current_section: Optional[str] = None
    pending_title: Optional[str] = None
    pending_body: List[str] = []

    def flush():
        nonlocal pending_title, pending_body
        if pending_title is not None and current_section is not None:
            parsed = _parse_item_block(pending_title, pending_body, current_section)
            if parsed is not None:
                items.append(parsed)
        pending_title = None
        pending_body = []

    for raw in lines:
        line = raw.rstrip()
        # Top-level section header (## ...).
        if line.startswith("## ") and not line.startswith("### "):
            flush()
            heading = line[3:].strip()
            if any(h in heading for h in _MORNING_HEADERS):
                current_section = "morning"
            elif any(h in heading for h in _EVENING_HEADERS):
                current_section = "evening"
            else:
                current_section = None
            continue

        if current_section is None:
            continue

        # Item header (### N) Title) inside a known section.
        if line.startswith("### "):
            flush()
            heading = line[4:].strip()
            # Strip the leading "1)" / "1." / "1、" numbering when present.
            heading = re.sub(r"^\s*\d+\s*[\)\.\、]\s*", "", heading)
            pending_title = heading
            pending_body = []
            continue

        if pending_title is not None:
            pending_body.append(line)
            continue

        # Plain bullets directly under the section, with no `### Title` —
        # treat the first non-placeholder bullet's text as a one-off item
        # (this lets a section like "晚報\n- 待今日晚報自動補上" stay
        #  empty rather than producing a placeholder topic).
        if line.lstrip().startswith(("-", "*", "+")):
            text_value = line.lstrip("-*+ \t").strip()
            if text_value and not _is_placeholder(text_value):
                pending_title = text_value[:80]
                pending_body = []

    flush()
    return items


def items_to_candidates(
    items: Iterable[ParsedItem],
    target_date: str,
    source_ref: str,
    default_priority_morning: int = 70,
    default_priority_evening: int = 65,
) -> List[TopicCandidate]:
    """Convert ParsedItems into TopicCandidate models."""
    candidates: List[TopicCandidate] = []
    for item in items:
        if not item.title:
            continue
        priority = (
            default_priority_morning
            if item.section == "morning"
            else default_priority_evening
        )
        # Prefer the first GitHub link (if any) as the source URL because
        # those usually point at the canonical artifact.
        primary_url: Optional[str] = None
        for url in item.links:
            if "github.com" in url:
                primary_url = url
                break
        if primary_url is None and item.links:
            primary_url = item.links[0]

        recommended = [ContentFormat.SUBSTACK, ContentFormat.FACEBOOK, ContentFormat.LINE]
        # Tools and repos tend to make great videos; news-of-the-day items don't always.
        if item.item_type and any(
            kw in item.item_type for kw in ("GitHub", "工具", "Repo", "repo", "tool")
        ):
            recommended.append(ContentFormat.VIDEO)

        summary_parts = [item.summary]
        if item.notes:
            summary_parts.append(f"備註: {item.notes}")
        summary = "\n".join(p for p in summary_parts if p).strip()

        candidates.append(
            TopicCandidate(
                title=item.title,
                summary=summary,
                why_it_matters=item.why_it_matters,
                source=TopicSource(
                    source_type="obsidian",
                    source_url=primary_url,
                    source_ref=source_ref,
                ),
                recommended_formats=recommended,
                priority=priority,
                date=target_date,
            )
        )
    return candidates


def load_candidates_for_date(
    target_date: str | _date | None = None,
    vault_root: Path | str | None = None,
) -> List[TopicCandidate]:
    """Read today's (or the given date's) daily note and return candidates."""
    if target_date is None:
        target_date = _date.today().isoformat()
    elif isinstance(target_date, _date):
        target_date = target_date.isoformat()

    path = daily_note_path(target_date, vault_root=vault_root)
    if not path.exists():
        raise DailyNoteNotFound(f"Daily note not found: {path}")

    text = path.read_text(encoding="utf-8")
    items = parse_daily_note(text)
    return items_to_candidates(items, target_date=target_date, source_ref=path.name)
