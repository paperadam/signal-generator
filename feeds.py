"""Fetch and filter RSS feeds for relevant articles."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import feedparser

import config


def fetch_all_feeds() -> list[dict]:
    """Fetch articles from all configured RSS feeds."""
    articles = []
    cutoff = time.time() - (config.ARTICLE_LOOKBACK_HOURS * 3600)

    for feed_url in config.FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                published = _parse_date(entry)
                if published and published < cutoff:
                    continue

                article = {
                    "title": entry.get("title", "").strip(),
                    "summary": _clean_summary(entry.get("summary", "")),
                    "link": entry.get("link", ""),
                    "published": published or time.time(),
                    "source": feed.feed.get("title", feed_url),
                }
                if article["title"]:
                    articles.append(article)
        except Exception as e:
            print(f"  warning: failed to fetch {feed_url}: {e}")

    articles = _deduplicate(articles)
    return sorted(articles, key=lambda a: a["published"], reverse=True)


def filter_relevant(articles: list[dict]) -> list[dict]:
    """Filter articles by topic keyword relevance."""
    relevant = []
    keywords = [k.lower() for k in config.TOPIC_KEYWORDS]

    for article in articles:
        text = f"{article['title']} {article['summary']}".lower()
        if any(kw in text for kw in keywords):
            relevant.append(article)

    return relevant


def _parse_date(entry) -> float | None:
    """Extract a unix timestamp from a feed entry."""
    for field in ("published_parsed", "updated_parsed"):
        parsed = entry.get(field)
        if parsed:
            try:
                dt = datetime(*parsed[:6], tzinfo=timezone.utc)
                return dt.timestamp()
            except (TypeError, ValueError):
                continue
    return None


def _clean_summary(summary: str) -> str:
    """Strip HTML tags from summary text."""
    import re
    text = re.sub(r"<[^>]+>", " ", summary)
    text = re.sub(r"\s+", " ", text)
    return text.strip()[:500]


def _deduplicate(articles: list[dict]) -> list[dict]:
    """Remove duplicate articles by URL."""
    seen = set()
    unique = []
    for article in articles:
        url = article["link"]
        if url and url not in seen:
            seen.add(url)
            unique.append(article)
    return unique
