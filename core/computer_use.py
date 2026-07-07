"""Computer use — the universal fallback when no API exists.

Layer 1: Playwright browser automation (preferred — LinkedIn, Facebook, any site).
         Uses a persistent browser profile so logins survive restarts.
Layer 2: PyAutoGUI desktop control (mouse + keyboard for native apps).
Layer 3: Vision loop — screenshot → Claude looks at it → next action → repeat.

Layer 3 is what makes the agent "never get stuck": if selectors fail or the UI
is unknown, it drives the screen the way a human would.
"""

import base64
import json
import time
from typing import Optional

from config.settings import settings
from core.agent import tools
from core.brain import brain, response_text
from core.logger import get_logger

log = get_logger("computer_use")


# ============================================================
# Layer 1 — Playwright browser (persistent profile)
# ============================================================

class BrowserController:
    """Singleton wrapper around a persistent Playwright Chromium context."""

    _instance: Optional["BrowserController"] = None

    def __init__(self):
        self._pw = None
        self._context = None
        self._page = None

    @classmethod
    def get(cls) -> "BrowserController":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _ensure(self):
        if self._page is not None and not self._page.is_closed():
            return
        from playwright.sync_api import sync_playwright

        if self._pw is None:
            self._pw = sync_playwright().start()
        settings.browser_profile_dir.mkdir(parents=True, exist_ok=True)
        self._context = self._pw.chromium.launch_persistent_context(
            str(settings.browser_profile_dir),
            headless=False,  # visible so the user can log in / solve captchas
            viewport={"width": 1280, "height": 900},
        )
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()

    @property
    def page(self):
        self._ensure()
        return self._page

    def open(self, url: str) -> str:
        self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
        time.sleep(2)
        return f"Opened {url} — page title: {self.page.title()}"

    def text(self, max_chars: int = 4000) -> str:
        body = self.page.inner_text("body")
        return " ".join(body.split())[:max_chars]

    def click_text(self, text: str) -> str:
        loc = self.page.get_by_text(text, exact=False).first
        loc.click(timeout=8000)
        time.sleep(1.5)
        return f"Clicked element containing '{text}'"

    def click_selector(self, selector: str) -> str:
        self.page.click(selector, timeout=8000)
        time.sleep(1.5)
        return f"Clicked {selector}"

    def fill(self, selector: str, value: str) -> str:
        self.page.fill(selector, value, timeout=8000)
        return f"Filled {selector}"

    def type_text(self, text: str) -> str:
        self.page.keyboard.type(text, delay=25)
        return "Typed text"

    def press(self, key: str) -> str:
        self.page.keyboard.press(key)
        time.sleep(1)
        return f"Pressed {key}"

    def screenshot_b64(self) -> str:
        return base64.b64encode(self.page.screenshot(type="png")).decode()

    def scroll(self, pixels: int = 600) -> str:
        self.page.mouse.wheel(0, pixels)
        time.sleep(0.8)
        return f"Scrolled {pixels}px"

    def close(self):
        try:
            if self._context:
                self._context.close()
            if self._pw:
                self._pw.stop()
        finally:
            self._context = self._page = self._pw = None


def browser() -> BrowserController:
    return BrowserController.get()


# ============================================================
# Layer 2 — PyAutoGUI desktop control
# ============================================================

def desktop_click(x: int, y: int) -> str:
    import pyautogui

    pyautogui.click(x, y)
    return f"Clicked screen at ({x}, {y})"


def desktop_type(text: str) -> str:
    import pyautogui

    pyautogui.typewrite(text, interval=0.02)
    return "Typed on desktop"


def desktop_hotkey(*keys: str) -> str:
    import pyautogui

    pyautogui.hotkey(*keys)
    return f"Pressed {'+'.join(keys)}"


def desktop_screenshot_b64() -> str:
    import io

    import pyautogui

    img = pyautogui.screenshot()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


# ============================================================
# Layer 3 — Vision loop (screenshot → Claude → action)
# ============================================================

