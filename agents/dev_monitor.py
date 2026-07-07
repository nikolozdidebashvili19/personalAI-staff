"""Dev Monitor sub-agent — GitHub activity awareness for the briefing."""

from core.agent import tools
from core.brain import brain


@tools.register(
    "dev_report",
    "Full developer report: repos activity digest + PRs needing review + notifications, "
    "condensed into a short readable update. Use for the morning briefing or "
    "'what do I need to look at on GitHub'.",
    {"type": "object", "properties": {}},
)
def dev_report() -> str:
    from integrations.github_agent import github_digest, github_notifications, github_prs_to_review

    sections = []
    for name, fn in (("Digest", github_digest), ("PRs", github_prs_to_review),
                     ("Notifications", github_notifications)):
        try:
            sections.append(f"--- {name} ---\n{fn()}")
        except Exception as e:
            sections.append(f"--- {name} --- unavailable: {e}")
    raw = "\n".join(sections)
    if "unavailable" in raw and raw.count("unavailable") == 3:
        return "GitHub isn't configured yet — set GITHUB_TOKEN in .env to enable dev monitoring."
    return brain.quick(
        f"{raw[:6000]}\n\nCondense this into a developer's 60-second update: "
        "what needs action first, then what's just news. Keep repo names.",
        system="You are a concise engineering chief of staff.",
    )
