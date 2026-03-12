"""Simple JSON file state tracking for seen articles and posted signals."""

import json
import os
from datetime import datetime, timezone

import config


def load() -> dict:
    """Load state from disk."""
    if not os.path.exists(config.STATE_FILE):
        return _empty_state()
    try:
        with open(config.STATE_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return _empty_state()


def save(state: dict) -> None:
    """Save state to disk."""
    with open(config.STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def is_article_seen(state: dict, url: str) -> bool:
    return url in state.get("seen_urls", [])


def mark_article_seen(state: dict, url: str) -> None:
    state.setdefault("seen_urls", []).append(url)


def posts_today(state: dict) -> int:
    """Count how many posts have been made today."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return len([p for p in state.get("posts", []) if p.get("date") == today])


def record_post(state: dict, text: str, source_url: str) -> None:
    """Record a published post."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    state.setdefault("posts", []).append({
        "text": text,
        "source_url": source_url,
        "date": today,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


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