VISION_SYSTEM = """You are controlling a web browser to complete a task for the user.
You see a screenshot of the current page. Respond ONLY with a single JSON object:
{"action": "click_text", "text": "..."}         click element containing visible text
{"action": "click_selector", "selector": "..."}  click a CSS selector
{"action": "fill", "selector": "...", "value": "..."}
{"action": "type", "text": "..."}                type into the focused element
{"action": "press", "key": "Enter"}
{"action": "scroll", "pixels": 600}
{"action": "goto", "url": "..."}
{"action": "wait_for_user", "reason": "..."}     login page / captcha — a human must act
{"action": "done", "summary": "..."}             task finished (or impossible — say why)
Pick ONE next action that makes the most progress. Never invent selectors you can't
see evidence for; prefer click_text with visible labels."""


def vision_browser_task(goal: str, max_steps: int = 15) -> str:
    """Drive the browser toward `goal` using screenshots + Claude vision."""
    if not brain.available:
        return "Vision computer use needs an AI brain (ANTHROPIC_API_KEY or GEMINI_API_KEY)."
    b = browser()
    transcript = []
    for step in range(max_steps):
        shot = b.screenshot_b64()
        messages = [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": shot}},
                {"type": "text", "text":
                    f"GOAL: {goal}\nSTEPS SO FAR:\n" + "\n".join(transcript[-8:]) +
                    f"\nCurrent URL: {b.page.url}\nWhat is the single next action? JSON only."},
            ],
        }]
        raw = response_text(brain.chat(messages, system=VISION_SYSTEM, max_tokens=500))
        try:
            start, end = raw.find("{"), raw.rfind("}") + 1
            act = json.loads(raw[start:end])
        except Exception:
            transcript.append(f"step {step}: model returned unparseable action")
            continue

        kind = act.get("action")
        try:
            if kind == "done":
                return f"Done: {act.get('summary', '')}\nActions taken:\n" + "\n".join(transcript)
            if kind == "wait_for_user":
                return ("PAUSED — human needed: " + act.get("reason", "login/captcha") +
                        ". The browser window is open; ask the user to complete it, then retry.")
            if kind == "goto":
                result = b.open(act["url"])
            elif kind == "click_text":
                result = b.click_text(act["text"])
            elif kind == "click_selector":
                result = b.click_selector(act["selector"])
            elif kind == "fill":
                result = b.fill(act["selector"], act["value"])
            elif kind == "type":
                result = b.type_text(act["text"])
            elif kind == "press":
                result = b.press(act.get("key", "Enter"))
            elif kind == "scroll":
                result = b.scroll(int(act.get("pixels", 600)))
            else:
                result = f"unknown action {kind}"
        except Exception as e:
            result = f"FAILED: {e}"
        transcript.append(f"step {step}: {json.dumps(act)[:120]} -> {result[:120]}")
    return "Step limit reached. Progress so far:\n" + "\n".join(transcript)


# ============================================================
# Decision router + registered tools
# ============================================================

@tools.register(
    "browser_open",
    "Open a URL in the agent's browser and return the page's visible text. "
    "The browser window is visible to the user and keeps logins between sessions.",
    {
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    },
)
def browser_open(url: str) -> str:
    if not settings.enable_computer_use:
        return "Computer use is disabled (ENABLE_COMPUTER_USE=false)."
    b = browser()
    status = b.open(url)
    return f"{status}\n\nPage text:\n{b.text()}"


@tools.register(
    "browser_task",
    "Complete a multi-step task on any website by looking at the screen and acting like "
    "a human (vision-driven). Use when no API or simpler tool exists — e.g. filling web "
    "forms, navigating unfamiliar sites. Describe the goal precisely.",
    {
        "type": "object",
        "properties": {
            "goal": {"type": "string", "description": "Precise description of what to accomplish"},
            "start_url": {"type": "string", "description": "URL to start from (optional)"},
        },
        "required": ["goal"],
    },
    requires_confirmation=True,
)
def browser_task(goal: str, start_url: str = "") -> str:
    if not settings.enable_computer_use:
        return "Computer use is disabled (ENABLE_COMPUTER_USE=false)."
    if start_url:
        browser().open(start_url)
    return vision_browser_task(goal)


@tools.register(
    "read_current_page",
    "Read the visible text of whatever page the agent's browser is currently on.",
    {"type": "object", "properties": {}},
)
def read_current_page() -> str:
    b = browser()
    return f"URL: {b.page.url}\n\n{b.text()}"
