"""LLM access with graceful degradation.

Primary brain:  Claude via the Anthropic SDK (full tool use).
Fallback brain: Google Gemini free tier (text only, no tools).
"""

from typing import Any, Optional

from config.settings import settings
from core.logger import get_logger

log = get_logger("brain")

try:
    import anthropic

    _HAS_ANTHROPIC = True
except ImportError:
    _HAS_ANTHROPIC = False

try:
    import google.generativeai as genai

    _HAS_GEMINI = True
except ImportError:
    _HAS_GEMINI = False


class Brain:
    def __init__(self):
        self._claude = None
        self._gemini = None
        if _HAS_ANTHROPIC and settings.has_anthropic:
            self._claude = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        if _HAS_GEMINI and settings.has_gemini:
            genai.configure(api_key=settings.gemini_api_key)
            self._gemini = genai.GenerativeModel(settings.gemini_model)

    @property
    def available(self) -> bool:
        return self._claude is not None or self._gemini is not None

    @property
    def supports_tools(self) -> bool:
        return self._claude is not None

    def chat(
        self,
        messages: list[dict],
        system: str = "",
        tools: Optional[list[dict]] = None,
        max_tokens: int = 4096,
    ) -> Any:
        """Full Messages-API call. Returns the Anthropic response object when Claude
        is available; otherwise a lightweight object mimicking .content/.stop_reason
        built from the Gemini fallback (no tool use)."""
        if self._claude is not None:
            try:
                return self._claude.messages.create(
                    model=settings.claude_model,
                    max_tokens=max_tokens,
                    system=system or anthropic.NOT_GIVEN,
                    tools=tools or anthropic.NOT_GIVEN,
                    messages=messages,
                )
            except anthropic.AuthenticationError:
                log.error("Anthropic auth failed — check ANTHROPIC_API_KEY. Trying Gemini.")
            except Exception as e:
                log.error("Claude call failed (%s) — trying Gemini fallback.", e)
        if self._gemini is not None:
            return self._gemini_chat(messages, system)
        raise RuntimeError(
            "No AI brain available. Set ANTHROPIC_API_KEY (or GEMINI_API_KEY) in .env"
        )

    def quick(self, prompt: str, system: str = "", max_tokens: int = 1024) -> str:
        """Single-shot text generation, no tools. Used by sub-agents for drafting."""
        resp = self.chat([{"role": "user", "content": prompt}], system=system, max_tokens=max_tokens)
        return response_text(resp)

    def _gemini_chat(self, messages: list[dict], system: str) -> Any:
        prompt_parts = []
        if system:
            prompt_parts.append(f"[System instructions]\n{system}\n")
        for m in messages:
            content = m["content"]
            if isinstance(content, list):  # flatten content blocks to text
                content = " ".join(
                    b.get("text", "") if isinstance(b, dict) else str(b) for b in content
                )
            prompt_parts.append(f"{m['role']}: {content}")
        result = self._gemini.generate_content("\n".join(prompt_parts))
        return _FakeResponse(result.text)


class _FakeBlock:
    type = "text"

    def __init__(self, text: str):
        self.text = text


class _FakeResponse:
    """Duck-types the parts of anthropic.Message the agent loop reads."""

    stop_reason = "end_turn"

    def __init__(self, text: str):
        self.content = [_FakeBlock(text)]


def response_text(resp: Any) -> str:
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


brain = Brain()
