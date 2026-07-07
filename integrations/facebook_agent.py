"""Facebook Marketplace via browser automation (no public API for listings).

Same pattern as LinkedIn: persistent logged-in browser profile + vision loop.
"""

import time

from core.agent import tools
from core.computer_use import browser, vision_browser_task
from core.logger import get_logger
from core.memory import memory

log = get_logger("facebook")


def _ensure_login() -> str | None:
    b = browser()
    b.open("https://www.facebook.com/marketplace/")
    text = b.text(1500).lower()
    if "log in" in text and "marketplace" not in b.page.title().lower():
        return (
            "Facebook is not logged in. The browser window is open — ask the user to "
            "log in there once (the session will be remembered), then try again."
        )
    return None


@tools.register(
    "facebook_create_listing",
    "Create a Facebook Marketplace listing for an item. Photos must already exist on disk "
    "(ask the user for the folder/paths). Price is a number in the user's local currency. "
    "The user confirms before publishing.",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "price": {"type": "number"},
            "description": {"type": "string"},
            "category": {"type": "string", "default": "Miscellaneous"},
            "photo_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Absolute paths to photo files (optional but recommended)",
            },
        },
        "required": ["title", "price", "description"],
    },
    requires_confirmation=True,
)
def facebook_create_listing(
    title: str, price: float, description: str, category: str = "Miscellaneous",
    photo_paths: list | None = None,
) -> str:
    err = _ensure_login()
    if err:
        return err
    b = browser()
    b.open("https://www.facebook.com/marketplace/create/item")
    time.sleep(3)

    # Upload photos programmatically if provided (file dialogs are hard for vision)
    photo_note = ""
    if photo_paths:
        try:
            file_input = b.page.locator("input[type='file']").first
            file_input.set_input_files(photo_paths)
            time.sleep(3)
            photo_note = f"{len(photo_paths)} photo(s) uploaded. "
        except Exception as e:
            photo_note = f"Photo upload failed ({e}) — ask the user to add photos manually. "

    result = vision_browser_task(
        f"Finish creating this Facebook Marketplace listing (photos step may already be done):\n"
        f"Title: {title}\nPrice: {price}\nCategory: {category}\nDescription: {description}\n"
        "Fill each field, choose the closest category, then click Next/Publish. "
        "If Facebook asks for anything you don't know, use wait_for_user."
    )
    status = "published" if result.lower().startswith("done") else "attempted"
    memory.remember_event("marketplace_listing", f"{title} @ {price}", status)
    return photo_note + result


@tools.register(
    "facebook_check_messages",
    "Check Facebook Marketplace messages from buyers and summarize them.",
    {"type": "object", "properties": {}},
)
def facebook_check_messages() -> str:
    err = _ensure_login()
    if err:
        return err
    b = browser()
    b.open("https://www.facebook.com/marketplace/inbox/")
    time.sleep(3)
    return "Marketplace inbox (visible text):\n" + b.text(4000)


@tools.register(
    "facebook_mark_sold",
    "Mark one of the user's Marketplace listings as sold. User confirms first.",
    {
        "type": "object",
        "properties": {"item_title": {"type": "string"}},
        "required": ["item_title"],
    },
    requires_confirmation=True,
)
def facebook_mark_sold(item_title: str) -> str:
    err = _ensure_login()
    if err:
        return err
    browser().open("https://www.facebook.com/marketplace/you/selling")
    result = vision_browser_task(
        f"On the 'Your listings' page, find the listing titled '{item_title}' "
        "and mark it as sold using its menu."
    )
    if result.lower().startswith("done"):
        memory.remember_event("marketplace_sold", item_title, "marked sold")
    return result
