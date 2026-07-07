"""LLM access with graceful degradation.

Primary brain:  Claude via the Anthropic SDK (best tool use + vision).
Fallback brain: Google Gemini free tier — with FULL tool use via function
calling, so the whole agent works even without an Anthropic key.

The agent loop speaks the Anthropic message format; the Gemini path translates
both directions and returns duck-typed response objects the loop understands.
"""

import uuid
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
    from google import genai
    from google.genai import types as gtypes

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
            self._gemini = genai.Client(api_key=settings.gemini_api_key)

    @property
    def available(self) -> bool:
        return self._claude is not None or self._gemini is not None

    @property
    def supports_tools(self) -> bool:
        return self._claude is not None or self._gemini is not None

    @property
    def supports_vision(self) -> bool:
        # the screenshot-driven browser loop is tuned for Claude
        return self._claude is not None

    def chat(
        self,
        messages: list[dict],
        system: str = "",
        tools: Optional[list[dict]] = None,
        max_tokens: int = 4096,
    ) -> Any:
        """Messages-API-shaped call. Returns an Anthropic response object, or a
        duck-typed equivalent from Gemini (same .content / .stop_reason)."""
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
            return self._gemini_chat(messages, system, tools, max_tokens)
        raise RuntimeError(
            "No AI brain available. Set ANTHROPIC_API_KEY (or GEMINI_API_KEY) in .env"
        )

    def quick(self, prompt: str, system: str = "", max_tokens: int = 1024) -> str:
        """Single-shot text generation, no tools. Used by sub-agents for drafting."""
        resp = self.chat([{"role": "user", "content": prompt}], system=system, max_tokens=max_tokens)
        return response_text(resp)

    # ------------------------------------------------------------------
    # Gemini translation layer
    # ------------------------------------------------------------------

    def _gemini_chat(self, messages: list[dict], system: str,
                     tools: Optional[list[dict]], max_tokens: int) -> "_FakeResponse":
        contents = _to_gemini_contents(messages)
        config = gtypes.GenerateContentConfig(
            system_instruction=system or None,
            tools=_to_gemini_tools(tools),
            max_output_tokens=max_tokens,
        )
        # Free-tier daily quotas differ wildly per model (newest = smallest),
        # so walk a fallback chain instead of failing on the first 429.
        chain = [settings.gemini_model, "gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest"]
        models = list(dict.fromkeys(chain))  # dedupe, keep order
        resp = None
        last_err: Optional[Exception] = None
        for model_name in models:
            try:
                resp = self._gemini.models.generate_content(
                    model=model_name, contents=contents, config=config
                )
                if model_name != models[0]:
                    log.info("Gemini fallback model used: %s", model_name)
                break
            except Exception as e:
                code = getattr(e, "code", None) or getattr(e, "status_code", None)
                if code in (404, 429):  # bad model name or quota — try the next one
                    log.warning("Gemini %s unavailable (%s) — trying next model", model_name, code)
                    last_err = e
                    continue
                raise
        if resp is None:
            raise RuntimeError(
                f"All Gemini models are rate-limited or unavailable right now: {last_err}"
            )

        blocks: list[Any] = []
        has_call = False
        candidate = resp.candidates[0] if resp.candidates else None
        parts = (candidate.content.parts or []) if candidate and candidate.content else []
        for p in parts:
            fc = getattr(p, "function_call", None)
            if fc is not None and getattr(fc, "name", None):
                has_call = True
                tu = _FakeToolUse(fc.name, dict(fc.args or {}))
                sig = getattr(p, "thought_signature", None)
                if sig:  # Gemini 3 requires signatures echoed back on replay
                    _SIGNATURES[tu.id] = sig
                blocks.append(tu)
            elif getattr(p, "text", None):
                blocks.append(_FakeBlock(p.text))
        if not blocks:
            blocks.append(_FakeBlock("(no reply)"))
        return _FakeResponse(blocks, "tool_use" if has_call else "end_turn")


# ---------- anthropic-format -> gemini-format ----------

# tool_use id -> Gemini thought_signature (must be replayed with the call)
_SIGNATURES: dict[str, bytes] = {}

_SCHEMA_KEYS = {"type", "properties", "required", "description", "items", "enum"}


def _sanitize_schema(schema: dict) -> dict:
    """Gemini accepts a JSON-schema subset — strip keys it rejects (default, etc.)."""
    out = {}
    for k, v in schema.items():
        if k not in _SCHEMA_KEYS:
            continue
        if k == "properties" and isinstance(v, dict):
            out[k] = {name: _sanitize_schema(sub) for name, sub in v.items()}
        elif k == "items" and isinstance(v, dict):
            out[k] = _sanitize_schema(v)
        else:
            out[k] = v
    return out


def _to_gemini_tools(tools: Optional[list[dict]]):
    if not tools:
        return None
    decls = []
    for t in tools:
        d = {"name": t["name"], "description": t.get("description", "")}
        params = _sanitize_schema(t.get("input_schema") or {})
        if params.get("properties"):
            d["parameters"] = params
        decls.append(d)
    return [gtypes.Tool(function_declarations=decls)]


def _to_gemini_contents(messages: list[dict]) -> list:
    contents = []
    id_to_name: dict[str, str] = {}
    for m in messages:
        c = m["content"]
        if isinstance(c, str):
            role = "user" if m["role"] == "user" else "model"
            contents.append(gtypes.Content(role=role, parts=[gtypes.Part.from_text(text=c)]))
            continue
        parts, is_tool_reply = [], False
        for b in c:
            btype = b.get("type") if isinstance(b, dict) else getattr(b, "type", "")
            if btype == "text":
                parts.append(gtypes.Part.from_text(text=b["text"]))
            elif btype == "image":
                import base64 as _b64

                src = b.get("source", {})
                parts.append(gtypes.Part.from_bytes(
                    data=_b64.b64decode(src.get("data", "")),
                    mime_type=src.get("media_type", "image/png"),
                ))
            elif btype == "tool_use":
                id_to_name[b["id"]] = b["name"]
                part = gtypes.Part.from_function_call(name=b["name"], args=b.get("input") or {})
                sig = _SIGNATURES.get(b["id"])
                if sig:
                    part.thought_signature = sig
                parts.append(part)
            elif btype == "tool_result":
                is_tool_reply = True
                name = id_to_name.get(b.get("tool_use_id", ""), "tool")
                result = b.get("content", "")
                if not isinstance(result, str):
                    result = str(result)
                parts.append(gtypes.Part.from_function_response(name=name, response={"result": result}))
        if not parts:
            continue
        if m["role"] == "user":
            role = "tool" if is_tool_reply else "user"
        else:
            role = "model"
        contents.append(gtypes.Content(role=role, parts=parts))
    return contents


# ---------- duck-typed response objects ----------

class _FakeBlock:
    type = "text"

    def __init__(self, text: str):
        self.text = text


class _FakeToolUse:
    type = "tool_use"

    def __init__(self, name: str, input_: dict):
        self.id = "gem_" + uuid.uuid4().hex[:12]
        self.name = name
        self.input = input_


class _FakeResponse:
    """Duck-types the parts of anthropic.Message the agent loop reads."""

    def __init__(self, blocks: list, stop_reason: str):
        self.content = blocks
        self.stop_reason = stop_reason


def response_text(resp: Any) -> str:
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


brain = Brain()
