# 🤖 Personal AI Chief of Staff

A fully autonomous personal assistant that runs 24/7 on your own machine. It manages
Gmail, Google Calendar, GitHub, LinkedIn, and Facebook Marketplace, responds to a voice
wake word, remembers everything it learns about you, and — when no API exists — controls
a real browser like a human would.

**It's a friend, coworker, and assistant all in one.** Its name is Aria (rename it in `.env`).

## What it can do

| Say… | It does… |
|---|---|
| "check my emails" | Summarizes unread mail, flags urgent, drafts replies in your voice |
| "what's on my calendar today" | Reads Google Calendar; can book/cancel meetings |
| "write a LinkedIn post about X" | Drafts in your style → you approve → it posts via the browser |
| "apply to remote Python jobs" | Searches LinkedIn Jobs, ranks by fit, Easy-Applies with confirmation, tracks everything |
| "what PRs do I need to review" | GitHub digest: PRs, issues, notifications |
| "list my old monitor for 100 euros" | Writes the listing, uploads photos, publishes on Marketplace |
| "what did I do yesterday" | Answers from long-term memory |
| *(8:00 every morning)* | Spoken morning briefing: email, meetings, GitHub, job pipeline |

## Setup

```bash
# 1. Install dependencies (Python 3.10+)
pip install -r requirements.txt
playwright install chromium

# 2. Configure
copy .env.example .env      # then edit .env
```

Minimum to start chatting: **ANTHROPIC_API_KEY** (get one at console.anthropic.com).
Everything else is optional — features light up as you add keys:

| Key | Enables |
|---|---|
| `ANTHROPIC_API_KEY` | The brain (Claude) — tool use, vision browser control |
| `GEMINI_API_KEY` | Free fallback brain if Claude is unavailable |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Gmail + Calendar (create an OAuth "Desktop app" in Google Cloud Console, enable Gmail & Calendar APIs) |
| `GITHUB_TOKEN` | GitHub monitoring (fine-grained PAT with repo + notifications read) |
| LinkedIn / Facebook | No keys — log in once in the agent's browser window when asked |

```bash
# 3. Run
python main.py
```

First run asks a few questions (name, work, goals, resume) and saves them to persistent
memory. Drop your resume at `data/resume.pdf` for job hunting.

## Voice

- Say **"hey aria"** (customizable) — local wake-word detection, no cloud audio.
- Speech-to-text: faster-whisper running locally on CPU. Text-to-speech: free Edge TTS.
- Toggle with `ENABLE_VOICE` / `ENABLE_WAKE_WORD` in `.env`, or type `voice off` in chat.

## How it never gets stuck

1. **API first** (Gmail, Calendar, GitHub) — fast and reliable.
2. **Browser automation** (Playwright, persistent logged-in profile) — LinkedIn, Facebook.
3. **Vision fallback** — screenshots go to Claude, which decides the next click/type, so
   unfamiliar UIs still work. Logins/captchas pause and ask you to take over.

## Safety rails

- Anything irreversible — sending email, posting, applying, publishing a listing,
  deleting events — asks **you** for confirmation first. Always.
- Secrets live only in `.env` (gitignored). Memory, tokens, and browser profile live in
  `data/` (gitignored).
- Every action is logged to `logs/assistant.log`.

## Project layout

```
main.py                  entry point — starts everything
config/settings.py       all configuration (from .env)
core/agent.py            main agent loop + tool registry
core/memory.py           episodic (SQLite/Chroma) + semantic (profile) memory
core/brain.py            Claude primary, Gemini fallback
core/voice.py            whisper in, edge-tts out
core/wake_word.py        "hey aria" listener
core/computer_use.py     browser/desktop/vision control layers
core/scheduler.py        morning routine
integrations/            gmail, calendar, github, linkedin, facebook
agents/                  marketer, job_hunter, assistant, seller, dev_monitor
ui/                      chat interface, first-run wizard, dashboard, notifications
```

Extra tools: `python -m ui.dashboard` shows a live status view.
`PROGRESS.md` tracks build state; `CONTEXT.md` holds what the agent knows about you.

## Resuming development

New Claude Code session? Say:
> "Read PROGRESS.md and CONTEXT.md, then resume building the Personal AI Chief of Staff project"

## A note on LinkedIn/Facebook automation

These platforms have no public APIs for personal posting/listing, so the agent drives a
visible browser using your own logged-in session — the same actions you'd do by hand,
just automated. Use reasonable volumes; aggressive automation can violate platform terms.
