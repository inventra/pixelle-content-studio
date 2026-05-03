"""Generate Substack / Facebook / LINE drafts for an approved topic.

The draft tone deliberately mirrors the "偷懶辦公室" voice: not a news
recap, but a short-form essay that answers "why does this matter,
what can I actually do with it, and what's one move I can try
today." When an LLM caller is injected we steer it with that prompt;
when not, we fall back to a structured template that gives the
editor an honest skeleton (the per-surface structure is the same
either way so the editor sees a consistent layout).

Templates are intentionally product-neutral — no LazyOffice imports
and no hard-coded brand name in the rendered output, so this same
generator is reusable for other publications. The "偷懶辦公室" anchor
lives in the LLM prompt only as a tone reference.
"""

from __future__ import annotations

import inspect
from typing import Awaitable, Callable, List, Optional

from loguru import logger

from api.schemas.content_studio import (
    DraftSet,
    Topic,
    TopicStatus,
)
from pixelle_video.services.content_studio.state_machine import (
    InvalidStateTransition,
    TopicStateMachine,
)
from pixelle_video.services.content_studio.storage import ContentStudioStorage


LLMCaller = Callable[[str], "str | Awaitable[str]"]


# Topics must have been at least selected before drafts make sense.
_DRAFT_ALLOWED_STATES = {
    TopicStatus.SELECTED,
    TopicStatus.DRAFTED,
    TopicStatus.DRAFT_APPROVED,
}


# Shared style brief reused by every per-surface LLM prompt. Keeping it
# here (instead of duplicated per surface) makes the voice consistent
# across Substack / Facebook / LINE.
_STYLE_BRIEF = (
    "Voice & style anchor: write in the spirit of 偷懶辦公室 (Toulan Office) — "
    "practical, insightful, slightly opinionated, never breathless or robotic. "
    "Do NOT write a news recap or a bulleted list of facts. Instead, structure "
    "the piece around: (1) a one-sentence hook on why this matters now, "
    "(2) the concrete problem it solves, (3) two or three real use cases the "
    "reader could try this week, and (4) one actionable prompt or workflow tip "
    "they can copy-paste. Use the user's original language (Traditional "
    "Chinese if the topic is in Chinese). Be specific; avoid filler like "
    "'in today's fast-paced world'."
)


def _split_sentences(text: str) -> List[str]:
    """Loose sentence splitter that keeps Chinese punctuation usable."""
    if not text:
        return []
    # Replace Chinese full-stops/separators with newlines so str.split works.
    normalised = (
        text.replace("。", "。\n")
        .replace("！", "！\n")
        .replace("？", "？\n")
        .replace("；", "；\n")
        .replace(";", ";\n")
    )
    parts: List[str] = []
    for chunk in normalised.split("\n"):
        for sub in chunk.split(". "):
            sub = sub.strip(" \t\n-•*")
            if sub:
                parts.append(sub)
    return parts


