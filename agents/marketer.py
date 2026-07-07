"""Marketer sub-agent — content creation in the user's voice.

Drafting is separate from publishing: draft_linkedin_post returns text for the
user to approve, then the main agent publishes via linkedin_post (confirmed).
"""

from core.agent import tools
from core.brain import brain
from core.memory import memory


def _style() -> str:
    ps = memory.profile.get("posting_style", {})
    return (
        f"Tone: {ps.get('linkedin_tone') or 'casual but insightful'}. "
        f"Usual topics: {', '.join(ps.get('topics', []) or ['coding', 'tech', 'career'])}. "
        f"General writing style: {memory.profile.get('writing_style') or 'natural, human, no corporate buzzwords'}."
    )


@tools.register(
    "draft_linkedin_post",
    "Write a LinkedIn post draft in the user's personal style. Returns the draft text — "
    "show it to the user, then publish with linkedin_post once they approve.",
    {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "What the post is about"},
            "extra_context": {"type": "string", "description": "Details, links, or angle to include"},
        },
        "required": ["topic"],
    },
)
def draft_linkedin_post(topic: str, extra_context: str = "") -> str:
    past = memory.recall("linkedin_post", limit=3)
    past_txt = "\n".join(e["description"] for e in past) or "(no past posts yet)"
    prompt = (
        f"Write ONE LinkedIn post about: {topic}\n"
        f"Extra context: {extra_context or 'none'}\n\n"
        f"User's style: {_style()}\n"
        f"Recent posts (do not repeat them):\n{past_txt}\n\n"
        "Rules: hook in the first line, short paragraphs, no hashtag spam (max 3), "
        "sound like a real person sharing something they learned. Output ONLY the post text."
    )
    return brain.quick(prompt, system="You are a ghostwriter matching the user's authentic voice.")


@tools.register(
    "content_ideas",
    "Suggest LinkedIn content ideas based on what the user has been doing lately "
    "(from memory) and their usual topics.",
    {"type": "object", "properties": {}},
)
def content_ideas() -> str:
    recent = memory.events_since(hours=72)
    recent_txt = "\n".join(f"{e['type']}: {e['description']}" for e in recent[-20:]) or "(quiet week)"
    return brain.quick(
        f"The user's recent activity:\n{recent_txt}\n\nTheir style: {_style()}\n\n"
        "Suggest 5 concrete LinkedIn post ideas (one line each) they could write today.",
        system="You are a sharp content strategist.",
    )
