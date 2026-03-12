"""Structured run logging with GitHub push."""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone

import requests

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = "paperadam/signal-generator"
GITHUB_BRANCH = "main"


class RunLog:
    """Captures deliberation data for a single bot run."""

    def __init__(self):
        now = datetime.now(timezone.utc)
        self.run_id = now.strftime("%Y-%m-%dT%H-%M-%SZ")
        self.data = {
            "version": 1,
            "run_id": self.run_id,
            "timestamp": now.isoformat(),
            "run_type": None,
            "outcome": None,
            "timing": None,
            "feed_intake": None,
            "story_selection": None,
            "post_generation": None,
            "publishing": None,
            "engagement": None,
            "errors": [],
        }

    def set_run_type(self, run_type: str):
        self.data["run_type"] = run_type

    def set_outcome(self, outcome: str):
        self.data["outcome"] = outcome

    def set_timing(self, sleep_hours: bool = False, skipped: bool = False,
                   pre_delay: float = 0, engage_gap: float = 0):
        self.data["timing"] = {
            "sleep_hours": sleep_hours,
            "skipped_randomly": skipped,
            "pre_post_delay_minutes": round(pre_delay, 1),
            "engage_gap_delay_minutes": round(engage_gap, 1),
        }

    def record_feed_intake(self, total: int, matched: int, new: int,
                           articles: list[dict]):
        self.data["feed_intake"] = {
            "total_fetched": total,
            "matched_filters": matched,
            "new_articles": new,
            "articles": [
                {"title": a.get("title", ""), "source": a.get("source", ""),
                 "link": a.get("link", "")}
                for a in articles[:30]
            ],
        }

    def record_story_selection(self, considered: int, selected_stories: list[dict],
                               claude_raw: str = ""):
        self.data["story_selection"] = {
            "articles_considered": considered,
            "selected_count": len(selected_stories),
            "selected_stories": [
                {"title": a.get("title", ""), "source": a.get("source", ""),
                 "link": a.get("link", "")}
                for a in selected_stories
            ],
            "claude_raw_response": claude_raw[:1000],
        }

    def record_post_generation(self, stories_sent: int, posts: list[dict],
                               claude_raw: str = ""):
        self.data["post_generation"] = {
            "stories_sent": stories_sent,
            "generated_posts": posts,
            "claude_raw_response": claude_raw[:1000],
        }

    def record_publish_result(self, text: str, source_url: str,
                              uri: str = "", success: bool = True,
                              error: str = ""):
        if self.data["publishing"] is None:
            self.data["publishing"] = {"results": []}
        self.data["publishing"]["results"].append({
            "text": text,
            "source_url": source_url,
            "uri": uri,
            "success": success,
            "error": error,
        })

    def record_engagement(self, queries: list[str], candidates: list[dict],
                          selected_post: dict = None, reply_text: str = "",
                          reply_uri: str = "", reply_success: bool = True,
                          reply_error: str = "", claude_raw: str = ""):
        self.data["engagement"] = {
            "search_queries_used": queries,
            "candidates_found": len(candidates),
            "candidates": [
                {"author": c.get("author", ""), "text": c.get("text", "")[:200],
                 "likes": c.get("likes", 0), "query": c.get("query", "")}
                for c in candidates[:15]
            ],
            "selected_post": {
                "author": selected_post.get("author", ""),
                "text": selected_post.get("text", "")[:300],
            } if selected_post else None,
            "reply_text": reply_text,
            "reply_uri": reply_uri,
            "reply_success": reply_success,
            "reply_error": reply_error,
            "claude_raw_response": claude_raw[:1000],
        }

    def add_error(self, error: str):
        self.data["errors"].append(error)

    def to_dict(self) -> dict:
        return self.data

    def push_to_github(self):
        """Commit the run log JSON to the GitHub repo."""
        if not GITHUB_TOKEN:
            print("  warning: GITHUB_TOKEN not set, skipping log push")
            return

        path = f"logs/{self.run_id}.json"
        content = base64.b64encode(
            json.dumps(self.data, indent=2).encode()
        ).decode()

        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
        }
        payload = {
            "message": f"run log: {self.run_id}",
            "content": content,
            "branch": GITHUB_BRANCH,
        }

        try:
            resp = requests.put(url, headers=headers, json=payload, timeout=30)
            if resp.status_code in (200, 201):
                print(f"  pushed run log to {path}")
            else:
                print(f"  warning: failed to push log: {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            print(f"  warning: failed to push log: {e}")
