/* Simple chat frontend: API-key gate first, then WebSocket chat. No dependencies. */

const $ = (id) => document.getElementById(id);
const messagesEl = $("messages");
const inputEl = $("input");
const sendBtn = $("sendBtn");

let ws = null;
let agentName = "Aria";
let thinkingEl = null;

/* ---------- markdown-lite (bold, italics, code, links, lists, headings) ---------- */

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function renderMarkdown(text) {
  const codeBlocks = [];
  let src = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, _lang, code) => {
    codeBlocks.push(code);
    return `\u0000${codeBlocks.length - 1}\u0000`;
  });

  src = escapeHtml(src);
  src = src.replace(/`([^`\n]+)`/g, "<code>$1</code>");
  src = src.replace(/\*\*([^*\n]+)\*\*/g, "<b>$1</b>");
  src = src.replace(/(^|\s)\*([^*\n]+)\*/g, "$1<i>$2</i>");
  src = src.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  src = src.replace(/^## (.+)$/gm, "<h2>$1</h2>");
  src = src.replace(/^# (.+)$/gm, "<h1>$1</h1>");
  src = src.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  src = src.replace(/(^|[^"(])(https?:\/\/[^\s<]+)/g, '$1<a href="$2" target="_blank" rel="noopener">$2</a>');

  // group consecutive "- " lines into <ul>
  src = src.replace(/((?:^[-*] .+\n?)+)/gm, (block) => {
    const items = block.trim().split("\n").map((l) => `<li>${l.replace(/^[-*] /, "")}</li>`).join("");
    return `<ul>${items}</ul>`;
  });
  // group consecutive "1. " lines into <ol>
  src = src.replace(/((?:^\d+\. .+\n?)+)/gm, (block) => {
    const items = block.trim().split("\n").map((l) => `<li>${l.replace(/^\d+\. /, "")}</li>`).join("");
    return `<ol>${items}</ol>`;
  });

  src = src.replace(/\u0000(\d+)\u0000/g, (_, i) => `<pre><code>${escapeHtml(codeBlocks[+i])}</code></pre>`);
  return src;
}

/* ---------- message rendering ---------- */

function scrollDown() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function addMessage(role, text, { markdown = false } = {}) {
  const wrap = document.createElement("div");
  wrap.className = `msg ${role}`;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  if (markdown) {
    bubble.style.whiteSpace = "normal";
    bubble.innerHTML = renderMarkdown(text);
  } else {
    bubble.textContent = text;
  }
  wrap.appendChild(bubble);
  messagesEl.appendChild(wrap);
  scrollDown();
  return wrap;
}

function showThinking() {
  hideThinking();
  thinkingEl = document.createElement("div");
  thinkingEl.className = "msg agent";
  thinkingEl.innerHTML = '<div class="bubble typing"><span></span><span></span><span></span></div>';
  messagesEl.appendChild(thinkingEl);
  scrollDown();
}

function hideThinking() {
  if (thinkingEl) { thinkingEl.remove(); thinkingEl = null; }
}

function addConfirmCard(id, question) {
  const card = document.createElement("div");
  card.className = "confirm-card";
  card.innerHTML = `
    <div class="q">${escapeHtml(question)}</div>
    <div class="confirm-actions">
      <button class="allow">Allow</button>
      <button class="deny">Deny</button>
    </div>
    <div class="verdict"></div>`;
  const resolve = (allow) => {
    ws?.send(JSON.stringify({ type: "confirm_response", id, allow }));
    card.classList.add("resolved");
    card.querySelector(".verdict").textContent = allow ? "✓ allowed" : "✕ denied";
    showThinking(); // agent keeps working after the verdict
  };
  card.querySelector(".allow").addEventListener("click", () => resolve(true));
  card.querySelector(".deny").addEventListener("click", () => resolve(false));
  messagesEl.appendChild(card);
  hideThinking();
  scrollDown();
}

/* ---------- websocket ---------- */

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);

  ws.onopen = () => { $("connDot").classList.add("ok"); setBusy(false); };

  ws.onclose = () => {
    $("connDot").classList.remove("ok");
    hideThinking();
    setTimeout(connect, 2000);
  };

  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    switch (msg.type) {
      case "thinking":
        showThinking();
        break;
      case "reply":
        hideThinking();
        addMessage("agent", msg.text || "(no reply)", { markdown: true });
        setBusy(false);
        break;
      case "confirm":
        addConfirmCard(msg.id, msg.question);
        break;
      case "info":
        addMessage("system", msg.text);
        break;
      case "error":
        hideThinking();
        addMessage("error", msg.text);
        setBusy(false);
        break;
    }
  };
}

/* ---------- composer ---------- */

function setBusy(busy) {
  sendBtn.disabled = busy;
}

function send() {
  const text = inputEl.value.trim();
  if (!text || sendBtn.disabled || ws?.readyState !== WebSocket.OPEN) return;
  addMessage("user", text);
  ws.send(JSON.stringify({ type: "chat", text }));
  inputEl.value = "";
  inputEl.style.height = "auto";
  setBusy(true);
}

$("composer").addEventListener("submit", (e) => { e.preventDefault(); send(); });

inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
});

inputEl.addEventListener("input", () => {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 160) + "px";
});

/* ---------- key gate ---------- */

function enterChat() {
  $("gate").classList.add("hidden");
  $("chat").classList.remove("hidden");
  addMessage("agent", `Hi! I'm ${agentName}, your AI Chief of Staff. What can I do for you?`);
  connect();
  inputEl.focus();
}

async function submitKeys() {
  const btn = $("enterBtn");
  const errEl = $("gateError");
  errEl.classList.add("hidden");
  btn.disabled = true;
  btn.textContent = "Checking…";
  try {
    const res = await fetch("/api/keys", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        anthropic_key: $("claudeKey").value.trim(),
        gemini_key: $("geminiKey").value.trim(),
      }),
    });
    const s = await res.json();
    if (s.brain_available) {
      enterChat();
    } else {
      errEl.textContent = "Please enter at least one API key (Claude or Gemini).";
      errEl.classList.remove("hidden");
    }
  } catch {
    errEl.textContent = "Could not reach the server — is it still running?";
    errEl.classList.remove("hidden");
  } finally {
    btn.disabled = false;
    btn.textContent = "Enter";
  }
}

$("enterBtn").addEventListener("click", submitKeys);
["claudeKey", "geminiKey"].forEach((id) =>
  $(id).addEventListener("keydown", (e) => { if (e.key === "Enter") submitKeys(); })
);

/* ---------- boot ---------- */

async function boot() {
  try {
    const s = await (await fetch("/api/status")).json();
    agentName = s.agent_name;
    document.title = `${s.agent_name} — Personal AI Chief of Staff`;
    $("gateTitle").textContent = `Welcome to ${s.agent_name}`;
    $("gateAvatar").textContent = s.agent_name[0].toUpperCase();
    $("headerTitle").textContent = s.agent_name;
    $("modelBadge").textContent = s.model;
    if (s.claude) $("claudeHint").textContent = "✓ configured — leave blank to keep";
    if (s.gemini) $("geminiHint").textContent = "✓ configured — leave blank to keep";
  } catch { /* gate still works with defaults */ }
  $("claudeKey").focus();
}

boot();
