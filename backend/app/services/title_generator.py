import re
import asyncio
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Acronyms or technical tokens to preserve in uppercase
KNOWN_ACRONYMS = {"srv", "db", "api", "cpu", "ram", "rag", "sql", "mrpl", "ai", "llm", "id", "os", "ip", "url", "uri"}

def _preserve_case_word(w: str) -> str:
    cleaned = re.sub(r"[^\w\-]", "", w)
    if not cleaned:
        return w
    # If contains numbers and letters with hyphens (e.g., SRV-DB01, DB01)
    if any(c.isdigit() for c in cleaned) and any(c.isalpha() for c in cleaned):
        return cleaned.upper()
    if cleaned.lower() in KNOWN_ACRONYMS:
        return cleaned.upper()
    if cleaned.isupper() and len(cleaned) <= 5:
        return cleaned
    return cleaned.capitalize()

def generate_title_heuristic(message: str) -> str:
    """
    Fast, reliable local heuristic to generate a 3-7 word title
    from the user's first message without requiring an LLM call.
    """
    text = message.strip()
    if not text:
        return "New Conversation"

    # Normalize whitespace
    text = " ".join(text.split())

    # Check for "Summarize X" -> "X Summary"
    summarize_match = re.match(
        r"^(?:please\s+)?summarize\s+(?:the\s+)?(.+?)(?:\s+and\s+.*|\?|\.|$)",
        text,
        re.IGNORECASE
    )
    if summarize_match:
        target = summarize_match.group(1).strip()
        words = target.split()
        if 1 <= len(words) <= 6:
            title_words = [_preserve_case_word(w) for w in words]
            # Avoid duplicate "Summary" if already present
            if title_words[-1].lower() != "summary":
                title_words.append("Summary")
            return " ".join(title_words[:7])

    # Check for "What is the <topic> of/for/in <entity>?" -> "<Entity> <Topic>"
    entity_topic_match = re.match(
        r"^(?:what\s+(?:is|are)\s+(?:the\s+)?)(.+?)\s+(?:of|for|in)\s+([A-Za-z0-9\-_]+(?:\s+[A-Za-z0-9\-_]+)?)\??$",
        text,
        re.IGNORECASE
    )
    if entity_topic_match:
        topic_part = entity_topic_match.group(1).strip()
        entity_part = entity_topic_match.group(2).strip()
        topic_words = [_preserve_case_word(w) for w in topic_part.split()]
        entity_words = [_preserve_case_word(w) for w in entity_part.split()]
        # e.g., "SRV-DB01 Storage Capacity" or "2026 Planned Upgrades"
        return " ".join((entity_words + topic_words)[:7])

    # Remove standard introductory question/command fillers
    cleaned = re.sub(
        r"^(?:can\s+you\s+)?(?:please\s+)?(?:tell\s+me\s+about|what\s+(?:is|are|was|were)(?:\s+the)?|"
        r"how\s+(?:do|does|can|is|are)|why\s+(?:is|are|does)|give\s+me(?:\s+a|\s+the)?|"
        r"show\s+me(?:\s+a|\s+the)?|explain(?:\s+the)?|describe(?:\s+the)?|"
        r"find(?:\s+the)?|get(?:\s+the)?|look\s+up(?:\s+the)?)\s+",
        "",
        text,
        flags=re.IGNORECASE
    ).strip()

    # Strip trailing punctuation
    cleaned = re.sub(r"[?!.,;:]+$", "", cleaned).strip()

    # If it has "for <year/entity>" at end, e.g. "planned upgrades for 2026"
    for_match = re.match(r"^(.+?)\s+(?:for|in)\s+([0-9]{4}|[A-Za-z0-9\-_]{2,})\b", cleaned, re.IGNORECASE)
    if for_match:
        subj = for_match.group(1).strip()
        ent = for_match.group(2).strip()
        subj_words = [_preserve_case_word(w) for w in subj.split()]
        ent_word = _preserve_case_word(ent)
        return " ".join(([ent_word] + subj_words)[:7])

    words = cleaned.split()
    if not words:
        words = text.split()

    title_words = [_preserve_case_word(w) for w in words[:6]]
    # Ensure between 3 and 7 words if original had enough words
    if len(title_words) > 7:
        title_words = title_words[:7]

    return " ".join(title_words)


async def generate_title(message: str, gateway=None) -> str:
    """
    Generates a 3-7 word conversation title.
    Attempts local LLM generation with strict 2.0s timeout;
    falls back immediately to rule-based heuristic on failure/timeout.
    """
    if gateway:
        try:
            from app.core.config import settings
            from app.core.model_gateway.schemas import GenerationRequest, Message as GenMessage

            prompt = (
                f"Generate a concise 3 to 6 word title describing the topic of this user message.\n"
                f"User message: \"{message.strip()}\"\n"
                f"Rules: Return ONLY the title words, no quotes, no markdown, no explanation."
            )
            gen_req = GenerationRequest(
                model=settings.DEFAULT_CHAT_MODEL,
                messages=[GenMessage(role="user", content=prompt)]
            )
            # 2.0 second bounded timeout to never block user response
            resp = await asyncio.wait_for(gateway.generate(gen_req), timeout=2.0)
            candidate = resp.text.strip().strip('"\'`')
            # Sanitize LLM response
            candidate = re.sub(r"^(Title|Topic):\s*", "", candidate, flags=re.IGNORECASE).strip()
            words = candidate.split()
            if 2 <= len(words) <= 8:
                return " ".join([_preserve_case_word(w) for w in words[:7]])
        except Exception as e:
            logger.debug(f"LLM title generation skipped/failed: {e}; using heuristic fallback")

    return generate_title_heuristic(message)
