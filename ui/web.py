"""Web UI — browser chat interface. Run `python -m ui.web` and open http://localhost:8765.

Before entering the chat, the page asks for the Claude and Gemini API keys;
they are saved to .env and the brain is re-initialized live. The chat wraps the
same ChiefOfStaff agent as the terminal, over one WebSocket per tab.
Confirmations for irreversible actions become Allow/Deny cards in the chat:
the agent's blocking confirm() call (running in a worker thread) parks on a
Future that the browser's button click resolves.
"""

import asyncio
import concurrent.futures
import importlib
import uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config.settings import PROJECT_ROOT, settings
from core.agent import ChiefOfStaff, tools
from core.brain import brain
from core.logger import get_logger

log = get_logger("web")

HOST = "127.0.0.1"
PORT = 8765
STATIC_DIR = Path(__file__).parent / "web_static"
CONFIRM_TIMEOUT_S = 300  # unanswered confirmation cards deny after 5 minutes

# Same tool modules as main.py — importing registers them into the registry.
TOOL_MODULES = [
    "integrations.gmail_agent",
    "integrations.calendar_agent",
    "integrations.github_agent",
    "integrations.linkedin_agent",
    "integrations.facebook_agent",
    "core.computer_use",
    "agents.marketer",
    "agents.job_hunter",
    "agents.assistant",
    "agents.seller",
    "agents.dev_monitor",
]


def load_tool_modules() -> None:
    for mod in TOOL_MODULES:
        try:
            importlib.import_module(mod)
        except Exception as e:
            log.warning("Module %s disabled: %s", mod, e)


app = FastAPI(title="Personal AI Chief of Staff")


# ---------- REST: status + API keys ----------

@app.get("/api/status")
def api_status():
    return {
        "agent_name": settings.agent_name,
        "model": settings.claude_model,
        "claude": settings.has_anthropic,
        "gemini": settings.has_gemini,
        "brain_available": brain.available,
        "tools": len(tools),
    }


def update_env_file(path: Path, updates: dict[str, str]) -> None:
    """Upsert KEY=value lines in a .env file, preserving everything else."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(updates)
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if key in remaining:
            lines[i] = f"{key}={remaining.pop(key)}"
    lines.extend(f"{k}={v}" for k, v in remaining.items())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@app.post("/api/keys")
async def api_keys(payload: dict):
    """Save API keys from the entry screen to .env and re-init the brain."""
    anthropic_key = str(payload.get("anthropic_key", "")).strip()
    gemini_key = str(payload.get("gemini_key", "")).strip()

    updates = {}
    if anthropic_key:
        updates["ANTHROPIC_API_KEY"] = anthropic_key
        settings.anthropic_api_key = anthropic_key
    if gemini_key:
        updates["GEMINI_API_KEY"] = gemini_key
        settings.gemini_api_key = gemini_key
    if updates:
        update_env_file(PROJECT_ROOT / ".env", updates)
        brain.reinit()
        log.info("API keys updated (%s)", ", ".join(updates))

    return {
        "claude": settings.has_anthropic,
        "gemini": settings.has_gemini,
        "brain_available": brain.available,
    }


# ---------- WebSocket chat ----------

class ChatSession:
    """One browser tab: its own agent (own history) over one WebSocket."""

    def __init__(self, ws: WebSocket, loop: asyncio.AbstractEventLoop):
        self.ws = ws
        self.loop = loop
        self.pending: dict[str, concurrent.futures.Future] = {}
        self.agent = ChiefOfStaff(
            confirm_callback=self._confirm,
            notify_callback=self._notify,
        )

    def _send_threadsafe(self, message: dict) -> None:
        asyncio.run_coroutine_threadsafe(self.ws.send_json(message), self.loop)

    def _confirm(self, question: str) -> bool:
        """Called from the agent's worker thread mid-turn; blocks until the
        browser answers the confirmation card (deny on timeout/disconnect)."""
        cid = uuid.uuid4().hex
        fut: concurrent.futures.Future = concurrent.futures.Future()
        self.pending[cid] = fut
        self._send_threadsafe({"type": "confirm", "id": cid, "question": question})
        try:
            return bool(fut.result(timeout=CONFIRM_TIMEOUT_S))
        except Exception:
            return False
        finally:
            self.pending.pop(cid, None)

    def _notify(self, message: str) -> None:
        self._send_threadsafe({"type": "info", "text": str(message)})

    def resolve_confirm(self, cid: str, allow: bool) -> None:
        fut = self.pending.get(cid)
        if fut and not fut.done():
            fut.set_result(allow)

    def deny_all_pending(self) -> None:
        for fut in self.pending.values():
            if not fut.done():
                fut.set_result(False)


@app.websocket("/ws")
async def ws_chat(ws: WebSocket):
    await ws.accept()
    session = ChatSession(ws, asyncio.get_running_loop())
    busy = False
    try:
        while True:
            data = await ws.receive_json()
            kind = data.get("type")

            if kind == "confirm_response":
                session.resolve_confirm(data.get("id", ""), bool(data.get("allow")))
                continue

            if kind == "chat":
                text = str(data.get("text", "")).strip()
                if not text:
                    continue
                if busy:
                    await ws.send_json({"type": "error", "text": "Still working on the previous message."})
                    continue
                if not brain.available:
                    await ws.send_json({
                        "type": "error",
                        "text": "No AI brain configured — reload the page and enter an API key.",
                    })
                    continue
                busy = True
                await ws.send_json({"type": "thinking"})
                try:
                    reply = await asyncio.to_thread(session.agent.run_turn, text)
                    await ws.send_json({"type": "reply", "text": reply})
                except Exception as e:
                    log.exception("Chat turn failed")
                    await ws.send_json({"type": "error", "text": f"Something went wrong: {e}"})
                finally:
                    busy = False
    except WebSocketDisconnect:
        pass
    finally:
        session.deny_all_pending()


# ---------- static frontend ----------

@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def main() -> None:
    load_tool_modules()
    log.info("%d tools loaded", len(tools))
    print(f"\n  {settings.agent_name} web UI running at http://{HOST}:{PORT}\n")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
