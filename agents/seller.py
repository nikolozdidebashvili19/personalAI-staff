"""Seller sub-agent — Marketplace listing copywriting + price sense."""

from core.agent import tools
from core.brain import brain
from core.memory import memory


@tools.register(
    "draft_listing",
    "Write a Facebook Marketplace listing (title + description) for an item the user wants "
    "to sell, and sanity-check the price. Returns the draft — publish with "
    "facebook_create_listing after the user approves.",
    {
        "type": "object",
        "properties": {
            "item": {"type": "string", "description": "What is being sold, condition, age, specs"},
            "price": {"type": "number"},
            "currency": {"type": "string", "default": "EUR"},
        },
        "required": ["item", "price"],
    },
)
def draft_listing(item: str, price: float, currency: str = "EUR") -> str:
    style = memory.profile.get("writing_style") or "honest, friendly, no salesy fluff"
    return brain.quick(
        f"Item for sale: {item}\nAsking price: {price} {currency}\nSeller's voice: {style}\n\n"
        "Produce:\nTITLE: (max 65 chars, searchable keywords first)\n"
        "DESCRIPTION: (3-6 short lines — condition, what's included, why selling, pickup/shipping)\n"
        "PRICE CHECK: one line on whether the price seems high/fair/low for this kind of item.",
        system="You write marketplace listings that sell fast without overpromising.",
    )


@tools.register(
    "selling_report",
    "Summarize the user's marketplace activity from memory: what's listed, what sold, "
    "recent buyer messages.",
    {"type": "object", "properties": {}},
)
def selling_report() -> str:
    listed = memory.recall("marketplace_listing", limit=10)
    sold = memory.recall("marketplace_sold", limit=10)
    lines = ["Marketplace activity:"]
    lines += [f"  listed [{e['timestamp'][:10]}]: {e['description']} ({e['result']})" for e in listed]
    lines += [f"  sold   [{e['timestamp'][:10]}]: {e['description']}" for e in sold]
    if len(lines) == 1:
        return "No marketplace activity recorded yet."
    return "\n".join(lines)
