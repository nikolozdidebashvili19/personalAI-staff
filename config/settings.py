"""Central configuration. Everything is loaded from .env — never hardcode secrets."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"

load_dotenv(PROJECT_ROOT / ".env")


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    # AI brains
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-3.5-flash"))
    claude_model: str = field(default_factory=lambda: os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"))

    # Google
    google_client_id: str = field(default_factory=lambda: os.getenv("GOOGLE_CLIENT_ID", ""))
    google_client_secret: str = field(default_factory=lambda: os.getenv("GOOGLE_CLIENT_SECRET", ""))
    google_redirect_uri: str = field(default_factory=lambda: os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8080"))

    # GitHub
    github_token: str = field(default_factory=lambda: os.getenv("GITHUB_TOKEN", ""))
    github_username: str = field(default_factory=lambda: os.getenv("GITHUB_USERNAME", ""))

    # Agent identity
    agent_name: str = field(default_factory=lambda: os.getenv("AGENT_NAME", "Aria"))
    agent_voice: str = field(default_factory=lambda: os.getenv("AGENT_VOICE", "en-US-AriaNeural"))
    wake_word: str = field(default_factory=lambda: os.getenv("WAKE_WORD", "hey aria").lower())

    # User
    user_name: str = field(default_factory=lambda: os.getenv("USER_NAME", ""))
    user_email: str = field(default_factory=lambda: os.getenv("USER_EMAIL", ""))
    user_timezone: str = field(default_factory=lambda: os.getenv("USER_TIMEZONE", "UTC"))
    resume_path: str = field(default_factory=lambda: os.getenv("RESUME_PATH", str(DATA_DIR / "resume.pdf")))

    # Features
    enable_voice: bool = field(default_factory=lambda: _bool("ENABLE_VOICE", True))
    enable_computer_use: bool = field(default_factory=lambda: _bool("ENABLE_COMPUTER_USE", True))
    enable_wake_word: bool = field(default_factory=lambda: _bool("ENABLE_WAKE_WORD", True))
    enable_morning_routine: bool = field(default_factory=lambda: _bool("ENABLE_MORNING_ROUTINE", True))
    morning_routine_time: str = field(default_factory=lambda: os.getenv("MORNING_ROUTINE_TIME", "08:00"))

    # Paths
    memory_db_path: Path = field(default_factory=lambda: DATA_DIR / "memory.db")
    user_context_path: Path = field(default_factory=lambda: DATA_DIR / "user_context.json")
    user_profile_path: Path = field(default_factory=lambda: PROJECT_ROOT / "config" / "user_profile.json")
    chroma_dir: Path = field(default_factory=lambda: DATA_DIR / "chroma")
    browser_profile_dir: Path = field(default_factory=lambda: DATA_DIR / "browser_profile")

    def ensure_dirs(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def has_anthropic(self) -> bool:
        return bool(self.anthropic_api_key) and "your_key" not in self.anthropic_api_key

    @property
    def has_gemini(self) -> bool:
        return bool(self.gemini_api_key) and "your_key" not in self.gemini_api_key

    @property
    def has_google(self) -> bool:
        return bool(self.google_client_id) and "your_key" not in self.google_client_id

    @property
    def has_github(self) -> bool:
        return bool(self.github_token) and "your_key" not in self.github_token


settings = Settings()
settings.ensure_dirs()
