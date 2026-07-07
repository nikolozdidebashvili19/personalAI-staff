"""Main agent loop — the Chief of Staff.

A manual tool-use loop over the Messages API: Claude decides which registered
tools to call, we execute them, feed results back, and repeat until it answers.
Irreversible tools (send email, post, apply) require user confirmation first.
"""

import json
from typing import Callable, Optional

from config.settings import settings
from core.brain import brain, response_text
from core.logger import get_logger
from core.memory import memory

log = get_logger("agent")

MAX_TOOL_ROUNDS = 12


class Tool:
    def __init__(
        self,
        name: str,
        description: str,
        input_schema: dict,
        handler: Callable[..., str],
        requires_confirmation: bool = False,
    ):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.handler = handler
        self.requires_confirmation = requires_confirmation

    def to_api(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(
        self,
        name: str,
        description: str,
        input_schema: Optional[dict] = None,
        requires_confirmation: bool = False,
    ):
        """Decorator: @tools.register("get_weather", "…", {…})"""

        def deco(fn):
            self._tools[name] = Tool(
                name,
                description,
                input_schema or {"type": "object", "properties": {}},
                fn,
                requires_confirmation,
            )
            return fn

        return deco

    def add(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def to_api(self) -> list[dict]:
        return [t.to_api() for t in self._tools.values()]

    def __len__(self):
        return len(self._tools)


tools = ToolRegistry()  # global registry — integrations/agents register into it


class ChiefOfStaff:
    def __init__(self, confirm_callback: Optional[Callable[[str], bool]] = None,
                 notify_callback: Optional[Callable[[str], None]] = None):
        # confirm_callback(question) -> bool: how we ask the user before
        # irreversible actions. Defaults to console input.
        self.confirm = confirm_callback or (
            lambda q: input(f"\n⚠️  {q} (y/n): ").strip().lower().startswith("y")
        )
        self.notify = notify_callback or (lambda msg: print(msg))
        self.history: list[dict] = []

    # ---------- system prompt ----------

    def system_prompt(self) -> str:
        recent = memory.events_since(hours=24)
        recent_txt = "\n".join(
            f"- [{e['timestamp']}] {e['type']}: {e['description']} ({e['result']})"
            for e in recent[-15:]
        ) or "(nothing yet today)"
        return f"""You are {settings.agent_name}, a personal AI Chief of Staff — a friend, coworker,
and assistant all in one. You run on the user's own computer, 24/7.

Personality: {memory.profile.get('preferences', {}).get('agent_personality', 'friendly coworker')}.
Be warm, direct, and useful. Keep spoken-style replies short; this may be read aloud.

WHAT YOU KNOW ABOUT THE USER:
{memory.profile_summary()}

WHAT HAPPENED IN THE LAST 24 HOURS:
{recent_txt}

RULES:
1. Use your tools to actually do things — don't just describe what you would do.
2. Before sending emails, posting content, applying to jobs, or listing items,
   the system will ask the user to confirm. Never claim something was done
   unless the tool result says it succeeded.
3. When the user shares something new about themselves (skills, preferences,
   schedule, goals), call remember_fact or update_profile so you never forget.
4. If a tool fails, say what failed and suggest what the user can do
   (e.g. missing API key, needs login). Other capabilities keep working.
5. Ask a clarifying question when a request is ambiguous.
6. Today's context matters: reference past events from memory when relevant.
"""

    # ---------- main loop ----------

    def run_turn(self, user_input: str) -> str:
        self.history.append({"role": "user", "content": user_input})
        # keep the rolling window bounded
        if len(self.history) > 40:
            self.history = self.history[-40:]
            # history must start with a plain user turn (a leading tool_result
            # block without its matching tool_use would be rejected by the API)
            while self.history and not (
                self.history[0]["role"] == "user"
                and isinstance(self.history[0]["content"], str)
            ):
                self.history.pop(0)

        api_tools = tools.to_api() if brain.supports_tools else None
        reply = ""

        for _ in range(MAX_TOOL_ROUNDS):
            resp = brain.chat(self.history, system=self.system_prompt(), tools=api_tools)

            if resp.stop_reason != "tool_use":
                reply = response_text(resp)
                self.history.append({"role": "assistant", "content": reply or "(no reply)"})
                break

            # serialize assistant content blocks back into history
            assistant_blocks = []
            tool_uses = []
            for block in resp.content:
                if block.type == "text":
                    assistant_blocks.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    assistant_blocks.append(
                        {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
                    )
                    tool_uses.append(block)
            self.history.append({"role": "assistant", "content": assistant_blocks})

            results = []
            for tu in tool_uses:
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": self._execute_tool(tu.name, tu.input),
                    }
                )
            self.history.append({"role": "user", "content": results})
        else:
            reply = "I hit my tool-call limit for one request — let's break this into smaller steps."
            self.history.append({"role": "assistant", "content": reply})

        memory.remember_event("conversation", f"User: {user_input[:200]}", f"Reply: {reply[:200]}")
        return reply

    def _execute_tool(self, name: str, tool_input: dict) -> str:
        tool = tools.get(name)
        if tool is None:
            return f"Error: unknown tool '{name}'"

        if tool.requires_confirmation:
            summary = json.dumps(tool_input, ensure_ascii=False)[:400]
            if not self.confirm(f"{settings.agent_name} wants to run '{name}' with: {summary}. Allow?"):
                memory.remember_event("action_denied", f"{name}: {summary}", "user declined")
                return "The user declined this action. Do not retry it; ask what they'd like instead."

        try:
            log.info("Tool call: %s(%s)", name, json.dumps(tool_input)[:300])
            result = tool.handler(**tool_input)
            result = str(result)
            memory.remember_event("tool_call", f"{name}: {json.dumps(tool_input)[:200]}", result[:300])
            return result
        except TypeError as e:
            return f"Error: bad arguments for {name}: {e}"
        except Exception as e:
            log.exception("Tool %s failed", name)
            memory.remember_event("tool_error", name, str(e)[:300])
            return f"Error while running {name}: {e}"


# ---------- built-in memory tools ----------

@tools.register(
    "remember_fact",
    "Save a new fact learned about the user (preference, skill, habit, goal, anything personal). "
    "Use whenever the user reveals something worth remembering.",
    {
        "type": "object",
        "properties": {"fact": {"type": "string", "description": "The fact, phrased in third person"}},
        "required": ["fact"],
    },
)
def _remember_fact(fact: str) -> str:
    memory.add_fact(fact)
    return f"Remembered: {fact}"


@tools.register(
    "update_profile",
    "Update a structured field of the user profile. Dotted keys, e.g. "
    "'job_preferences.salary_min', 'posting_style.linkedin_tone', 'name', 'schedule.timezone'.",
    {
        "type": "object",
        "properties": {
            "key": {"type": "string"},
            "value": {"description": "New value (string, number, or list)"},
        },
        "required": ["key", "value"],
    },
)
def _update_profile(key: str, value) -> str:
    memory.update_profile(key, value)
    return f"Profile updated: {key} = {value}"


@tools.register(
    "recall_memory",
    "Search long-term memory for past events, tasks, and conversations. "
    "Use for questions like 'what did I do yesterday' or 'did we apply to that job'.",
    {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
)
def _recall_memory(query: str) -> str:
    events = memory.recall(query)
    if not events:
        return "No matching memories found."
    return "\n".join(f"[{e['timestamp']}] {e['type']}: {e['description']} -> {e['result']}" for e in events)
