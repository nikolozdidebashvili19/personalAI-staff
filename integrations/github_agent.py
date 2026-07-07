"""GitHub integration via the REST API (PyGithub)."""

from datetime import datetime, timedelta, timezone

from config.settings import settings
from core.agent import tools
from core.logger import get_logger

log = get_logger("github")

_client = None


def _gh():
    global _client
    if _client is None:
        if not settings.has_github:
            raise RuntimeError("GitHub not configured — set GITHUB_TOKEN in .env")
        from github import Auth, Github

        _client = Github(auth=Auth.Token(settings.github_token))
    return _client


@tools.register(
    "github_prs_to_review",
    "List open pull requests that need the user's review (or are open on their repos).",
    {"type": "object", "properties": {}},
)
def github_prs_to_review() -> str:
    gh = _gh()
    user = gh.get_user()
    lines = []
    review_requested = gh.search_issues(f"is:pr is:open review-requested:{user.login}")
    for pr in list(review_requested[:10]):
        lines.append(f"REVIEW NEEDED: {pr.title} — {pr.html_url}")
    own_open = gh.search_issues(f"is:pr is:open author:{user.login}")
    for pr in list(own_open[:10]):
        lines.append(f"Your open PR: {pr.title} — {pr.html_url}")
    return "\n".join(lines) or "No open PRs need attention. 🎉"


@tools.register(
    "github_digest",
    "Daily digest of the user's GitHub: recent activity on their repos "
    "(commits, issues opened/closed, PRs) in the last N hours.",
    {
        "type": "object",
        "properties": {"hours": {"type": "integer", "default": 24}},
    },
)
def github_digest(hours: int = 24) -> str:
    gh = _gh()
    user = gh.get_user()
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    lines = [f"GitHub digest for {user.login} (last {hours}h):"]
    repos = list(user.get_repos(sort="pushed"))[:8]
    for repo in repos:
        if repo.pushed_at and repo.pushed_at.replace(tzinfo=timezone.utc) < since:
            continue
        entry = [f"\n📦 {repo.full_name}"]
        try:
            commits = list(repo.get_commits(since=since))[:5]
            for c in commits:
                entry.append(f"  commit: {c.commit.message.splitlines()[0][:80]}")
        except Exception:
            pass
        try:
            for issue in list(repo.get_issues(state="open", since=since))[:5]:
                kind = "PR" if issue.pull_request else "issue"
                entry.append(f"  open {kind}: {issue.title[:80]}")
        except Exception:
            pass
        if len(entry) > 1:
            lines.extend(entry)
    if len(lines) == 1:
        lines.append("Quiet — no recent activity on your repos.")
    return "\n".join(lines)


@tools.register(
    "github_notifications",
    "List the user's unread GitHub notifications.",
    {"type": "object", "properties": {}},
)
def github_notifications() -> str:
    gh = _gh()
    notes = list(gh.get_user().get_notifications())[:15]
    if not notes:
        return "No unread GitHub notifications."
    return "\n".join(
        f"[{n.repository.full_name}] {n.subject.type}: {n.subject.title} ({n.reason})" for n in notes
    )


@tools.register(
    "github_repo_summary",
    "Summarize one repository: description, open issues/PRs count, last push, top languages.",
    {
        "type": "object",
        "properties": {"repo": {"type": "string", "description": "owner/name, e.g. ERRORniku404/myrepo"}},
        "required": ["repo"],
    },
)
def github_repo_summary(repo: str) -> str:
    gh = _gh()
    r = gh.get_repo(repo)
    langs = ", ".join(list(r.get_languages().keys())[:5]) or "n/a"
    return (
        f"{r.full_name}: {r.description or '(no description)'}\n"
        f"⭐ {r.stargazers_count} | open issues+PRs: {r.open_issues_count} | "
        f"last push: {r.pushed_at} | languages: {langs}\n{r.html_url}"
    )
