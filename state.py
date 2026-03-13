"""State tracking with GitHub persistence for Railway deployments."""

import base64
import json
import os
from datetime import datetime, timezone

import requests

import config

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = "paperadam/signal-generator"
GITHUB_BRANCH = "main"
STATE_GH_PATH = "state/state.json"


# ---------------------------------------------------------------------------
# GitHub-backed load / save
# ---------------------------------------------------------------------------

def _gh_headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }


def _load_from_github() -> tuple[dict, str]:
    """Fetch state.json from GitHub. Returns (state_dict, sha)."""
    if not GITHUB_TOKEN:
        return _empty_state(), ""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{STATE_GH_PATH}?ref={GITHUB_BRANCH}"
    try:
        resp = requests.get(url, headers=_gh_headers(), timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            content = base64.b64decode(data["content"]).decode()
            sha = data["sha"]
            return json.loads(content), sha
        elif resp.status_code == 404:
            return _empty_state(), ""
        else:
            print(f"  warning: github state fetch returned {resp.status_code}")
            return _empty_state(), ""
    except Exception as e:
        print(f"  warning: failed to load state from github: {e}")
        return _empty_state(), ""


def _save_to_github(state: dict, sha: str) -> None:
    """Write state.json back to GitHub."""
    if not GITHUB_TOKEN:
        print("  warning: GITHUB_TOKEN not set, state not persisted remotely")
        return

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{STATE_GH_PATH}"
    content = base64.b64encode(json.dumps(state, indent=2).encode()).decode()
    payload = {
        "message": "update state",
        "content": content,
        "branch": GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha

    try:
        resp = requests.put(url, headers=_gh_headers(), json=payload, timeout=15)
        if resp.status_code in (200, 201):
            print("  state synced to github")
        else:
            print(f"  warning: failed to save state to github: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        print(f"  warning: failed to save state to github: {e}")


# Keep the sha between load/save in a single run
_github_sha = ""


def load() -> dict:
    """Load state: try GitHub first, fall back to local file."""
    global _github_sha

    # Try GitHub (primary for Railway)
    gh_state, sha = _load_from_github()
    if sha:
        _github_sha = sha
        # Also save locally as a cache
        _save_local(gh_state)
        return gh_state

    # Fall back to local file (for local dev)
    if os.path.exists(config.STATE_FILE):
        try:
            with open(config.STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    return _empty_state()


def save(state: dict) -> None:
    """Save state to both local disk and GitHub."""
    global _github_sha
    _save_local(state)
    _save_to_github(state, _github_sha)


def _save_local(state: dict) -> None:
    """Save state to local disk."""
    try:
        with open(config.STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except IOError as e:
        print(f"  warning: failed to save local state: {e}")


# ---------------------------------------------------------------------------
# State accessors (unchanged)
# ---------------------------------------------------------------------------

def is_article_seen(state: dict, url: str) -> bool:
    return url in state.get("seen_urls", [])


def mark_article_seen(state: dict, url: str) -> None:
    state.setdefault("seen_urls", []).append(url)


def posts_today(state: dict) -> int:
    """Count how many posts have been made today."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return len([p for p in state.get("posts", []) if p.get("date") == today])


def record_post(state: dict, text: str, source_url: str, theme: str = "") -> None:
    """Record a published post."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = {
        "text": text,
        "source_url": source_url,
        "date": today,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if theme:
        entry["theme"] = theme
    state.setdefault("posts", []).append(entry)


def is_replied_to(state: dict, uri: str) -> bool:
    return uri in state.get("replied_to", [])


def replies_today(state: dict) -> int:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return len([r for r in state.get("replies", []) if r.get("date") == today])


def record_reply(state: dict, post_uri: str, reply_text: str, author: str = "") -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    state.setdefault("replied_to", []).append(post_uri)
    state.setdefault("replies", []).append({
        "post_uri": post_uri,
        "text": reply_text,
        "author": author,
        "date": today,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


def cleanup_old(state: dict, keep_days: int = 7) -> None:
    """Remove state entries older than keep_days."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=keep_days)).strftime("%Y-%m-%d")

    state["posts"] = [p for p in state.get("posts", []) if p.get("date", "") >= cutoff]
    state["replies"] = [r for r in state.get("replies", []) if r.get("date", "") >= cutoff]

    # Keep lists from growing unbounded
    for key in ("seen_urls", "replied_to"):
        items = state.get(key, [])
        if len(items) > 2000:
            state[key] = items[-2000:]


def _empty_state() -> dict:
    return {"seen_urls": [], "posts": [], "replied_to": [], "replies": []}
