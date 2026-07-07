# PROGRESS.md — Personal AI Chief of Staff

> **Resume instructions:** Read this file + CONTEXT.md, then continue from "In Progress".
> Update this file after every completed module.

## ✅ Completed
- Phase 1 — Foundation: config/settings.py, core/logger.py, core/memory.py (SQLite +
  optional ChromaDB + JSON profile), core/brain.py (Claude + Gemini fallback),
  core/agent.py (tool registry + manual tool-use loop + confirmation gate),
  ui/chat_interface.py, ui/first_run.py, main.py, .env.example, requirements.txt
- Phase 2 — Voice: core/voice.py (faster-whisper in, edge-tts out, mp3 playback
  via PowerShell MediaPlayer on Windows), core/wake_word.py (fuzzy wake word loop)
- Phase 3 — Google: integrations/google_auth.py (OAuth, token cache),
  integrations/gmail_agent.py (check/read/draft/send/reply),
  integrations/calendar_agent.py (list/create/delete events)
- Phase 4 — Computer use: core/computer_use.py (Playwright persistent-profile
  browser, PyAutoGUI desktop helpers, Claude-vision action loop, browser_open /
  browser_task / read_current_page tools)
- Phase 5 — LinkedIn: integrations/linkedin_agent.py (post via selectors with
  vision fallback, job search, Easy Apply with confirmation)
- Phase 6 — GitHub: integrations/github_agent.py (PR review list, digest,
  notifications, repo summary)
- Phase 7 — Facebook: integrations/facebook_agent.py (create listing with photo
  upload, check messages, mark sold)
- Phase 8 — Sub-agents: agents/marketer.py, job_hunter.py (with SQLite
  application tracker), assistant.py, seller.py, dev_monitor.py
- Phase 9 — Morning routine: core/scheduler.py (daily schedule + on-demand
  morning_briefing tool, notification + voice delivery)
- Phase 10 — Polish: ui/notifications.py (toast), ui/dashboard.py (live status),
  README.md (full setup guide), first-run wizard (ui/first_run.py)

## 🔄 In Progress
- (nothing — build complete; see verification notes below)

## ✅ Verification done (2026-07-08)
- All modules compile (python -m compileall)
- All 22 modules import cleanly with full deps; 37 tools register
- Memory system tested end-to-end incl. ChromaDB vector recall
- `python main.py` without .env degrades gracefully (clear setup message)
- Full requirements.txt installed + Playwright Chromium downloaded
  (first install hit disk-full; fixed by purging pip cache + chunked install)

## ✅ Gemini upgrade (2026-07-08, later session)
- core/brain.py migrated to the new `google-genai` SDK
- Gemini now does FULL tool calling (translation layer: anthropic message
  format <-> gemini contents, incl. images and Gemini-3 thought signatures)
- Model fallback chain for free-tier quotas: GEMINI_MODEL (gemini-3.5-flash,
  only 20 req/day free!) -> gemini-2.5-flash -> gemini-2.0-flash -> flash-latest
- integrations/github_agent.py: added github_create_repo + github_push_file
  (both require user confirmation)
- Live-verified: tool round trip via Gemini works; GitHub token authenticates
  (note: token account is nikolozdidebashvili19, .env says ERRORniku404)

## ⚠️ Known follow-ups
- Add prompt caching to the Claude path when the user gets an Anthropic key
- Real secrets were briefly in tracked .env.example (since sanitized) — user
  should rotate the Gemini key at some point

## ⏳ Not Started / Future ideas
- Cross-posting to other platforms (marketer)
- Indeed/Glassdoor job sources in addition to LinkedIn
- Price-adjustment automation for marketplace listings
- Wake-word engine upgrade (pvporcupine) if whisper chunking is too slow

## 🔧 Current Session Goal
Full scaffold built (all 10 phases coded). Remaining: dependency install +
smoke test + final commit. User still needs to: create .env with API keys,
run `playwright install chromium`, and do the first-run wizard.