class DraftGenerator:
    def __init__(
        self,
        storage: ContentStudioStorage,
        llm_caller: Optional[LLMCaller] = None,
    ):
        self.storage = storage
        self.llm_caller = llm_caller

    async def generate(
        self,
        topic_id: str,
        tone: str = "informative",
        regenerate: bool = False,
    ) -> DraftSet:
        topic = self.storage.get_topic(topic_id)
        if topic is None:
            raise LookupError(f"Topic {topic_id} not found")

        if topic.status not in _DRAFT_ALLOWED_STATES:
            raise InvalidStateTransition(
                f"Topic {topic.id} is in '{topic.status.value}' state; select it before generating drafts."
            )

        existing = self.storage.get_drafts(topic_id)
        if existing and not regenerate:
            return existing

        substack = await self._render(topic, tone, "substack")
        facebook = await self._render(topic, tone, "facebook")
        line_draft = await self._render(topic, tone, "line")

        draft_set = DraftSet(
            topic_id=topic.id,
            substack_draft=substack,
            facebook_draft=facebook,
            line_draft=line_draft,
            editor_notes="",
            approved_for_video=existing.approved_for_video if existing else False,
        )
        self.storage.save_drafts(draft_set)

        if topic.status == TopicStatus.SELECTED:
            topic.status = TopicStatus.DRAFTED
            self.storage.save_topic(topic)

        return draft_set

    def update(self, topic_id: str, **changes) -> DraftSet:
        drafts = self.storage.get_drafts(topic_id)
        if drafts is None:
            raise LookupError(f"Drafts for topic {topic_id} not found")
        for key, value in changes.items():
            if value is None:
                continue
            if not hasattr(drafts, key):
                raise AttributeError(f"DraftSet has no field '{key}'")
            setattr(drafts, key, value)
        return self.storage.save_drafts(drafts)

    def approve(self, topic_id: str, approved: bool = True) -> DraftSet:
        drafts = self.storage.get_drafts(topic_id)
        topic = self.storage.get_topic(topic_id)
        if drafts is None or topic is None:
            raise LookupError(f"Drafts for topic {topic_id} not found")

        drafts.approved_for_video = approved
        self.storage.save_drafts(drafts)

        if approved:
            TopicStateMachine.assert_transition(topic.status, TopicStatus.DRAFT_APPROVED)
            topic.status = TopicStatus.DRAFT_APPROVED
        else:
            # Roll the topic back to "drafted" so the operator can edit again.
            if topic.status == TopicStatus.DRAFT_APPROVED:
                topic.status = TopicStatus.DRAFTED
        self.storage.save_topic(topic)
        return drafts

    # ----- rendering --------------------------------------------------------

    async def _render(self, topic: Topic, tone: str, surface: str) -> str:
        prompt = self._build_prompt(topic, tone, surface)
        if self.llm_caller is not None:
            try:
                result = self.llm_caller(prompt)
                if inspect.isawaitable(result):
                    result = await result
                if isinstance(result, str) and result.strip():
                    return result.strip()
            except Exception as e:  # pragma: no cover - defensive
                logger.warning(f"LLM draft generation failed for {surface}: {e}")
        return self._fallback_template(topic, tone, surface)

    @staticmethod
    def _build_prompt(topic: Topic, tone: str, surface: str) -> str:
        surface_brief = {
            "substack": (
                "Format: a Substack newsletter post in Markdown. Start with a "
                "level-1 heading containing the topic title verbatim. Then a "
                "single hook paragraph, then short H2 sections for: 為什麼值得看一眼, "
                "實際可以拿來做什麼 (2-3 concrete use cases as a numbered list), "
                "一個今天就能用的招式 (an actionable prompt or workflow snippet "
                "in a fenced code block when relevant), and 一句話總結. "
                "Aim for ~350-500 words."
            ),
            "facebook": (
                "Format: a Facebook post. Plain text, ~120-180 words. Lead "
                "with a single-line hook (no headline). One short paragraph "
                "on why this matters, then 2-3 bullet-style lines (use • or →) "
                "with concrete use cases, then one short prompt/workflow tip, "
                "then 2-3 hashtags on the last line. Topic title must appear "
                "in the body."
            ),
            "line": (
                "Format: a LINE broadcast message. ≤ 220 Traditional-Chinese "
                "characters total. Start with 【title】, then one line "
                "summarising the angle, one line on why it matters, and one "
                "line with a copy-paste prompt or action. No hashtags. Topic "
                "title must appear in the message."
            ),
        }.get(surface, "")
        return (
            f"{_STYLE_BRIEF}\n\n"
            f"Surface: {surface}.\n"
            f"{surface_brief}\n\n"
            f"Tone hint from caller: {tone} (use this only as a nudge; the style "
            f"anchor above always wins).\n\n"
            f"--- Topic ---\n"
            f"Title: {topic.title}\n"
            f"Summary: {topic.summary or '(no summary supplied)'}\n"
            f"Why it matters: {topic.why_it_matters or '(no why-it-matters supplied)'}\n"
        )

    @staticmethod
    def _use_case_seeds(topic: Topic) -> List[str]:
        """Best-effort use-case bullets pulled from summary sentences.

        The fallback templates can't invent real use cases, but they
        can surface the most actionable-looking pieces of the summary
        so the editor sees a meaningful skeleton instead of empty
        bullets.
        """
        sentences = _split_sentences(topic.summary)
        seeds: List[str] = []
        for s in sentences:
            if len(s) < 6:
                continue
            seeds.append(s)
            if len(seeds) >= 3:
                break
        # Always pad to at least two slots so the editor sees the structure.
        while len(seeds) < 2:
            seeds.append("(編輯補上一個具體 use case)")
        return seeds

    @classmethod
    def _fallback_template(cls, topic: Topic, tone: str, surface: str) -> str:
        title = topic.title.strip() or "今天這條值得花三分鐘看的 AI 消息"
        summary = topic.summary.strip() or "（待補：用一句話講清楚這條在做什麼）"
        why = topic.why_it_matters.strip() or "（待補：為什麼今天的讀者要在意這件事）"
        use_cases = cls._use_case_seeds(topic)

        if surface == "substack":
            bullets = "\n".join(f"{i + 1}. {seed}" for i, seed in enumerate(use_cases))
            return (
                f"# {title}\n\n"
                f"_Tone: {tone}_\n\n"
                f"今天這條我之所以挑出來，是因為它直接戳到一個我們每天都在處理的痛點：{why}\n\n"
                f"## 為什麼值得看一眼\n"
                f"{why}\n\n"
                f"在資訊爆炸的早晨，多數新工具都是「看起來很酷、但跟我無關」。"
                f"這條的差別在於：它把一件原本要花半天的事，壓到一個工作流就能跑完。\n\n"
                f"## 它在解決什麼問題\n"
                f"{summary}\n\n"
                f"## 實際可以拿來做什麼\n"
                f"{bullets}\n\n"
                f"## 一個今天就能用的招式\n"
                f"```\n"
                f"請以「{title}」為主題，幫我列出三個我這週可以實際試試的應用場景，"
                f"每個場景請給我一段可以直接複製貼上的 prompt 或 workflow。\n"
                f"```\n\n"
                f"## 一句話總結\n"
                f"{title} 不是又一個玩具——它幫你把「想到了卻懶得做」的事，變成「順手就做完」。\n"
            )
        if surface == "facebook":
            uc_lines = "\n".join(f"• {seed}" for seed in use_cases[:3])
            return (
                f"🧠 {title}\n\n"
                f"今天值得花三分鐘看的一條：{summary}\n\n"
                f"為什麼重要：{why}\n\n"
                f"實際可以這樣用：\n"
                f"{uc_lines}\n\n"
                f"→ 試試這個 prompt：「請以『{title}』為題，"
                f"幫我設計一個我這週可以馬上跑的工作流」\n\n"
                f"#AI工具 #工作效率 #偷懶有方法"
            )
        if surface == "line":
            short_summary = summary if len(summary) <= 60 else summary[:57] + "…"
            short_why = why if len(why) <= 50 else why[:47] + "…"
            first_use = use_cases[0] if use_cases else "拿它幫你跑一次本來不想做的事"
            short_use = first_use if len(first_use) <= 50 else first_use[:47] + "…"
            return (
                f"【{title}】\n"
                f"📌 {short_summary}\n"
                f"💡 為什麼值得看：{short_why}\n"
                f"🛠 怎麼用：{short_use}"
            )
        raise ValueError(f"Unknown surface: {surface}")
